import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Generator, Tuple, Optional
from .tool_registry import execute_tool
from .plugin_loader import plugin_loader
from .persistence import user_memory, prompt_cache, chat_store
from .context_manager import (
    user_settings, SessionSummarizer, CartridgeContext, GlobalProfile
)

logger = logging.getLogger(__name__)

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
    """Produce actionable feedback when a tool execution fails."""
    hints = []
    err = error_result.lower()

    if "no such file" in err or "does not exist" in err:
        hints.append("The file/path doesn't exist. Use `list_directory` or `search_files` to find the correct path first.")
    elif "permission denied" in err:
        hints.append("Permission denied. Try a different path or approach.")
    elif "timed out" in err:
        hints.append("The command took too long (30s limit). Simplify the operation or break it into smaller steps.")
    elif "syntax" in err or "indentation" in err:
        hints.append("There's a syntax error in the code. Review and fix it before retrying.")
    elif "modulenotfounderror" in err or "import" in err:
        hints.append("A required module is not available. Use only pre-imported packages (pandas, numpy, matplotlib, scipy, seaborn) or ask the user to install it.")
    elif "blocked" in err:
        hints.append("This command is blocked for safety. Try an alternative approach.")
    elif "consent_required" in err:
        hints.append("This command needs user approval. The user will see a prompt to approve it.")

    base = f"Tool result for {tool_name}: {error_result}"
    if hints:
        base += "\n[Hint: " + " ".join(hints) + "]"
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

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token count estimate from character length."""
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
        return result
        
    TOOL_DESCRIPTIONS = {
        "get_current_time": {"desc": "Get the current local date and time.", "params": {}},
        "list_directory": {"desc": "List directory contents with file sizes.", "params": {"path": "Directory path (default: '.')"}},
        "get_system_info": {"desc": "Get system overview: OS, hardware, disk, uptime.", "params": {}},
        "search_files": {"desc": "Search for files matching a glob pattern (max 50 results).", "params": {"pattern": "Glob pattern to match", "directory": "Directory to search (default: '~')"}},
        "read_file": {"desc": "Read a text file (max 200 lines / 50KB).", "params": {"path": "File path to read", "max_lines": "Max lines to read (default: 100)"}},
        "run_command": {"desc": "Run shell commands (30s timeout). Supports pipes (|), chaining (&&, ;). Most commands work. Destructive commands (rm, sudo, kill) are blocked. Write operations (mkdir, cp, mv, chmod, pip install, git commit, etc.) require user consent — you'll get a CONSENT_REQUIRED response for those.", "params": {"command": "Shell command to run"}},
        "calculate": {"desc": "Evaluate a math expression safely. Supports sqrt, log, trig, factorial, pi, e.", "params": {"expression": "Math expression to evaluate"}},
        "execute_python": {"desc": "Execute Python code in a stateful sandbox. Captures stdout/stderr. Matplotlib plots are AUTO-CAPTURED as images — do NOT call plt.show(). Variables persist across calls. Pre-imported: pandas (pd), numpy (np), matplotlib.pyplot (plt), scipy (+ scipy.stats), seaborn (sns), math, json, csv, re, PIL/PILImage, sklearn (model_selection, preprocessing, metrics, ensemble, linear_model, cluster, decomposition), torch, torchvision. Quick chart helpers: qchart_bar(labels, values, title), qchart_pie(labels, values, title), qchart_line(x, y_series, labels, title), qchart_scatter(x, y, title), qchart_hist(data, bins, title), qchart_heatmap(data, xlabels, ylabels, title). If a package is missing, you'll get MISSING_PACKAGE — ask the user for consent to install it before retrying.", "params": {"code": "Python code to execute"}},
        "execute_cpp": {"desc": "Compile and run C++ code (C++17, g++/clang++). Returns compilation errors or program output.", "params": {"code": "C++ source code", "stdin_input": "(optional) stdin input for the program"}},
        "search_web": {"desc": "Search the web using DuckDuckGo. Returns titles, URLs, and snippets for top results.", "params": {"query": "Search query", "max_results": "Number of results (default: 5)"}},
        "read_url": {"desc": "Fetch and extract readable text content from a webpage URL. Returns markdown-formatted content.", "params": {"url": "Full URL to fetch (include https://)"}},
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
        
        tools_block = (
            "\n\n## Available Tools\n"
            "Call tools using this EXACT format — one tool call per message:\n\n"
            '```\n<tool_call>{"name": "tool_name", "arguments": {"param": "value"}}</tool_call>\n```\n\n'
            "### Tool Call Rules (CRITICAL)\n"
            "1. The JSON inside `<tool_call>` must be valid. For `code` arguments with multi-line code, use `\\n` for newlines and `\\\"` for quotes inside strings.\n"
            '2. Call **ONE tool at a time**. After the `</tool_call>` tag, STOP generating text. Wait for the tool result before continuing.\n'
            "3. Do NOT put any text after the `</tool_call>` closing tag.\n"
            "4. Do NOT wrap tool calls in markdown code fences — just use the raw `<tool_call>` XML tags.\n"
            "5. When a tool returns an image/plot, the user can already see it. Do NOT describe or recreate it — focus on insights.\n\n"
            "### Agentic Behavior\n"
            "You are an autonomous agent that can chain multiple tool calls to accomplish complex tasks. "
            "For multi-step tasks, think through your plan in your reasoning before acting:\n"
            "1. **Plan** — decide what information you need and which tools to use in what order.\n"
            "2. **Act** — call the first tool. You will automatically get the result and can continue.\n"
            "3. **Observe** — analyze the result. Decide if you need another tool call or can answer.\n"
            "4. **Adapt** — if a tool fails, read the error carefully, adjust your approach, and retry with a corrected call.\n"
            "5. **Synthesize** — once you have all the data, give a clear final answer.\n\n"
            "You can use up to 10 tool calls per response. Do NOT ask the user to do things you can do with tools — "
            "just do them. If you need to read a file, list a directory, run code, or search the web, call the tool directly.\n\n"
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
        
        # Max rounds of tool calling
        MAX_TOOL_ROUNDS = 10
        MAX_PARSE_RETRIES = 2
        consecutive_failures = 0
        
        current_history = list(base_history)
        
        for tool_round in range(MAX_TOOL_ROUNDS):
            # ── 1. Stream Model Generation ──
            accumulated = ""
            thinking_done = False
            is_retry_gen = False  # set True during parse-retry re-generations
            yield json.dumps({"type": "status", "data": "Generating..."})
            
            for chunk in self.model_client.stream_generate(
                messages=current_history,
                image=image_path,
                max_tokens=self.config.suggested_tokens,
                thinking=self.config.suggested_thinking
            ):
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
            
            # Strip leading echo fragments from previous round (e.g. "code.", "intuitive.")
            if tool_round > 0 and text:
                frag_match = re.match(r'^(\S[^.\n]{0,28}\.)\s*\n\n', text)
                if frag_match:
                    text = text[frag_match.end():]
            
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
                tool_result = f"Error: Tool '{tool_name}' is not enabled in this cartridge."
                sandbox_images = []
                html_artifact = ""
            else:
                raw_result = execute_tool(tool_name, tool_args)
                if isinstance(raw_result, dict):
                    tool_result = raw_result.get("output", "")
                    sandbox_images = raw_result.get("images", [])
                    html_artifact = raw_result.get("html", "")
                else:
                    tool_result = str(raw_result)
                    sandbox_images = []
                    html_artifact = ""
                
            result_data = {"name": tool_name, "result": tool_result, "images": sandbox_images}
            if html_artifact:
                result_data["html"] = html_artifact
            yield json.dumps({"type": "tool_result", "data": result_data})
            
            # ── 4. Build enriched context for next round ──
            is_failure = tool_result in ("(no output)", "") or str(tool_result).startswith("Error:")
            consecutive_failures = consecutive_failures + 1 if is_failure else 0
            
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
                result_context += f"\n[{len(sandbox_images)} plot image(s) were generated and displayed to the user. Do NOT recreate or describe the plot — the user can already see it. Focus on analysis and insights.]"
            result_context += failure_note
                
            # Append interaction to history — strip <tool_call> XML from assistant text
            history_text = re.sub(r'<tool_call>[\s\S]*?</tool_call>', '', text, flags=re.IGNORECASE)
            history_text = re.sub(r'<tool_call>[\s\S]*$', '', history_text, flags=re.IGNORECASE)
            history_text = re.sub(r'<\|tool_call\|>[\s\S]*$', '', history_text)
            history_text = history_text.strip()
            current_history.append({"role": "assistant", "content": history_text or "(used tool)"})
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
        
        # Post-conversation: extract user memories
        try:
            extracted = user_memory.extract_memories_from_conversation(history)
            new_memories = []
            for mem_type, mem_content in extracted:
                mem = user_memory.add(mem_content, memory_type=mem_type, source="auto")
                if mem.get("hits", 1) == 1:  # Only report newly created
                    new_memories.append(mem)
            if new_memories:
                yield json.dumps({
                    "type": "memory_update",
                    "data": [{"content": m["content"], "type": m["type"]} for m in new_memories]
                })
                logger.info(f"Extracted {len(new_memories)} new memories from conversation")
        except Exception as e:
            logger.warning(f"Memory extraction failed: {e}")

        # Post-conversation: update cartridge context and global profile
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

        # Cleanup temp image files created during inference
        self.model_client.cleanup_temp_files()
