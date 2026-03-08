import json
import hashlib
import logging
import re
import uuid
import threading
from pathlib import Path
from typing import List, Dict, Any, Generator, Tuple, Optional
from .tool_registry import execute_tool, run_approved_command
from .plugin_loader import plugin_loader
from .sandbox import _SHARED_GLOBALS as _sandbox_globals
from .persistence import user_memory, prompt_cache, chat_store
from .context_manager import (
    user_settings, SessionSummarizer, CartridgeContext, GlobalProfile
)

logger = logging.getLogger(__name__)

# ─── Consent state for commands requiring user approval ───
# Global registry keyed by consent_id. Each Agent instance creates unique IDs,
# so concurrent streams never collide.
_consent_registry: Dict[str, dict] = {}  # consent_id -> {"event": Event, "approved": bool}
_consent_lock = threading.Lock()

def _register_consent(consent_id: str) -> threading.Event:
    """Register a new consent entry. Returns the Event to wait on."""
    event = threading.Event()
    with _consent_lock:
        _consent_registry[consent_id] = {"event": event, "approved": False}
    return event

def _pop_consent(consent_id: str) -> dict:
    """Remove and return a consent entry."""
    with _consent_lock:
        return _consent_registry.pop(consent_id, {})

def approve_consent(consent_id: str):
    """Called by api.py when user approves a command."""
    with _consent_lock:
        entry = _consent_registry.get(consent_id)
    if entry:
        entry["approved"] = True
        entry["event"].set()

def deny_consent(consent_id: str):
    """Called by api.py when user denies a command."""
    with _consent_lock:
        entry = _consent_registry.get(consent_id)
    if entry:
        entry["approved"] = False
        entry["event"].set()

def parse_thinking(raw: str) -> Tuple[str, str]:
    """Extract thinking content from model output."""
    tag_pairs = [
        ("<think>", "</think>"),
        ("<|thinking|>", "<|/thinking|>"),
    ]
    for open_tag, close_tag in tag_pairs:
        if close_tag in raw:
            if open_tag in raw:
                start = raw.index(open_tag) + len(open_tag)
                end = raw.index(close_tag)
                thought = raw[start:end].strip()
                answer = (raw[:raw.index(open_tag)] + raw[end + len(close_tag):]).strip()
                return thought, answer
            else:
                parts = raw.split(close_tag, 1)
                return parts[0].strip(), parts[1].strip()

    for open_tag, _ in tag_pairs:
        if open_tag in raw:
            start = raw.index(open_tag) + len(open_tag)
            return raw[start:].strip(), ""
            
    return "", raw.strip()

def extract_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """Extract tool call JSON from model output. Handles multiple formats robustly."""
    # 1. Standard: <tool_call>...</tool_call>
    match = re.search(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL | re.IGNORECASE)
    if match:
        return _try_parse_tool_json(match.group(1))

    # 2. Unclosed tag: <tool_call>...{json}... (no closing tag — very common)
    match = re.search(r"<tool_call>\s*(.*)", text, re.DOTALL | re.IGNORECASE)
    if match:
        result = _try_parse_tool_json(match.group(1))
        if result:
            return result

    # 3. Alternative tag format: <|tool_call|>...<|/tool_call|>
    match = re.search(r"<\|tool_call\|>\s*(.*?)(?:<\|/tool_call\|>|$)", text, re.DOTALL)
    if match:
        result = _try_parse_tool_json(match.group(1))
        if result:
            return result

    # 4. Raw JSON with "name" and "arguments" keys (no tags at all)
    match = re.search(r'\{\s*"name"\s*:\s*"(\w+)"\s*,\s*"arguments"\s*:', text, re.DOTALL)
    if match:
        # Try to extract the full JSON object starting from this match
        start = match.start()
        result = _try_parse_tool_json(text[start:])
        if result:
            return result

    return None


def _fix_json_newlines(s: str) -> str:
    """Escape raw newlines/tabs inside JSON strings that the model forgot to escape."""
    return s.replace('\r\n', '\\n').replace('\r', '\\n').replace('\n', '\\n').replace('\t', '\\t')


def _try_parse_tool_json(raw: str) -> Optional[Dict[str, Any]]:
    """Attempt to parse a tool call JSON from potentially messy model output."""
    raw = raw.strip()
    if not raw:
        return None

    # Try direct parse first
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "name" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    # Try with fixed newlines (model often puts raw newlines in code strings)
    try:
        obj = json.loads(_fix_json_newlines(raw))
        if isinstance(obj, dict) and "name" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    # Extract the first complete JSON object using brace-depth counting
    brace_depth = 0
    start = None
    for i, ch in enumerate(raw):
        if ch == '{':
            if start is None:
                start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and start is not None:
                candidate = raw[start:i + 1]
                # Try raw first, then with newline fix
                for attempt in (candidate, _fix_json_newlines(candidate)):
                    try:
                        obj = json.loads(attempt)
                        if isinstance(obj, dict) and "name" in obj:
                            return obj
                    except json.JSONDecodeError:
                        pass
                start = None

    # Dedicated extraction for execute_python / execute_cpp — the most common failure
    # The model generates {"name":"execute_python","arguments":{"code":"...raw multi-line code..."}}
    name_match = re.search(r'"name"\s*:\s*"(\w+)"', raw)
    if name_match:
        tool_name = name_match.group(1)
        # For code tools, extract the code string directly
        if tool_name in ("execute_python", "execute_cpp"):
            code_match = re.search(r'"code"\s*:\s*"', raw)
            if code_match:
                code_start = code_match.end()
                # Scan for the closing quote of the code string (not preceded by \)
                i = code_start
                code_chars = []
                while i < len(raw):
                    if raw[i] == '\\' and i + 1 < len(raw):
                        code_chars.append(raw[i:i+2])
                        i += 2
                    elif raw[i] == '"':
                        break
                    else:
                        code_chars.append(raw[i])
                        i += 1
                code_value = ''.join(code_chars)
                # Unescape what the model did escape, keep raw newlines as-is
                code_value = code_value.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
                logger.info(f"Extracted code for {tool_name} ({len(code_value)} chars) via direct scan")
                return {"name": tool_name, "arguments": {"code": code_value}}

        # For other tools, try regex extraction of arguments
        args_match = re.search(r'"arguments"\s*:\s*\{', raw)
        if args_match:
            # Extract from the opening brace using depth counting
            depth = 0
            astart = args_match.end() - 1
            for i in range(astart, len(raw)):
                if raw[i] == '{': depth += 1
                elif raw[i] == '}': depth -= 1
                if depth == 0:
                    args_str = raw[astart:i+1]
                    for attempt in (args_str, _fix_json_newlines(args_str)):
                        try:
                            args = json.loads(attempt)
                            return {"name": tool_name, "arguments": args}
                        except json.JSONDecodeError:
                            pass
                    break

    if '<tool_call>' in raw.lower() or '"name"' in raw:
        logger.warning(f"Failed to parse tool call from: {raw[:200]}")
    return None


def _has_tool_call_attempt(text: str) -> bool:
    """Check if the model attempted a tool call but it failed to parse."""
    lower = text.lower()
    return '<tool_call>' in lower or '<|tool_call|>' in lower


def _diagnose_tool_call_error(text: str) -> str:
    """Analyze a failed tool call and produce a clear error message for the model."""
    # Extract the raw JSON attempt
    match = re.search(r'<tool_call>\s*(.*?)(?:</tool_call>|$)', text, re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(r'<\|tool_call\|>\s*(.*?)(?:<\|/tool_call\|>|$)', text, re.DOTALL)

    raw_json = match.group(1).strip() if match else ""
    snippet = raw_json[:300] if raw_json else text[-300:]

    # Diagnose specific issues
    issues = []
    if raw_json:
        brace_count = raw_json.count('{') - raw_json.count('}')
        if brace_count > 0:
            issues.append(f"Unclosed braces: {brace_count} opening '{{' without matching '}}'.")
        elif brace_count < 0:
            issues.append(f"Extra closing braces: {abs(brace_count)} unmatched '}}'.")

        # Check for raw newlines inside strings (most common failure)
        if '"code"' in raw_json:
            code_start = raw_json.find('"code"')
            # Check if there are unescaped newlines after the code key
            code_section = raw_json[code_start:]
            in_str = False
            for i, ch in enumerate(code_section):
                if ch == '"' and (i == 0 or code_section[i-1] != '\\'):
                    in_str = not in_str
                if in_str and ch == '\n':
                    issues.append("Raw newlines inside the 'code' string value. Use \\n instead of actual line breaks.")
                    break

        if '"name"' not in raw_json:
            issues.append("Missing 'name' key in the tool call JSON.")
        if '"arguments"' not in raw_json:
            issues.append("Missing 'arguments' key in the tool call JSON.")

        try:
            json.loads(raw_json)
        except json.JSONDecodeError as e:
            issues.append(f"JSON parse error: {e.msg} at position {e.pos}.")
    else:
        issues.append("The <tool_call> tag was found but no JSON content was extracted.")

    issue_text = "\n".join(f"  - {i}" for i in issues) if issues else "  - Unknown JSON formatting error."

    return (
        f"[SYSTEM] Your previous tool call failed to parse. Here's what went wrong:\n"
        f"{issue_text}\n\n"
        f"Your malformed output was:\n```\n{snippet}\n```\n\n"
        f"Fix the JSON and try again. Remember:\n"
        f"- The JSON must be valid. Use \\n for newlines and \\\" for quotes inside string values.\n"
        f"- Format: <tool_call>{{\"name\": \"tool_name\", \"arguments\": {{...}}}}</tool_call>\n"
        f"- Do NOT put any text after the </tool_call> tag."
    )


def _enrich_tool_error(tool_name: str, tool_args: dict, error_result: str) -> str:
    """Produce actionable feedback when a tool execution fails.
    Pattern-matches common error types and provides specific remediation hints."""
    hints = []
    err = error_result.lower()
    err_raw = error_result

    # ── File system errors ──
    if "no such file" in err or "does not exist" in err or "filenotfounderror" in err:
        path_hint = tool_args.get("path", tool_args.get("directory", ""))
        hints.append(f"The file/path doesn't exist. Use `list_directory` or `search_files` to verify the correct path first.")
        if path_hint:
            # Suggest checking parent directory
            from pathlib import PurePosixPath
            parent = str(PurePosixPath(path_hint).parent)
            hints.append(f"Try: list_directory(\"{parent}\") to see what exists.")
    elif "permission" in err and "denied" in err:
        hints.append("Permission denied. The sandbox cannot access this path. Try a different location or use ~/.")
    elif "isadirectoryerror" in err:
        hints.append("You tried to read a directory as a file. Use `list_directory` instead of `read_file`.")
    elif "notadirectoryerror" in err:
        hints.append("You tried to list a file as a directory. Use `read_file` instead of `list_directory`.")

    # ── Python code errors ──
    elif "syntaxerror" in err or "indentationerror" in err:
        # Try to extract line number
        line_match = re.search(r'line (\d+)', err_raw)
        line_info = f" at line {line_match.group(1)}" if line_match else ""
        hints.append(f"Syntax/indentation error{line_info}. Fix the specific line — do NOT rewrite the entire script.")
    elif "nameerror" in err:
        var_match = re.search(r"name '(\w+)' is not defined", err_raw)
        if var_match:
            hints.append(f"Variable `{var_match.group(1)}` is not defined. Check spelling, or define it before use. Remember: variables persist across execute_python calls.")
        else:
            hints.append("A variable is not defined. Check your variable names and ensure they're defined before use.")
    elif "typeerror" in err:
        hints.append("Type mismatch. Check function argument types and return values. Common causes: passing None where a value is expected, wrong number of arguments.")
    elif "keyerror" in err:
        key_match = re.search(r"KeyError:\s*['\"]?(\w+)", err_raw)
        key_info = f" Key `{key_match.group(1)}` not found." if key_match else ""
        hints.append(f"Dictionary key not found.{key_info} Use `.get()` for safe access or check available keys with `.keys()`.")
    elif "indexerror" in err:
        hints.append("List index out of range. Check the length of your list/array before indexing. Use `len()` to verify.")
    elif "valueerror" in err:
        hints.append("Invalid value. Check that input data is in the expected format (e.g., numeric strings for int(), valid dates for datetime).")
    elif "attributeerror" in err:
        attr_match = re.search(r"has no attribute '(\w+)'", err_raw)
        if attr_match:
            hints.append(f"Object has no attribute `{attr_match.group(1)}`. Check the object type with `type()` and use `dir()` to see available attributes.")
        else:
            hints.append("Attribute error. Verify the object type and available methods.")
    elif "modulenotfounderror" in err or "no module named" in err:
        mod_match = re.search(r"No module named ['\"](\w+)", err_raw)
        mod_name = mod_match.group(1) if mod_match else "the module"
        hints.append(f"Module `{mod_name}` is not installed. Pre-available: pandas, numpy, matplotlib, scipy, seaborn, plotly, Pillow, sympy. For others, ask the user to `pip install {mod_name}`.")
    elif "zerodivisionerror" in err:
        hints.append("Division by zero. Add a check before dividing (e.g., `if denominator != 0:`).")

    # ── Shell command errors ──
    elif "timed out" in err:
        hints.append("Command timed out (30s limit). Simplify the operation, add filters (e.g., head/tail), or break into smaller steps.")
    elif "blocked" in err:
        hints.append("This command is blocked for safety. Use an alternative approach or a different tool.")
    elif "consent_required" in err:
        hints.append("This command needs user approval. Wait for the consent prompt.")
    elif "command not found" in err:
        cmd_match = re.search(r"(\w+): command not found", err_raw)
        if cmd_match:
            hints.append(f"`{cmd_match.group(1)}` is not installed on this system. Try an alternative tool or approach.")
    elif "exit" in err and re.search(r'exit (\d+)', err):
        exit_match = re.search(r'exit (\d+)', err)
        hints.append(f"Command exited with code {exit_match.group(1)}. Check stderr output above for details.")

    # ── Generic fallback ──
    elif "traceback" in err and not hints:
        hints.append("An exception occurred. Read the traceback carefully and fix only the failing line(s).")

    base = f"Tool result for {tool_name}: {error_result}"
    if hints:
        base += "\n[Diagnosis: " + " ".join(hints) + "]"
    return base


def _extract_attachment_context(content: str) -> str:
    """
    Intelligently extract content from [Attached file: path] tags.
    For files: reads the content inline.
    For directories: lists the directory tree.
    Returns augmented content with attachment data injected.
    """
    import re as _re
    attachment_pattern = _re.compile(r'\[Attached file:\s*(.*?)\]')
    matches = attachment_pattern.findall(content)
    if not matches:
        return content

    augmented = content
    for file_path in matches:
        try:
            p = Path(file_path).expanduser().resolve()
            if not p.exists():
                continue

            if p.is_file():
                # Read file content (with limits)
                size = p.stat().st_size
                if size > 50 * 1024:
                    context = f"\n<attached_context path=\"{file_path}\">\n[File too large: {size / 1024:.0f}KB. Use read_file or run_command to inspect.]\n</attached_context>"
                else:
                    try:
                        text = p.read_text(encoding="utf-8")
                        lines = text.splitlines()
                        if len(lines) > 150:
                            text = "\n".join(lines[:150]) + f"\n... ({len(lines) - 150} more lines)"
                        context = f"\n<attached_context path=\"{file_path}\" type=\"file\" lines=\"{len(lines)}\" size=\"{size}\">\n{text}\n</attached_context>"
                    except UnicodeDecodeError:
                        context = f"\n<attached_context path=\"{file_path}\">\n[Binary file - cannot display inline]\n</attached_context>"
            elif p.is_dir():
                # List directory contents (shallow)
                entries = []
                try:
                    for entry in sorted(p.iterdir()):
                        if entry.name.startswith("."):
                            continue
                        kind = "dir" if entry.is_dir() else "file"
                        size_str = ""
                        if entry.is_file():
                            s = entry.stat().st_size
                            size_str = f" ({s} bytes)" if s < 1024 else f" ({s/1024:.1f}KB)"
                        entries.append(f"  {'[DIR] ' if kind == 'dir' else ''}{entry.name}{size_str}")
                except PermissionError:
                    entries.append("  [Permission denied]")

                listing = "\n".join(entries[:80])
                if len(entries) > 80:
                    listing += f"\n  ... ({len(entries) - 80} more entries)"
                context = f"\n<attached_context path=\"{file_path}\" type=\"directory\" entries=\"{len(entries)}\">\n{listing}\n</attached_context>"
            else:
                continue

            # Inject context right after the attachment tag
            tag = f"[Attached file: {file_path}]"
            augmented = augmented.replace(tag, tag + context, 1)
        except Exception as e:
            logger.warning(f"Failed to extract context for {file_path}: {e}")

    return augmented


class Agent:
    # Rough chars-per-token estimate for context budgeting
    CHARS_PER_TOKEN = 3.5
    # Reserve tokens for generation output
    GENERATION_RESERVE = 4096
    # Max context window (conservative estimate for most models)
    MAX_CONTEXT_TOKENS = 28000

    def __init__(self, model_client, config, allow_shell: bool = True):
        """
        model_client: object with a .stream_generate() method
        config: LoadedConfig from CartridgeLoader
        allow_shell: if False, shell/terminal tools are blocked (for network clients)
        """
        self.model_client = model_client
        self.config = config
        self.allow_shell = allow_shell

    def _estimate_tokens(self, text: str) -> int:
        """Token count using actual tokenizer if available, heuristic fallback."""
        try:
            proc = getattr(self.model_client, "processor", None)
            tokenizer = getattr(proc, "tokenizer", None) if proc else None
            if tokenizer and hasattr(tokenizer, "encode"):
                return len(tokenizer.encode(text))
        except Exception:
            pass
        return max(1, int(len(text) / Agent.CHARS_PER_TOKEN))

    def _trim_context(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Trim conversation history to fit within context budget.
        Strategy: Always keep system message + last N messages that fit.
        Dropped messages are summarized using SessionSummarizer for
        structured context preservation.
        """
        budget = self.MAX_CONTEXT_TOKENS - self.GENERATION_RESERVE - self.config.suggested_tokens

        if not messages:
            return messages

        system_msg = messages[0] if messages[0]["role"] == "system" else None
        history = messages[1:] if system_msg else list(messages)

        # First pass: truncate very long tool result messages
        MAX_TOOL_RESULT_CHARS = 3000
        trimmed_history = []
        for msg in history:
            content = msg["content"]
            if msg["role"] == "user" and content.startswith("Tool result for ") and len(content) > MAX_TOOL_RESULT_CHARS:
                content = content[:MAX_TOOL_RESULT_CHARS] + "\n... (output truncated)"
            trimmed_history.append({**msg, "content": content})

        system_cost = self._estimate_tokens(system_msg["content"]) if system_msg else 0
        remaining_budget = budget - system_cost

        if remaining_budget <= 0:
            logger.warning("System prompt alone exceeds context budget")
            remaining_budget = 2000

        # Build from most recent, adding messages until budget exhausted
        selected = []
        used = 0
        for msg in reversed(trimmed_history):
            msg_tokens = self._estimate_tokens(msg["content"])
            if used + msg_tokens > remaining_budget:
                break
            selected.insert(0, msg)
            used += msg_tokens

        dropped_msgs = trimmed_history[:len(trimmed_history) - len(selected)]
        dropped = len(dropped_msgs)
        result = []
        if system_msg:
            result.append(system_msg)
        if dropped > 0 and user_settings.get("context", "use_session_summary"):
            # Use SessionSummarizer for structured context preservation
            cached = prompt_cache.get_summary(dropped_msgs)
            if cached:
                summary_msg = {"role": "system", "content": cached}
            else:
                summary_msg = SessionSummarizer.create_summary_message(
                    dropped_msgs, dropped
                )
                prompt_cache.store_summary(
                    dropped_msgs, summary_msg["content"]
                )
            result.append(summary_msg)
            logger.info(
                f"Context trimmed: dropped {dropped} messages, "
                f"keeping {len(selected)}"
            )
        elif dropped > 0:
            result.append({
                "role": "system",
                "content": f"[{dropped} earlier messages trimmed]"
            })
        result.extend(selected)
        self._trimmed_count = dropped  # Store for SSE notification
        return result
        
    TOOL_DESCRIPTIONS = {
        "get_current_time": {"desc": "Get the current local date and time.", "params": {}},
        "list_directory": {"desc": "List directory contents with file sizes.", "params": {"path": "Directory path (default: '.')"}},
        "get_system_info": {"desc": "Get system overview: OS, hardware, disk, uptime.", "params": {}},
        "search_files": {"desc": "Search for files matching a glob pattern (max 50 results).", "params": {"pattern": "Glob pattern to match", "directory": "Directory to search (default: '~')"}},
        "read_file": {"desc": "Read a text file. Files under 50KB are shown in full (up to 200 lines). Files over 50KB automatically return a structural overview: imports, function/class signatures with line numbers, exports, plus the first 20 and last 10 lines. Max 500KB.", "params": {"path": "File path to read", "max_lines": "Max lines to read (default: 100, only for files under 50KB)"}},
        "run_command": {"desc": "Run shell commands (30s timeout). Supports pipes (|), chaining (&&, ;). Most commands work. Destructive commands (rm, sudo) are blocked. Process management (kill, killall, pkill) and write operations (mkdir, cp, mv, chmod, pip install, git commit, etc.) require user consent — you'll get a CONSENT_REQUIRED response for those.", "params": {"command": "Shell command to run"}},
        "calculate": {"desc": "Evaluate a math expression safely. Supports sqrt, log, trig, factorial, pi, e.", "params": {"expression": "Math expression to evaluate"}},
        "execute_python": {"desc": "Execute Python code in a stateful sandbox. Captures stdout/stderr. Matplotlib plots are AUTO-CAPTURED as images — do NOT call plt.show(). Variables persist across calls. Pre-imported: pandas (pd), numpy (np), matplotlib.pyplot (plt), scipy (+ scipy.stats), seaborn (sns), math, json, csv, re, PIL/PILImage, sklearn (model_selection, preprocessing, metrics, ensemble, linear_model, cluster, decomposition), torch, torchvision. Quick chart helpers: qchart_bar, qchart_pie, qchart_line, qchart_scatter, qchart_hist, qchart_heatmap. Image editing helpers (for Image Editor cartridge): img_load, img_save, img_show, img_adjust, img_hue_shift, img_color_replace, img_color_range_replace, img_tint, img_adjust_highlights, img_adjust_shadows, img_overlay_color, img_get_original, img_crop, img_resize, img_rotate, img_flip, img_blur, img_grayscale, img_edge_detect, img_threshold, img_draw_rect, img_draw_text, img_convert, img_info. If a package is missing, you'll get MISSING_PACKAGE — ask the user for consent to install it before retrying.", "params": {"code": "Python code to execute"}},
        "execute_cpp": {"desc": "Compile and run C++ code (C++17, g++/clang++). Returns compilation errors or program output.", "params": {"code": "C++ source code", "stdin_input": "(optional) stdin input for the program"}},
        "search_web": {"desc": "Search the web using DuckDuckGo. Returns titles, URLs, and snippets for top results.", "params": {"query": "Search query", "max_results": "Number of results (default: 5)"}},
        "read_url": {"desc": "Fetch and extract readable text content from a webpage URL. Content is preprocessed: ads, navs, sidebars, and boilerplate are stripped. Returns clean markdown.", "params": {"url": "Full URL to fetch (include https://)"}},
        "read_rss": {"desc": "Read and parse an RSS or Atom feed. Returns structured entries with title, date, link, and summary.", "params": {"url": "RSS/Atom feed URL", "max_items": "Max entries to return (default: 10)"}},
        "get_location": {"desc": "Get approximate location from IP geolocation: city, region, country, timezone, coordinates.", "params": {}},
    }

    def _build_system_message(self) -> Dict[str, str]:
        # Build detailed tool descriptions for the model
        # Merge built-in descriptions with dynamically loaded plugin descriptions
        all_descriptions = dict(self.TOOL_DESCRIPTIONS)
        all_descriptions.update(plugin_loader.get_tool_descriptions())

        tool_lines = []
        for t in self.config.tools:
            info = all_descriptions.get(t, {"desc": t, "params": {}})
            params_str = ", ".join(f'{k}: {v}' for k, v in info["params"].items())
            tool_lines.append(f"- **{t}**({params_str}): {info['desc']}")
        
        tool_id_list = ", ".join(f"`{t}`" for t in self.config.tools)
        tools_block = (
            "\n\n## Available Tools\n"
            "Call tools using this EXACT format — one tool call per message:\n\n"
            '```\n<tool_call>{"name": "tool_name", "arguments": {"param": "value"}}</tool_call>\n```\n\n'
            "### Tool Call Rules (CRITICAL)\n"
            f"**You may ONLY call tools from this exact list: {tool_id_list}.** "
            "Any tool not in this list DOES NOT EXIST. Do NOT invent tool names, do NOT guess tool names from your training data. "
            "If a tool you want is not listed, use an alternative from the list above or answer without tools.\n\n"
            "1. The JSON inside `<tool_call>` must be valid. For `code` arguments with multi-line code, use `\\n` for newlines and `\\\"` for quotes inside strings.\n"
            '2. Call **ONE tool at a time**. After the `</tool_call>` tag, STOP generating — do not write any more text. Wait for the tool result.\n'
            "3. Do NOT put ANY text after the `</tool_call>` closing tag. Not even a period.\n"
            "4. Do NOT wrap tool calls in markdown code fences — just use the raw `<tool_call>` XML tags.\n"
            "5. When a tool returns an image/plot, the user can already see it. Do NOT describe or recreate it — focus on insights.\n"
            "6. Do NOT place `<tool_call>` inside `<think>` blocks. Finish thinking first, then output the tool call.\n\n"
            "### Code Tool Rules (execute_python)\n"
            "- **Keep code SHORT** — under 40 lines. Long code will be truncated. Break complex tasks into multiple smaller calls.\n"
            "- **NumPy images are (H, W, C)** — height × width × channels. To modify the red channel: `img[:, :, 0]`, NOT `img[0]`.\n"
            "- **Use PIL/Pillow built-ins** for image operations: `ImageEnhance`, `ImageFilter`, `Image.convert('HSV')`. Do NOT manually implement HSV conversion.\n"
            "- **Matplotlib plots are auto-captured** — do NOT call `plt.show()` or `plt.savefig()`.\n"
            "- **If code fails, fix only the error** — do NOT rewrite the entire script. Make a minimal targeted edit.\n"
            "- **Never repeat the same code** — if code failed twice, try a fundamentally different approach or give up and explain.\n\n"
            "### Agentic Behavior\n"
            "You are an autonomous agent that can chain multiple tool calls to accomplish complex tasks. "
            "For multi-step tasks, think through your plan first:\n"
            "1. **Plan** — decide what information you need and which tools to use.\n"
            "2. **Act** — call the first tool.\n"
            "3. **Observe** — analyze the result. Decide if you need another tool call or can answer.\n"
            "4. **Adapt** — if a tool fails, read the error carefully. Try a DIFFERENT approach, not the same one.\n"
            "5. **Synthesize** — once you have enough data, give a clear final answer and STOP.\n\n"
            "**Error recovery**: If a tool is not available, immediately switch to an available alternative. "
            "If code fails twice with the same error, stop and explain the issue to the user instead of retrying.\n\n"
            "### Tool Selection Guide\n"
            "- **Math**: Use `calculate` for simple arithmetic. Use `execute_python` for anything complex.\n"
            "- **Files**: Always `read_file` before editing. Use `list_directory` to explore first.\n"
            "- **Search**: Prefer `search_files` over `run_command find`. Use `search_web` for factual lookups.\n"
            "- **Shell**: Use `run_command` only when no specialized tool fits.\n"
            "- **Web**: Use `read_url` to fetch content. Use `search_web` first if you don't have a URL.\n"
            "- **Images**: If the user attaches an image and you can see it, describe what you see directly. Use `execute_python` with PIL for editing.\n\n"
            + "\n".join(tool_lines)
        )
        
        # Inject user memory if available
        memory_block = user_memory.get_context_block()

        # Inject cartridge context if enabled
        cartridge_block = ""
        if user_settings.get("context", "use_cartridge_context"):
            cid = self.config.active_cartridge_ids[0] if self.config.active_cartridge_ids else None
            if cid:
                cartridge_block = CartridgeContext.get_context_block(cid)

        # Inject global profile if enabled
        global_block = ""
        if user_settings.get("context", "use_global_profile"):
            global_block = GlobalProfile.get_context_block()

        return {
            "role": "system",
            "content": (
                self.config.merged_prompt
                + tools_block
                + memory_block
                + cartridge_block
                + global_block
            ),
        }

    def chat_stream(
        self, 
        history: List[Dict[str, str]], 
        image_path: str = None
    ) -> Generator[str, None, None]:
        """
        Executes a turn of conversation with multi-step tool loop.
        Yields JSON strings containing SSE events: { "type": "...", "data": ... }
        """
        # Pre-process attachments in the last user message for intelligent context extraction
        processed_history = list(history)
        if processed_history and processed_history[-1].get("role") == "user":
            last_msg = processed_history[-1]
            if "[Attached file:" in last_msg["content"]:
                augmented = _extract_attachment_context(last_msg["content"])
                processed_history[-1] = {**last_msg, "content": augmented}
        
        base_history = [self._build_system_message()] + processed_history
        
        # Trim context to fit within budget
        base_history = self._trim_context(base_history)
        
        # Emit context info for frontend
        total_chars = sum(len(m["content"]) for m in base_history)
        est_tokens = self._estimate_tokens(" ".join(m["content"] for m in base_history))
        yield json.dumps({
            "type": "context_info",
            "data": {
                "message_count": len(history),
                "estimated_tokens": est_tokens,
                "max_tokens": self.MAX_CONTEXT_TOKENS,
            }
        })
        
        # Notify frontend if context was trimmed
        trimmed = getattr(self, '_trimmed_count', 0)
        if trimmed > 0:
            yield json.dumps({
                "type": "context_trimmed",
                "data": {"dropped_messages": trimmed}
            })
        
        # Max rounds of tool calling — configurable per cartridge
        MAX_TOOL_ROUNDS = getattr(self.config, 'suggested_max_rounds', 6)
        MAX_PARSE_RETRIES = 2
        consecutive_failures = 0
        session_errors: List[str] = []  # Track errors to prevent repeats
        _prev_code_hashes: List[str] = []  # Track code hashes to detect identical re-submissions
        
        current_history = list(base_history)
        
        # Inject current working image context for multi-turn image editing
        _cimg = _sandbox_globals.get('_current_image_path')
        if _cimg and Path(_cimg).exists():
            # Find last user message and append image context
            for i in range(len(current_history) - 1, -1, -1):
                if current_history[i].get('role') == 'user':
                    current_history[i] = {
                        **current_history[i],
                        'content': current_history[i]['content'] + (
                            f"\n[SYSTEM: The current working image from a previous edit is saved at: {_cimg}. "
                            f"Use `img = img_load('{_cimg}')` or the persisted variable `_current_image` to continue editing. "
                            f"Python variables from previous tool calls persist across executions.]"
                        )
                    }
                    break
        
        for tool_round in range(MAX_TOOL_ROUNDS):
            # ── 1. Stream Model Generation ──
            accumulated = ""
            thinking_done = False
            is_retry_gen = False  # set True during parse-retry re-generations
            yield json.dumps({"type": "status", "data": "Generating..."})
            
            # Retry wrapper: one automatic retry on transient inference failures
            def _stream_with_retry():
                try:
                    yield from self.model_client.stream_generate(
                        messages=current_history,
                        image=image_path if tool_round == 0 else None,
                        max_tokens=self.config.suggested_tokens,
                        thinking=self.config.suggested_thinking
                    )
                except Exception as inf_err:
                    logger.warning(f"Inference failed (attempt 1): {inf_err}, retrying...")
                    import gc; gc.collect()
                    yield from self.model_client.stream_generate(
                        messages=current_history,
                        image=image_path if tool_round == 0 else None,
                        max_tokens=self.config.suggested_tokens,
                        thinking=self.config.suggested_thinking
                    )

            for chunk in _stream_with_retry():
                accumulated += chunk
                
                # Check for thinking completion to stream actual content
                if "</think>" in accumulated:
                    if not thinking_done:
                        thinking_done = True
                        yield json.dumps({"type": "think_end"})
                    
                    _, answer = parse_thinking(accumulated)
                    if answer.strip():
                        yield json.dumps({"type": "token", "data": chunk})
                elif self.config.suggested_thinking:
                    content = accumulated
                    if "<think>" in content:
                        content = content[content.index("<think>") + len("<think>"):]
                    if content.strip():
                        yield json.dumps({"type": "think_token", "data": chunk})
                else:
                    yield json.dumps({"type": "token", "data": chunk})

            # ── 2. Process complete generation ──
            thought, text = parse_thinking(accumulated)
            
            # If model placed a tool call INSIDE the think block, extract it
            if thought and not extract_tool_call(text):
                think_tool = extract_tool_call(thought)
                if think_tool:
                    logger.info("Found tool call inside <think> block — extracting it")
                    # Reconstruct text with the tool call so it gets processed normally
                    text = f'<tool_call>{json.dumps(think_tool)}</tool_call>'
            
            # Strip leading JSON fragments leaked from think blocks (e.g. '"}> properly.')
            text = re.sub(r'^["\s\}>\.\,]+(?:\s+\w{0,20}\.?)?\s*\n', '', text)
            
            # Strip leading echo fragments from previous round (e.g. "code.", "intuitive.")
            if tool_round > 0 and text:
                frag_match = re.match(r'^(\S[^.\n]{0,28}\.)\s*\n\n', text)
                if frag_match:
                    text = text[frag_match.end():]
            
            # ── 2a. Detect output limit truncation and auto-continue ──
            _truncated = False
            _truncated_tool_call = False
            if '<tool_call>' in text and '</tool_call>' not in text:
                _truncated = True
                _truncated_tool_call = True
            elif text.count('```') % 2 != 0:
                _truncated = True
            
            if _truncated and tool_round < MAX_TOOL_ROUNDS - 1:
                logger.info(f"Detected truncated output (round {tool_round}, tool_call={_truncated_tool_call})")
                if _truncated_tool_call:
                    # Tool call was truncated — do NOT auto-continue (causes infinite loops)
                    # Instead, strip the partial tool call and ask model to write shorter code
                    yield json.dumps({"type": "status", "data": "Code was too long — requesting shorter version…"})
                    clean_text = re.sub(r'<tool_call>[\s\S]*$', '', text, flags=re.IGNORECASE).strip()
                    current_history.append({"role": "assistant", "content": clean_text or "(attempted tool call)"})
                    current_history.append({"role": "user", "content": (
                        "[SYSTEM] Your tool call was truncated because the code was too long. "
                        "You MUST write much shorter code — under 30 lines. Strategies:\n"
                        "1. Break the task into smaller steps across multiple tool calls.\n"
                        "2. Use built-in library functions instead of manual implementations.\n"
                        "3. Remove comments and combine simple lines.\n"
                        "Do NOT repeat the same long code. Write a SHORTER version now."
                    )})
                    continue
                else:
                    yield json.dumps({"type": "status", "data": "Continuing response…"})
                    current_history.append({"role": "assistant", "content": accumulated})
                    current_history.append({"role": "user", "content": "Your previous response was cut off mid-way due to output length limits. Continue EXACTLY from where you stopped. Do NOT repeat any content already written."})
                    continue

            tool_req = extract_tool_call(text)

            # ── 2b. Auto-retry on tool call parse failure ──
            if not tool_req and _has_tool_call_attempt(text):
                for retry in range(MAX_PARSE_RETRIES):
                    logger.warning(f"Tool call parse failure (retry {retry + 1}/{MAX_PARSE_RETRIES})")
                    yield json.dumps({
                        "type": "status",
                        "data": f"Tool call format error — auto-correcting ({retry + 1}/{MAX_PARSE_RETRIES})…"
                    })
                    
                    # Inject diagnostic feedback so the model can self-correct
                    error_feedback = _diagnose_tool_call_error(text)
                    # Clean the failed attempt from text before adding to history
                    failed_text = re.sub(r'<tool_call>[\s\S]*', '', text, flags=re.IGNORECASE).strip()
                    current_history.append({"role": "assistant", "content": failed_text or "(attempted tool call)"})
                    current_history.append({"role": "user", "content": error_feedback})
                    
                    # Re-generate with thinking visible to user
                    accumulated = ""
                    thinking_done = False
                    for chunk in self.model_client.stream_generate(
                        messages=current_history,
                        max_tokens=self.config.suggested_tokens,
                        thinking=self.config.suggested_thinking
                    ):
                        accumulated += chunk
                        if "</think>" in accumulated:
                            if not thinking_done:
                                thinking_done = True
                                yield json.dumps({"type": "think_end"})
                            _, answer = parse_thinking(accumulated)
                            if answer.strip():
                                yield json.dumps({"type": "token", "data": chunk})
                        elif self.config.suggested_thinking:
                            c = accumulated
                            if "<think>" in c:
                                c = c[c.index("<think>") + len("<think>"):]
                            if c.strip():
                                yield json.dumps({"type": "think_token", "data": chunk})
                        else:
                            yield json.dumps({"type": "token", "data": chunk})
                    
                    _, text = parse_thinking(accumulated)
                    tool_req = extract_tool_call(text)
                    if tool_req:
                        logger.info(f"Tool call parse succeeded on retry {retry + 1}")
                        break
                else:
                    logger.warning("All parse retries exhausted — treating as final answer")

            # ── 2c. Final answer (no tool call) ──
            if not tool_req:
                clean_text = re.sub(r'<tool_call>[\s\S]*?</tool_call>', '', text, flags=re.IGNORECASE)
                clean_text = re.sub(r'<tool_call>[\s\S]*$', '', clean_text, flags=re.IGNORECASE)
                clean_text = re.sub(r'<\|tool_call\|>[\s\S]*$', '', clean_text)
                clean_text = clean_text.strip()
                if not clean_text and text.strip():
                    clean_text = text.strip()
                yield json.dumps({"type": "done", "data": clean_text})
                break
                
            # ── 3. Tool Execution Phase ──
            tool_name = tool_req.get("name", "")
            tool_args = tool_req.get("arguments", {})
            
            # Detect identical code re-submissions (loop detection)
            if tool_name in ("execute_python", "execute_cpp") and "code" in tool_args:
                code_hash = hashlib.md5(tool_args["code"].encode()).hexdigest()
                if code_hash in _prev_code_hashes:
                    logger.warning(f"Identical code re-submission detected (hash={code_hash[:8]}), forcing stop")
                    yield json.dumps({"type": "status", "data": "Detected repeated code — stopping loop."})
                    current_history.append({"role": "assistant", "content": "(repeated identical code)"})
                    current_history.append({"role": "user", "content": (
                        "[SYSTEM] You just submitted the EXACT SAME code again. This is a loop. "
                        "STOP calling tools. Either explain what you're trying to do and what's failing, "
                        "or try a completely different approach with much simpler code."
                    )})
                    consecutive_failures = max(consecutive_failures, 3)
                    continue
                _prev_code_hashes.append(code_hash)
            
            start_data = {"name": tool_name, "args": tool_args}
            if tool_name in ("execute_python", "execute_cpp") and "code" in tool_args:
                start_data["code"] = tool_args["code"]
            
            yield json.dumps({"type": "tool_start", "data": start_data})
            
            # Block dangerous tools for network (non-local) clients
            SHELL_TOOLS = {"run_command", "execute_python", "execute_cpp"}
            if not self.allow_shell and tool_name in SHELL_TOOLS:
                tool_result = "Error: Shell/code execution is disabled for network clients. Only the local machine can run commands."
                sandbox_images = []
                html_artifact = ""
            elif tool_name not in self.config.tools:
                available = ", ".join(self.config.tools)
                tool_result = (
                    f"Error: Tool '{tool_name}' does not exist. "
                    f"The ONLY tools you can use are: {available}. "
                    f"Pick one of these tools instead. Do NOT retry '{tool_name}'."
                )
                sandbox_images = []
                html_artifact = ""
            else:
                try:
                    raw_result = execute_tool(tool_name, tool_args)
                    if isinstance(raw_result, dict):
                        tool_result = raw_result.get("output", "")
                        sandbox_images = raw_result.get("images", [])
                        html_artifact = raw_result.get("html", "")
                    else:
                        tool_result = str(raw_result)
                        sandbox_images = []
                        html_artifact = ""
                except Exception as tool_err:
                    logger.error(f"Tool '{tool_name}' crashed: {tool_err}")
                    tool_result = f"Error: Tool '{tool_name}' failed unexpectedly: {str(tool_err)[:200]}"
                    sandbox_images = []
                    html_artifact = ""

            # ── Consent flow: pause stream and wait for user approval ──
            if isinstance(tool_result, str) and "[CONSENT_REQUIRED]" in tool_result:
                cmd_match = re.search(r'`([^`]+)`', tool_result)
                cmd = cmd_match.group(1) if cmd_match else tool_args.get("command", "")
                consent_id = str(uuid.uuid4())
                event = _register_consent(consent_id)
                yield json.dumps({"type": "consent_required", "data": {
                    "id": consent_id, "command": cmd, "tool": tool_name
                }})
                event.wait(timeout=120)
                state = _pop_consent(consent_id)
                if state.get("approved"):
                    approved_result = run_approved_command(cmd)
                    tool_result = str(approved_result) if not isinstance(approved_result, dict) else approved_result.get("output", str(approved_result))
                    sandbox_images = approved_result.get("images", []) if isinstance(approved_result, dict) else []
                    html_artifact = approved_result.get("html", "") if isinstance(approved_result, dict) else ""
                else:
                    tool_result = "Command denied by user. Do NOT retry this command. Adjust your plan accordingly."

            result_data = {"name": tool_name, "result": tool_result, "images": sandbox_images}
            if html_artifact:
                result_data["html"] = html_artifact
            yield json.dumps({"type": "tool_result", "data": result_data})
            
            # ── 4. Build enriched context for next round ──
            is_failure = tool_result in ("(no output)", "") or str(tool_result).startswith("Error:") or "Traceback" in str(tool_result)
            consecutive_failures = consecutive_failures + 1 if is_failure else 0

            # Loop detection: if the model retries the exact same tool+args, force stop sooner
            call_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)[:200]}"
            if is_failure and call_sig in session_errors:
                consecutive_failures = max(consecutive_failures, 3)  # Immediate escalation for repeated identical failures

            if consecutive_failures >= 3:
                yield json.dumps({"type": "status", "data": "Multiple tools failed. Generating final response…"})
                failure_note = "\nIMPORTANT: Multiple tools have failed. Stop calling tools and give your best final answer with whatever data you have."
            else:
                failure_note = ""
            
            # Use enriched error context for tool failures
            if is_failure and not failure_note:
                result_context = _enrich_tool_error(tool_name, tool_args, tool_result)
            else:
                result_context = f"Tool result for {tool_name}: {tool_result}"
            if sandbox_images:
                _saved = _sandbox_globals.get('_current_image_path', '')
                result_context += f"\n[{len(sandbox_images)} image(s) were generated and displayed to the user. Do NOT recreate or describe them — the user can already see them."
                if _saved:
                    result_context += f" The edited image is auto-saved at: {_saved}. For further edits, use `img = img_load('{_saved}')` or the persisted variable `_current_image`."
                result_context += " Your task is likely complete. Provide a brief summary and STOP calling tools.]"
            if html_artifact:
                result_context += "\n[An interactive visualization was generated and displayed. Your task is likely complete. Summarize and STOP calling tools.]"
            if tool_name == "execute_python" and "Traceback" in str(tool_result):
                result_context += "\n[IMPORTANT: Fix ONLY the specific error in your code — do NOT rewrite from scratch. Make a minimal targeted edit to the failing line(s).]"
            # Inject round counter so model knows budget
            result_context += f"\n[Tool round {tool_round + 1}/{MAX_TOOL_ROUNDS}]"
            # Inject error history to prevent repeats
            if is_failure:
                err_summary = f"{tool_name}({json.dumps(tool_args)[:80]}): {str(tool_result)[:120]}"
                session_errors.append(err_summary)
                session_errors.append(call_sig)  # Store call signature for loop detection
            if session_errors:
                result_context += f"\n[Previous errors in this session — do NOT repeat these: {'; '.join(session_errors[-3:])}]"
            result_context += failure_note
                
            # Append interaction to history — strip <tool_call> XML from assistant text
            history_text = re.sub(r'<tool_call>[\s\S]*?</tool_call>', '', text, flags=re.IGNORECASE)
            history_text = re.sub(r'<tool_call>[\s\S]*$', '', history_text, flags=re.IGNORECASE)
            history_text = re.sub(r'<\|tool_call\|>[\s\S]*$', '', history_text)
            history_text = history_text.strip()
            current_history.append({"role": "assistant", "content": history_text or "[Calling tool...]"})
            current_history.append({"role": "user", "content": result_context})
            
            if consecutive_failures >= 3:
                final_res = self.model_client.generate(current_history, max_tokens=self.config.suggested_tokens, thinking=False)
                _, final_text = parse_thinking(final_res)
                yield json.dumps({"type": "token", "data": final_text})
                yield json.dumps({"type": "done", "data": final_text})
                break
        else:
            # Hit max rounds — produce a final summary
            current_history.append({"role": "user", "content": "You have reached the maximum number of tool rounds. Summarize your findings and give your best final answer with the information gathered so far."})
            final_res = self.model_client.generate(current_history, max_tokens=self.config.suggested_tokens, thinking=False)
            _, final_text = parse_thinking(final_res)
            yield json.dumps({"type": "token", "data": final_text})
            yield json.dumps({"type": "done", "data": final_text})
        
        # Post-conversation: extract memories & update context in background thread
        def _post_conversation_tasks():
            try:
                extracted = user_memory.extract_memories_from_conversation(history)
                for mem_type, mem_content in extracted:
                    user_memory.add(mem_content, memory_type=mem_type, source="auto")
                if extracted:
                    logger.info(f"Extracted {len(extracted)} memories from conversation (async)")
            except Exception as e:
                logger.warning(f"Memory extraction failed: {e}")

            try:
                cid = self.config.active_cartridge_ids[0] if self.config.active_cartridge_ids else None
                if cid:
                    title = ""
                    for msg in history:
                        if msg.get("role") == "user":
                            t = msg["content"].strip()
                            if not t.startswith("[Attached file:") and not t.startswith("Tool result"):
                                title = t[:60]
                                break
                    CartridgeContext.update_from_chat(cid, history, chat_title=title)
                    GlobalProfile.update_from_chat(cid, history)
            except Exception as e:
                logger.warning(f"Context update failed: {e}")

        threading.Thread(target=_post_conversation_tasks, daemon=True).start()

        # Cleanup temp image files created during inference
        self.model_client.cleanup_temp_files()
