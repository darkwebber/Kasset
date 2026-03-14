"""
reflection.py — Pre-execution and post-execution verification for tool calls.

Catches syntax errors, common mistakes, and provides structured feedback
BEFORE wasting a tool round on broken code. Also verifies post-execution
results to detect silent failures.
"""

import ast
import logging
import re
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)


class ReflectionEngine:
    """Pre/post execution checks for tool calls."""

    # Common mistakes the model makes that we can catch statically
    _PYTHON_ANTIPATTERNS = [
        # plt.show() in sandbox (monkey-patched but wastes a call)
        (r'\bplt\.show\(\)', "plt.show() is not needed — plots are auto-captured."),
        # plt.savefig() instead of letting auto-capture handle it
        (r'\bplt\.savefig\(', "plt.savefig() is not needed — plots are auto-captured. Remove it."),
        # import inside function (sandbox already has imports)
        (r'^import\s+(pandas|numpy|matplotlib|seaborn|scipy|sklearn|torch|PIL)',
         "This module is already pre-imported in the sandbox. Skip the import."),
        # input() blocks the sandbox forever
        (r'\binput\s*\(', "input() blocks the sandbox — remove it. Use hardcoded values or tool parameters instead."),
        # os.system / subprocess in sandbox — use run_command tool instead
        (r'\bos\.system\s*\(', "os.system() should not be used in sandbox code. Use the run_command tool instead."),
        (r'\bsubprocess\.(run|call|Popen|check_output)\s*\(',
         "subprocess calls should not be used in sandbox code. Use the run_command tool instead."),
        # while True without break — likely infinite loop
        (r'while\s+True\s*:', "while True detected — ensure there is a break condition to avoid infinite loops."),
    ]

    @classmethod
    def pre_check_python(cls, code: str) -> Optional[str]:
        """Check Python code for syntax errors and common mistakes before execution.
        Returns error/warning string if issues found, None if code looks ok.
        """
        if not code or not code.strip():
            return "Empty code — nothing to execute."

        # 1. Syntax check via AST
        try:
            ast.parse(code)
        except SyntaxError as e:
            return (
                f"SyntaxError before execution (line {e.lineno}): {e.msg}\n"
                f"Fix the syntax error and retry. Do NOT rewrite the entire script."
            )

        # 2. Check for common antipatterns (warnings, not blockers)
        warnings = []
        for pattern, msg in cls._PYTHON_ANTIPATTERNS:
            if re.search(pattern, code, re.MULTILINE):
                warnings.append(msg)

        # 3. Check for extremely long code (likely to be truncated)
        line_count = len(code.strip().splitlines())
        if line_count > 60:
            warnings.append(
                f"Code is {line_count} lines — risk of truncation. "
                f"Break into smaller steps (<40 lines each)."
            )

        if warnings:
            return "[Pre-check warnings]\n" + "\n".join(f"- {w}" for w in warnings)
        return None

    @classmethod
    def pre_check_cpp(cls, code: str) -> Optional[str]:
        """Basic pre-check for C++ code."""
        if not code or not code.strip():
            return "Empty code — nothing to compile."

        # Check for missing main function
        if 'int main' not in code and 'void main' not in code:
            return "Missing main() function. C++ programs need an entry point."

        # Check balanced braces
        opens = code.count('{')
        closes = code.count('}')
        if opens != closes:
            diff = opens - closes
            if diff > 0:
                return f"Unbalanced braces: {diff} unclosed '{{'. Check your code."
            else:
                return f"Unbalanced braces: {abs(diff)} extra '}}'. Check your code."

        return None

    @classmethod
    def pre_check(cls, tool_name: str, tool_args: Dict[str, Any]) -> Optional[str]:
        """Run pre-execution checks for any tool. Returns feedback or None."""
        if tool_name == "execute_python" and "code" in tool_args:
            return cls.pre_check_python(tool_args["code"])
        elif tool_name == "execute_cpp" and "code" in tool_args:
            return cls.pre_check_cpp(tool_args["code"])
        elif tool_name == "edit_file":
            # Check that old_text and new_text are different
            old = tool_args.get("old_text", "")
            new = tool_args.get("new_text", "")
            if old and old == new:
                return "old_text and new_text are identical — this edit would change nothing."
            if not old:
                return "old_text is empty — edit_file needs text to find and replace."
        elif tool_name == "read_file":
            path = tool_args.get("path", "")
            if not path:
                return "No path specified for read_file."
        return None

    @classmethod
    def post_check(
        cls, tool_name: str, tool_args: Dict[str, Any],
        result: str, images: List[str]
    ) -> Optional[str]:
        """Run post-execution verification. Returns advisory feedback or None."""
        if not result:
            return None

        result_lower = result.lower()

        # Detect silent failures in Python execution
        if tool_name == "execute_python":
            # Check for matplotlib without any output
            code = tool_args.get("code", "")
            if "plt." in code and not images and "(no output)" in result_lower:
                return (
                    "[Post-check] Code uses matplotlib but produced no plot. "
                    "Ensure you call plt.figure() and plotting functions. "
                    "Do NOT call plt.show() — plots are auto-captured."
                )

            # Detect infinite loop indicators
            if "timed out" in result_lower:
                return (
                    "[Post-check] Code timed out — likely an infinite loop. "
                    "Add loop bounds or break conditions."
                )

        # Detect file operation failures
        if tool_name in ("read_file", "write_file", "edit_file"):
            if "no such file" in result_lower or "does not exist" in result_lower:
                path = tool_args.get("path", "")
                return (
                    f"[Post-check] Path '{path}' not found. "
                    f"Use list_directory or search_files to find the correct path."
                )

        return None
