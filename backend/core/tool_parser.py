"""
tool_parser.py — Tool call extraction, parsing, and error diagnosis.

Extracted from agent.py for modularity. Handles multiple XML/JSON formats
that models produce, with robust fallback parsing for malformed output.
"""

import json
import logging
import re
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


def parse_thinking(raw: str) -> Tuple[str, str]:
    """Extract thinking content from model output.
    Returns (thinking_text, answer_text)."""
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
                for attempt in (candidate, _fix_json_newlines(candidate)):
                    try:
                        obj = json.loads(attempt)
                        if isinstance(obj, dict) and "name" in obj:
                            return obj
                    except json.JSONDecodeError:
                        pass
                start = None

    # Dedicated extraction for execute_python / execute_cpp — the most common failure
    name_match = re.search(r'"name"\s*:\s*"(\w+)"', raw)
    if name_match:
        tool_name = name_match.group(1)
        if tool_name in ("execute_python", "execute_cpp"):
            code_match = re.search(r'"code"\s*:\s*"', raw)
            if code_match:
                code_start = code_match.end()
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
                code_value = code_value.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
                logger.info(f"Extracted code for {tool_name} ({len(code_value)} chars) via direct scan")
                return {"name": tool_name, "arguments": {"code": code_value}}

        # For other tools, try regex extraction of arguments
        args_match = re.search(r'"arguments"\s*:\s*\{', raw)
        if args_match:
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


def has_tool_call_attempt(text: str) -> bool:
    """Check if the model attempted a tool call but it failed to parse."""
    lower = text.lower()
    return '<tool_call>' in lower or '<|tool_call|>' in lower


def diagnose_tool_call_error(text: str) -> str:
    """Analyze a failed tool call and produce a clear error message for the model."""
    match = re.search(r'<tool_call>\s*(.*?)(?:</tool_call>|$)', text, re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(r'<\|tool_call\|>\s*(.*?)(?:<\|/tool_call\|>|$)', text, re.DOTALL)

    raw_json = match.group(1).strip() if match else ""
    snippet = raw_json[:300] if raw_json else text[-300:]

    issues = []
    if raw_json:
        brace_count = raw_json.count('{') - raw_json.count('}')
        if brace_count > 0:
            issues.append(f"Unclosed braces: {brace_count} opening '{{' without matching '}}'.")
        elif brace_count < 0:
            issues.append(f"Extra closing braces: {abs(brace_count)} unmatched '}}'.")

        if '"code"' in raw_json:
            code_start = raw_json.find('"code"')
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


def enrich_tool_error(tool_name: str, tool_args: dict, error_result: str) -> str:
    """Produce actionable feedback when a tool execution fails."""
    hints = []
    err = error_result.lower()
    err_raw = error_result

    if "no such file" in err or "does not exist" in err or "filenotfounderror" in err:
        path_hint = tool_args.get("path", tool_args.get("directory", ""))
        hints.append("The file/path doesn't exist. Use `list_directory` or `search_files` to verify the correct path first.")
        if path_hint:
            from pathlib import PurePosixPath
            parent = str(PurePosixPath(path_hint).parent)
            hints.append(f"Try: list_directory(\"{parent}\") to see what exists.")
    elif "permission" in err and "denied" in err:
        hints.append("Permission denied. The sandbox cannot access this path. Try a different location or use ~/.")
    elif "isadirectoryerror" in err:
        hints.append("You tried to read a directory as a file. Use `list_directory` instead of `read_file`.")
    elif "notadirectoryerror" in err:
        hints.append("You tried to list a file as a directory. Use `read_file` instead of `list_directory`.")
    elif "syntaxerror" in err or "indentationerror" in err:
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
        hints.append("Type mismatch. Check function argument types and return values.")
    elif "keyerror" in err:
        key_match = re.search(r"KeyError:\s*['\"]?(\w+)", err_raw)
        key_info = f" Key `{key_match.group(1)}` not found." if key_match else ""
        hints.append(f"Dictionary key not found.{key_info} Use `.get()` for safe access or check available keys with `.keys()`.")
    elif "indexerror" in err:
        hints.append("List index out of range. Check the length of your list/array before indexing.")
    elif "valueerror" in err:
        prop_match = re.search(r"Invalid property specified for object of type ['\"]?[\w.]+['\"]?:\s*['\"](\w+)['\"]", err_raw)
        if prop_match:
            bad_prop = prop_match.group(1)
            hints.append(f"Property `{bad_prop}` does NOT exist on this Plotly object. REMOVE it entirely.")
        else:
            hints.append("Invalid value. Check that input data is in the expected format.")
    elif "attributeerror" in err:
        attr_match = re.search(r"has no attribute '(\w+)'", err_raw)
        if attr_match:
            hints.append(f"Object has no attribute `{attr_match.group(1)}`. Check the object type with `type()` and use `dir()` to see available attributes.")
        else:
            hints.append("Attribute error. Verify the object type and available methods.")
    elif "modulenotfounderror" in err or "no module named" in err:
        mod_match = re.search(r"No module named ['\"](\w+)", err_raw)
        mod_name = mod_match.group(1) if mod_match else "the module"
        hints.append(f"Module `{mod_name}` is not installed. Pre-available: pandas, numpy, matplotlib, scipy, seaborn, plotly, Pillow, sympy.")
    elif "zerodivisionerror" in err:
        hints.append("Division by zero. Add a check before dividing.")
    elif "timed out" in err:
        hints.append("Command timed out (30s limit). Simplify the operation or break into smaller steps.")
    elif "blocked" in err:
        hints.append("This command is blocked for safety. Use an alternative approach.")
    elif "consent_required" in err:
        hints.append("This command needs user approval. Wait for the consent prompt.")
    elif "command not found" in err:
        cmd_match = re.search(r"(\w+): command not found", err_raw)
        if cmd_match:
            hints.append(f"`{cmd_match.group(1)}` is not installed. Try an alternative tool or approach.")
    elif "exit" in err and re.search(r'exit (\d+)', err):
        exit_match = re.search(r'exit (\d+)', err)
        hints.append(f"Command exited with code {exit_match.group(1)}. Check stderr output above for details.")
    elif "traceback" in err and not hints:
        hints.append("An exception occurred. Read the traceback carefully and fix only the failing line(s).")

    base = f"Tool result for {tool_name}: {error_result}"
    if hints:
        base += "\n[Diagnosis: " + " ".join(hints) + "]"
    return base
