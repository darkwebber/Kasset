"""
tool_executor.py — Encapsulates tool validation, execution dispatch,
code dedup detection, and result context building.

Extracted from agent.py to keep the agent focused on orchestration
while tool execution logic is isolated and testable.
"""

import hashlib
import json
import logging
import re
from typing import Dict, Any, List, Optional, Tuple

from .tool_registry import execute_tool, run_approved_command
from .tool_parser import enrich_tool_error, auto_resolve_error
from .reflection import ReflectionEngine

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Manages tool execution lifecycle: validation, dedup, dispatch, enrichment."""

    # Tools that require local access (blocked for network clients)
    SHELL_TOOLS = {"run_command", "execute_python", "execute_cpp", "write_file"}

    def __init__(self, allowed_tools: List[str], allow_shell: bool = True, session_id: str = None):
        self.allowed_tools = set(allowed_tools)
        self.allow_shell = allow_shell
        self.session_id = session_id
        # Code dedup tracking
        self._prev_code_hashes: List[str] = []
        self._prev_code_norms: List[Tuple[str, str]] = []  # (hash, normalized)
        # Error tracking
        self.session_errors: List[str] = []
        self.consecutive_failures: int = 0
        self._error_patterns: List[str] = []

    def validate(self, tool_name: str) -> Optional[str]:
        """Validate a tool call. Returns error string if invalid, None if ok."""
        if not self.allow_shell and tool_name in self.SHELL_TOOLS:
            return "Error: Shell/code execution is disabled for network clients. Only the local machine can run commands."
        if tool_name not in self.allowed_tools:
            available = ", ".join(sorted(self.allowed_tools))
            return (
                f"Error: Tool '{tool_name}' does not exist. "
                f"The ONLY tools you can use are: {available}. "
                f"Pick one of these tools instead. Do NOT retry '{tool_name}'."
            )
        return None

    def check_code_dedup(self, tool_name: str, tool_args: dict) -> bool:
        """Check if code submission is a duplicate. Returns True if repeat detected."""
        if tool_name not in ("execute_python", "execute_cpp") or "code" not in tool_args:
            return False

        raw_code = tool_args["code"]
        # Normalize: strip whitespace, comments, blank lines for fuzzy matching
        normalized = re.sub(r'#[^\n]*', '', raw_code)  # strip comments
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        code_hash = hashlib.md5(normalized.encode()).hexdigest()

        is_repeat = code_hash in self._prev_code_hashes

        # Fuzzy match: catch near-identical code (e.g. 50→100 grid points)
        if not is_repeat and self._prev_code_norms:
            from difflib import SequenceMatcher
            for _, prev_norm in self._prev_code_norms:
                ratio = SequenceMatcher(None, normalized[:500], prev_norm[:500]).ratio()
                if ratio > 0.85:
                    is_repeat = True
                    logger.warning(f"Fuzzy code match detected (ratio={ratio:.2f})")
                    break

        if not is_repeat:
            self._prev_code_hashes.append(code_hash)
            self._prev_code_norms.append((code_hash, normalized))

        return is_repeat

    def execute(self, tool_name: str, tool_args: dict) -> Tuple[str, List[str], str]:
        """Execute a tool and return (result_text, images, html_artifact).

        Runs ReflectionEngine pre-check before execution and post-check after.
        Does NOT handle interactive widgets or consent — those stay in agent.py
        because they require SSE streaming integration.
        """
        validation_error = self.validate(tool_name)
        if validation_error:
            return validation_error, [], ""

        # Pre-execution reflection: catch syntax errors before wasting a round
        pre_feedback = ReflectionEngine.pre_check(tool_name, tool_args)
        if pre_feedback and pre_feedback.startswith(("SyntaxError", "Empty code", "Missing main", "Unbalanced", "old_text and new_text", "old_text is empty", "No path")):
            # Hard errors — don't execute, return the feedback as the result
            logger.info(f"ReflectionEngine blocked {tool_name}: {pre_feedback[:80]}")
            return f"Error (pre-check): {pre_feedback}", [], ""

        try:
            raw_result = execute_tool(tool_name, tool_args, session_id=self.session_id)
            if isinstance(raw_result, dict):
                tool_result = raw_result.get("output", "")
                images = raw_result.get("images", [])
                html = raw_result.get("html", "")
            else:
                tool_result = str(raw_result)
                images = []
                html = ""
        except Exception as tool_err:
            logger.error(f"Tool '{tool_name}' crashed: {tool_err}")
            tool_result = f"Error: Tool '{tool_name}' failed unexpectedly: {str(tool_err)[:200]}"
            images = []
            html = ""

        # Post-execution reflection: detect silent failures
        post_feedback = ReflectionEngine.post_check(tool_name, tool_args, tool_result, images)
        if post_feedback:
            tool_result += f"\n{post_feedback}"

        # Append pre-check warnings (non-blocking) to result
        if pre_feedback and not pre_feedback.startswith(("SyntaxError", "Empty code", "Missing main", "Unbalanced", "old_text", "No path")):
            tool_result += f"\n{pre_feedback}"

        return tool_result, images, html

    def execute_approved(self, command: str) -> Tuple[str, List[str], str]:
        """Execute a user-approved command."""
        approved_result = run_approved_command(command)
        if isinstance(approved_result, dict):
            return (
                approved_result.get("output", str(approved_result)),
                approved_result.get("images", []),
                approved_result.get("html", ""),
            )
        return str(approved_result), [], ""

    def build_result_context(
        self,
        tool_name: str,
        tool_args: dict,
        tool_result: str,
        images: List[str],
        html: str,
        tool_round: int,
        max_rounds: int,
        sandbox_globals: dict,
    ) -> str:
        """Build enriched context string for the next model round."""
        is_failure = (
            tool_result in ("(no output)", "")
            or str(tool_result).startswith("Error:")
            or "Traceback" in str(tool_result)
        )

        if is_failure:
            self.consecutive_failures += 1
        else:
            self.consecutive_failures = 0

        # Loop detection: repeated identical call
        call_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)[:200]}"
        if is_failure and call_sig in self.session_errors:
            self.consecutive_failures = max(self.consecutive_failures, 3)

        # Error-pattern loop detection
        if is_failure and tool_name in ("execute_python", "execute_cpp"):
            err_lines = str(tool_result).strip().splitlines()
            core_err = err_lines[-1] if err_lines else ""
            err_pattern = f"{tool_name}::{core_err[:100]}"
            if err_pattern in self._error_patterns:
                logger.warning(f"Same error pattern repeated: {core_err[:80]}")
                self.consecutive_failures = max(self.consecutive_failures, 3)
            self._error_patterns.append(err_pattern)

        failure_note = ""
        if self.consecutive_failures >= 3:
            failure_note = "\nIMPORTANT: Multiple tools have failed. Stop calling tools and give your best final answer with whatever data you have."

        # Use enriched error context for tool failures
        if is_failure and not failure_note:
            # Try auto-resolve: local cache → web search → cache result
            auto_fix = auto_resolve_error(tool_result, tool_name=tool_name)
            result_context = enrich_tool_error(tool_name, tool_args, tool_result)
            if auto_fix and auto_fix not in result_context:
                result_context += f"\n{auto_fix}"
        else:
            result_context = f"Tool result for {tool_name}: {tool_result}"

        # Compact status annotations
        status_parts = [f"[Round {tool_round + 1}/{max_rounds}]"]
        if images:
            _saved = sandbox_globals.get('_current_image_path', '')
            status_parts.append(
                f"[{len(images)} image(s) displayed"
                f"{f' — saved: {_saved}' if _saved else ''}]"
            )
            # Summarize what was accomplished from the tool output
            _result_lines = str(tool_result).strip().splitlines()
            _accomplished = "; ".join(l.strip() for l in _result_lines if l.strip() and not l.startswith("Traceback"))[:200]
            if _accomplished:
                status_parts.append(f"[COMPLETED: {_accomplished}]")
            status_parts.append(
                "[Image NOW VISIBLE on canvas. "
                "SELF-REVIEW: You can see the updated image via vision. "
                "Critically evaluate — does it match the user's request? Any artifacts or issues? "
                "If good: summarize in 1-2 sentences and STOP. Do NOT call img_show or execute_python again. "
                "Do NOT re-run operations that already succeeded (e.g. do not remove bg again if already removed). "
                "If bad: fix immediately with a targeted edit.]"
            )
        if html:
            status_parts.append(
                "[HTML artifact RENDERED and VISIBLE to user in an interactive iframe. "
                "TASK COMPLETE. Do NOT write this HTML to a file, do NOT re-output it, do NOT call html_preview again. "
                "Simply confirm what you built in 1-2 sentences and STOP.]"
            )
        if is_failure:
            err_summary = f"{tool_name}({json.dumps(tool_args)[:80]}): {str(tool_result)[:120]}"
            self.session_errors.append(err_summary)
            self.session_errors.append(call_sig)
        if self.session_errors:
            status_parts.append(f"[Errors: {'; '.join(self.session_errors[-2:])}]")

        result_context += "\n" + " ".join(status_parts) + failure_note
        return result_context

    @property
    def should_force_stop(self) -> bool:
        """True when too many consecutive failures — agent should stop calling tools."""
        return self.consecutive_failures >= 3
