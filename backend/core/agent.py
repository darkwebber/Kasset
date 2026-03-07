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

    # Extract the first complete JSON object from the string
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
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict) and "name" in obj:
                        return obj
                except json.JSONDecodeError:
                    pass
                start = None

    # Last resort: try to find name and arguments with a more lenient approach
    name_match = re.search(r'"name"\s*:\s*"(\w+)"', raw)
    args_match = re.search(r'"arguments"\s*:\s*(\{[^}]*\})', raw, re.DOTALL)
    if name_match and args_match:
        try:
            args = json.loads(args_match.group(1))
            return {"name": name_match.group(1), "arguments": args}
        except json.JSONDecodeError:
            # Even more lenient: just extract what we can
            logger.warning(f"Partial tool call parsed: name={name_match.group(1)}, args failed")
            pass

    if '<tool_call>' in raw.lower() or '"name"' in raw:
        logger.warning(f"Failed to parse tool call from: {raw[:200]}")
    return None

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
            "To use a tool, wrap the call in XML tags like this:\n"
            '<tool_call>{"name": "tool_name", "arguments": {"param": "value"}}</tool_call>\n\n'
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
        MAX_TOOL_ROUNDS = 8
        consecutive_failures = 0
        
        current_history = list(base_history)
        
        for tool_round in range(MAX_TOOL_ROUNDS):
            # 1. Stream Model Generation
            accumulated = ""
            thinking_done = False
            yield json.dumps({"type": "status", "data": "Generating..."})
            
            for chunk in self.model_client.stream_generate(
                messages=current_history,
                image=image_path if tool_round == 0 else None,
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

            # 2. Process complete generation
            thought, text = parse_thinking(accumulated)
            
            tool_req = extract_tool_call(text)
            if not tool_req:
                # Final answer reached
                yield json.dumps({"type": "done", "data": text})
                break
                
            # 3. Tool Execution Phase
            tool_name = tool_req.get("name", "")
            tool_args = tool_req.get("arguments", {})
            
            # Include code directly in tool_start so frontend can display immediately
            start_data = {"name": tool_name, "args": tool_args}
            if tool_name in ("execute_python", "execute_cpp") and "code" in tool_args:
                start_data["code"] = tool_args["code"]
            
            yield json.dumps({
                "type": "tool_start", 
                "data": start_data
            })
            
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
                # Tool results can be str or dict with output/images/html
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
            yield json.dumps({
                "type": "tool_result", 
                "data": result_data
            })
            
            # Failure tracking
            is_failure = tool_result in ("(no output)", "") or str(tool_result).startswith("Error:")
            consecutive_failures = consecutive_failures + 1 if is_failure else 0
            
            if consecutive_failures >= 2:
                yield json.dumps({"type": "status", "data": "Tool failed repeatedly. Generating final response..."})
                failure_note = "\nIMPORTANT: Multiple tools failed. Give your best final answer with the data you have."
            else:
                failure_note = ""
            
            # Build context-rich tool result for history
            result_context = f"Tool result for {tool_name}: {tool_result}"
            if sandbox_images:
                result_context += f"\n[{len(sandbox_images)} plot image(s) were generated and displayed to the user. You do NOT need to recreate or describe the plot — the user can already see it. Focus on analysis and insights instead.]"
            result_context += failure_note
                
            # Append interaction to history for next synthesis step
            current_history.append({"role": "assistant", "content": text})
            current_history.append({"role": "user", "content": result_context})
            
            if consecutive_failures >= 2:
                # Do one last non-tool call to summarize
                final_res = self.model_client.generate(current_history, max_tokens=self.config.suggested_tokens, thinking=False)
                _, final_text = parse_thinking(final_res)
                yield json.dumps({"type": "token", "data": final_text})
                yield json.dumps({"type": "done", "data": final_text})
                break
        else:
            # Hit max rounds — do a final summarizing generation instead of erroring
            current_history.append({"role": "user", "content": "You have reached the maximum number of tool rounds. Please give your best final answer now with the information you have gathered so far."})
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
