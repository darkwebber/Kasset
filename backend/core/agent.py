import json
import hashlib
import logging
import re
import uuid
import threading
from pathlib import Path
from typing import List, Dict, Any, Generator, Tuple, Optional
from .tool_registry import execute_tool, run_approved_command, get_session_notes, clear_session_notes, save_notes as _save_session_notes
from .plugin_loader import plugin_loader
from .input_type_loader import input_type_loader
from .sandbox import _SHARED_GLOBALS as _sandbox_globals
from .persistence import user_memory, prompt_cache, chat_store
from .context_manager import (
    user_settings, SessionSummarizer, CartridgeContext, GlobalProfile
)
from .knowledge_graph import ConversationGraph
from .tool_parser import (
    parse_thinking, extract_tool_call, has_tool_call_attempt,
    diagnose_tool_call_error, enrich_tool_error,
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

# ─── Interactive widget state for structured user input ───
# Same pattern as consent: register → wait → respond.
# Supports: choice, slider, editor, form, embed
_interactive_registry: Dict[str, dict] = {}
_interactive_lock = threading.Lock()

def _register_interactive(widget_id: str) -> threading.Event:
    """Register an interactive widget request. Returns Event to wait on."""
    event = threading.Event()
    with _interactive_lock:
        _interactive_registry[widget_id] = {"event": event, "response": None, "dismissed": False}
    return event

def _pop_interactive(widget_id: str) -> dict:
    """Remove and return an interactive entry."""
    with _interactive_lock:
        return _interactive_registry.pop(widget_id, {})

def respond_interactive(widget_id: str, response_data: Any):
    """Called by api.py when user submits a widget response."""
    with _interactive_lock:
        entry = _interactive_registry.get(widget_id)
    if entry:
        entry["response"] = response_data
        entry["event"].set()

def dismiss_interactive(widget_id: str):
    """Called by api.py when user dismisses/skips a widget."""
    with _interactive_lock:
        entry = _interactive_registry.get(widget_id)
    if entry:
        entry["dismissed"] = True
        entry["event"].set()


# ─── Tool parsing functions are in tool_parser.py ───
# Backward-compat aliases for any internal references using old private names
_has_tool_call_attempt = has_tool_call_attempt
_diagnose_tool_call_error = diagnose_tool_call_error
_enrich_tool_error = enrich_tool_error


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
                        # Images and binary files: reinforce the full absolute path so models don't use just the filename
                        abs_path = str(p)
                        ext = p.suffix.lower()
                        file_type = "image" if ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.heic') else "binary"
                        context = (
                            f"\n<attached_context path=\"{abs_path}\" type=\"{file_type}\">"
                            f"\n[Binary {file_type} file. FULL ABSOLUTE PATH: {abs_path}]"
                            f"\n[IMPORTANT: You MUST use the full path '{abs_path}' — NOT just the filename '{p.name}'. Relative paths will fail.]"
                            f"\n</attached_context>"
                        )
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
        self.graph = ConversationGraph()  # Knowledge graph for this conversation

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
        "search_files": {"desc": "Search for files matching a glob pattern (max 50 results). Best first step for repo exploration: find candidate files/modules before reading them.", "params": {"pattern": "Glob pattern to match", "directory": "Directory to search (default: '~')"}},
        "read_file": {"desc": "Read a text file. Use start_line/end_line (1-indexed) to read specific line ranges — returns numbered lines. Without range: files under 50KB shown in full, files over 50KB return structural overview (signatures + line numbers). Max 500KB.", "params": {"path": "File path to read", "max_lines": "Max lines for full read (default: 100)", "start_line": "Start line number, 1-indexed (optional — for reading specific sections)", "end_line": "End line number, 1-indexed (optional — defaults to start_line+200)"}},
        "edit_file": {"desc": "Surgical find-and-replace in a file. Replaces the FIRST occurrence of old_text with new_text. Much better than write_file for targeted code edits — no need to rewrite the whole file. Always read_file first to get exact text.", "params": {"path": "File path to edit", "old_text": "Exact text to find (must match perfectly including whitespace)", "new_text": "Replacement text"}},
        "grep_code": {"desc": "Search file CONTENTS for a regex pattern across a directory tree. Returns matching lines with file paths and line numbers. Uses ripgrep if available. Essential for finding where functions/variables/classes are defined or used in a codebase.", "params": {"pattern": "Regex pattern to search for", "directory": "Directory to search in (default: '.')", "include": "File glob filter, e.g. '*.py' or '*.ts' (optional)", "max_results": "Max result lines (default: 30)"}},
        "write_file": {"desc": "Write text content to a file. Creates parent directories automatically. Use for saving code, documents, configs, or any text output. Prefer this over run_command for writing files.", "params": {"path": "File path to write (absolute or ~/...)", "content": "Text content to write", "mode": "'overwrite' (default) or 'append'"}},
        "run_command": {"desc": "Run shell commands with smart timeout. **Three modes**: (1) Fast commands (ls, cat, git status): 30s timeout. (2) Medium commands (find /, grep -r, make, builds): 120s timeout. (3) Long-running commands (servers, dev servers, watchers, tail -f): auto-started in background — returns a bg_id. **Background commands**: `bg_status <id>` to check output, `bg_stop <id>` to terminate, `bg_list` to see all. Supports pipes (|), chaining (&&, ;). Destructive commands (rm, sudo) are blocked. Write operations require user consent (CONSENT_REQUIRED).", "params": {"command": "Shell command to run (or bg_status/bg_stop/bg_list for background process management)", "cwd": "Optional working directory (absolute path). Defaults to home directory if not specified."}},
        "calculate": {"desc": "Evaluate a math expression safely. Supports sqrt, log, trig, factorial, pi, e.", "params": {"expression": "Math expression to evaluate"}},
        "execute_python": {"desc": "Execute Python code in a stateful sandbox. Captures stdout/stderr. Matplotlib plots are AUTO-CAPTURED as images — do NOT call plt.show(). Variables persist across calls. Pre-imported: pandas (pd), numpy (np), matplotlib.pyplot (plt), scipy (+ scipy.stats), seaborn (sns), math, json, csv, re, PIL/PILImage, sklearn, torch, torchvision. Quick chart helpers: qchart_bar/pie/line/scatter/hist/heatmap. Image editing helpers: img_load/save/show/preview/adjust/hue_shift/color_replace/tint/vignette/sepia/invert/crop/resize/rotate/flip/blur/grayscale/etc. If a package is missing, you'll get MISSING_PACKAGE — ask the user for consent to install it before retrying.", "params": {"code": "Python code to execute"}},
        "execute_cpp": {"desc": "Compile and run C++ code (C++17, g++/clang++). Returns compilation errors or program output.", "params": {"code": "C++ source code", "stdin_input": "(optional) stdin input for the program"}},
        "html_preview": {"desc": "Embed interactive HTML directly in the chat as a sandboxed iframe. Use for buttons, demos, mini-apps, interactive widgets, visualizations. The HTML is rendered live — user can interact with it. MUCH better than execute_python for HTML — avoids string escaping issues.", "params": {"html": "Complete HTML string (can include <style>, <script>, etc.)", "title": "Short title for the artifact (optional)"}},
        "save_notes": {"desc": "Save working notes/findings to a persistent scratchpad. Notes survive across tool rounds and are automatically available when user says 'continue'. Essential for multi-step analysis tasks — save findings as you go so nothing is lost if rounds run out.", "params": {"notes": "Text to save (findings, analysis, TODO items, progress)", "mode": "'append' (default — add to existing) or 'replace' (overwrite)"}},
        "search_web": {"desc": "Search the web using DuckDuckGo. Returns titles, URLs, and snippets for top results.", "params": {"query": "Search query", "max_results": "Number of results (default: 5)"}},
        "read_url": {"desc": "Fetch and extract readable text content from a webpage URL. Content is preprocessed: ads, navs, sidebars, and boilerplate are stripped. Returns clean markdown.", "params": {"url": "Full URL to fetch (include https://)"}},
        "read_rss": {"desc": "Read and parse an RSS or Atom feed. Returns structured entries with title, date, link, and summary.", "params": {"url": "RSS/Atom feed URL", "max_items": "Max entries to return (default: 10)"}},
        "get_location": {"desc": "Get approximate location from IP geolocation: city, region, country, timezone, coordinates.", "params": {}},
        "request_user_input": {
            "desc": (
                "Request structured input from the user via an interactive widget. "
                "The stream pauses until the user responds. Widget types:\n"
                "  - **choice**: Present options for user to pick. Use for quizzes, preferences, decisions. "
                "Args: prompt (question text), options (array of {label, value, description?}), multiple (bool, default false).\n"
                "  - **slider**: Numeric adjustment with live preview. Use for fine-tuning values (brightness, opacity, size). "
                "Args: prompt (label), sliders (array of {name, label, min, max, step, default, unit?}).\n"
                "  - **editor**: Let user edit text/code you generated, returns their edits. "
                "Args: prompt (instruction), content (initial text), language (code language or 'text').\n"
                "  - **form**: Collect multiple structured fields. "
                "Args: prompt (title), fields (array of {name, label, type: 'text'|'number'|'select'|'toggle', options?, default?}).\n"
                "  - **embed**: Display embedded content (YouTube, webpage). Display-only, no response. "
                "Args: url (URL to embed), title (display title), embed_type ('youtube'|'iframe')."
            ),
            "params": {
                "widget_type": "One of: choice, slider, editor, form, embed",
                "config": "Widget configuration object (varies by type — see description)",
            },
        },
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
        input_methods_block = ""
        input_methods_raw = getattr(self.config, "input_methods", []) or []
        # Resolve string IDs to full dicts via input_type_loader
        input_methods = []
        for ref in (input_methods_raw if isinstance(input_methods_raw, list) else []):
            resolved = input_type_loader.resolve_input_method(ref)
            if resolved:
                input_methods.append(resolved)
        if input_methods:
            lines = [
                "\n\n### Custom Input Methods (from this kasset)",
                "Use these templates when calling `request_user_input` to collect better structured input:",
            ]
            for m in input_methods[:12]:
                if not isinstance(m, dict):
                    continue
                mid = str(m.get("id", "")).strip() or "custom-method"
                name = str(m.get("name", mid)).strip()
                desc = str(m.get("description", "")).strip()
                widget_type = str(m.get("widget_type", "custom")).strip() or "custom"
                lines.append(f"- **{name}** (`{mid}`) — widget_type: `{widget_type}`")
                if desc:
                    lines.append(f"  - {desc}")
                example = m.get("example")
                if isinstance(example, dict):
                    try:
                        lines.append(f"  - Example: `{json.dumps(example, ensure_ascii=False)[:220]}`")
                    except Exception:
                        pass
            input_methods_block = "\n".join(lines) + "\n"
        code_mode_block = ""
        if "code-pilot" in (self.config.active_cartridge_ids or []):
            code_mode_block = (
                "\n\n### Code Pilot Mode\n"
                "- Explore progressively: grep → read relevant sections → act.\n"
                "- Track cross-file relationships. Reuse facts from earlier results.\n"
                "- Prefer minimal surgical edits over broad rewrites.\n"
                "- Save findings with `save_notes` every few rounds.\n"
            )

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
            "### Task Completion Awareness (CRITICAL)\n"
            "After EACH tool result, check: **Is the user's task done?**\n"
            "- If a plot/image was generated and displayed → task is DONE. Summarize in 1-2 sentences and STOP.\n"
            "- If a file was written successfully → task is DONE. Do NOT re-read or re-write the same file.\n"
            "- If code ran without errors and produced the expected output → task is DONE.\n"
            "- **NEVER** call the same tool with identical or near-identical arguments twice.\n"
            "- **NEVER** re-verify your own work unless the user asks you to. The tool result already confirms success.\n"
            "- After completing a task, give a SHORT summary (1-3 sentences) and STOP. Do not offer extensive follow-up suggestions.\n\n"
            "**Error recovery**: If a tool is not available, immediately switch to an available alternative. "
            "If code fails twice with the same error, stop and explain the issue to the user instead of retrying.\n\n"
            "### Multi-Round Response Rules (CRITICAL)\n"
            "Your response is streamed continuously to the user. When you make a tool call, your text BEFORE the tool call is ALREADY VISIBLE. "
            "After the tool result comes back, you continue the SAME response. This means:\n"
            "- **Keep pre-tool-call text SHORT** — 1-2 sentences max before a tool call. Don't write full explanations then call a tool.\n"
            "- **NEVER repeat yourself** — don't re-introduce topics, re-write headings, or restart explanations you already wrote in a previous round.\n"
            "- **Continue, don't restart** — after a tool result, pick up naturally from where you left off.\n"
            "- If the user asked a question, you can often answer it directly WITHOUT any tools. Only call tools when they add genuine value.\n\n"
            "### Content Rules\n"
            "- **NEVER generate markdown images** with external URLs like `![alt](https://...)` — they will NOT render. Describe visuals in text instead.\n"
            "- **NEVER narrate your reasoning outside of `<think>` tags.** If you need to think, wrap it in `<think>...</think>`. All text outside think tags is shown directly to the user.\n"
            "- **Don't run code unprompted** — if the user asks to learn something, explain it first. Only run code when the user asks to see it executed, or when you need a computation/visualization.\n"
            "- **Be concise** — prefer shorter, focused responses over walls of text. Let the user ask follow-ups.\n\n"
            "### Interactive Input (when `request_user_input` is available) — MANDATORY\n"
            "- **NEVER present numbered options in plain text and wait for the user to type a number or choice.** This is the #1 UX failure. ALWAYS use a widget instead.\n"
            "- `widget_type: \"choice\"` — **REQUIRED** whenever you would say \"Which of these...?\", \"Do you want A or B?\", \"Choose from:\", \"Pick one:\", or list numbered options. Examples:\n"
            "  - \"Should I use React or Vue?\" → choice widget with options\n"
            "  - \"Which file should I edit?\" → choice widget with file options\n"
            "  - \"Would you like to proceed?\" → choice widget with Yes/No\n"
            "  - \"What tone — formal, casual, or technical?\" → choice widget\n"
            "- `widget_type: \"form\"` — when you need multiple pieces of info (audience, goals, constraints). Keep forms SHORT (3-5 fields).\n"
            "- `widget_type: \"editor\"` — when presenting a draft/code the user might want to edit before finalizing.\n"
            "- `widget_type: \"slider\"` — when fine-tuning a numeric value (brightness, opacity, length, count).\n"
            "- **Anti-pattern (FORBIDDEN)**: Writing \"Here are your options: 1. X  2. Y  3. Z  — Which do you prefer?\" as plain text. This MUST be a choice widget.\n"
            "- **Anti-pattern (FORBIDDEN)**: Asking \"Would you like me to save this?\" as plain text when you could use a choice widget.\n\n"
            "### Tool Selection Guide\n"
            "- **Math**: Use `calculate` for simple arithmetic. Use `execute_python` for anything complex.\n"
            "- **Files**: Always `read_file` before editing. Use `start_line`/`end_line` to read specific sections. Use `list_directory` to explore first.\n"
            "- **Code editing**: Use `edit_file` for surgical find-and-replace. Use `write_file` only for new files or full rewrites.\n"
            "- **Code search**: Use `grep_code` to search file contents by pattern. Use `search_files` for filename matching.\n"
            "- **Shell**: Use `run_command` only when no specialized tool fits.\n"
            "- **Web**: Use `read_url` to fetch content. Use `search_web` first if you don't have a URL.\n"
            "- **HTML/Interactive**: Use `html_preview` to embed interactive HTML in chat (buttons, demos, mini-apps). Do NOT use execute_python for HTML — use the dedicated tool.\n"
            "- **Images**: If the user attaches an image and you can see it, describe what you see directly. Use `execute_python` with PIL for editing.\n"
            "- **Progress tracking**: Use `save_notes` during multi-step tasks (audits, research, analysis) to save findings progressively. Notes persist across rounds and 'continue' messages.\n\n"
            + code_mode_block
            + input_methods_block
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

        # Deduplicate facts across context layers to prevent repetition
        context_blocks = memory_block + cartridge_block + global_block
        if context_blocks.strip():
            _seen_facts = set()
            deduped_lines = []
            for line in context_blocks.split('\n'):
                stripped = line.strip().lower().rstrip('.')
                # Keep headers and short formatting lines as-is
                if len(stripped) <= 5 or stripped.startswith('#') or stripped.startswith('**'):
                    deduped_lines.append(line)
                elif stripped not in _seen_facts:
                    _seen_facts.add(stripped)
                    deduped_lines.append(line)
            context_blocks = '\n'.join(deduped_lines)

        return {
            "role": "system",
            "content": (
                self.config.merged_prompt
                + tools_block
                + context_blocks
                + self.graph.get_compact_map()
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
        
        # Build knowledge graph from conversation history
        if not self.graph.nodes:
            self.graph = ConversationGraph.from_messages(processed_history)
        # Capture user intent from the latest message
        if processed_history and processed_history[-1].get("role") == "user":
            self.graph.add_user_intent(processed_history[-1]["content"])
        
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
        
        # Clear session notes for brand new chats (only 1 user message = first turn)
        user_msg_count = sum(1 for m in history if m.get("role") == "user")
        if user_msg_count <= 1:
            clear_session_notes()
        
        # Detect "continue" messages and inject progress guidance
        last_user_msg = ""
        if processed_history and processed_history[-1].get("role") == "user":
            last_user_msg = processed_history[-1]["content"].strip().lower()
        _is_continue = last_user_msg in ("continue", "go on", "keep going", "continue please", "go ahead", "carry on")
        if _is_continue and user_msg_count > 1:
            # Build a real summary of what was already done from conversation history
            _done_summary_parts = []
            for m in history:
                c = m.get("content", "")
                if m.get("role") == "user" and c.startswith("Tool result for "):
                    # Extract tool name and first 150 chars of result
                    _tname = c.split("Tool result for ")[1].split(":")[0].strip()
                    _tresult = c.split(":", 1)[1].strip()[:150] if ":" in c.split("Tool result for ")[1] else ""
                    _done_summary_parts.append(f"  - {_tname}: {_tresult}")
            # Also include session notes and knowledge map
            _notes = get_session_notes()
            _kmap = self.graph.get_compact_map(max_tokens=400) if self.graph.nodes else ""
            _continuation_ctx = "\n\n[SYSTEM — CONTINUATION: The user asked you to continue your previous work.\n"
            if _kmap:
                _continuation_ctx += _kmap.strip() + "\n"
            if _done_summary_parts:
                _continuation_ctx += "Tools already called in previous rounds:\n" + "\n".join(_done_summary_parts[-15:]) + "\n"
            if _notes:
                _continuation_ctx += f"Your saved working notes:\n{_notes}\n"
            _continuation_ctx += "CRITICAL: Do NOT restart. Do NOT re-read files you already read. Pick up where you left off.]"
            for i in range(len(current_history) - 1, -1, -1):
                if current_history[i].get('role') == 'user':
                    current_history[i] = {
                        **current_history[i],
                        'content': current_history[i]['content'] + _continuation_ctx
                    }
                    break
        else:
            # Non-continue: inject session notes if available
            _notes = get_session_notes()
            if _notes:
                for i in range(len(current_history) - 1, -1, -1):
                    if current_history[i].get('role') == 'user':
                        current_history[i] = {
                            **current_history[i],
                            'content': current_history[i]['content'] + (
                                f"\n\n[SYSTEM — Your working notes from previous rounds:]\n{_notes}\n[END NOTES]"
                            )
                        }
                        break
        
        accumulated_response_text = ""  # Track ALL text generated across rounds for anti-repeat
        _tool_activity_log: List[str] = []  # Auto-track tool calls for continuation context
        
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
                        thinking=self.config.suggested_thinking,
                        temperature=getattr(self.config, 'suggested_temperature', None),
                        top_p=getattr(self.config, 'suggested_top_p', None)
                    )
                except Exception as inf_err:
                    logger.warning(f"Inference failed (attempt 1): {inf_err}, retrying...")
                    import gc; gc.collect()
                    yield from self.model_client.stream_generate(
                        messages=current_history,
                        image=image_path if tool_round == 0 else None,
                        max_tokens=self.config.suggested_tokens,
                        thinking=self.config.suggested_thinking,
                        temperature=getattr(self.config, 'suggested_temperature', None),
                        top_p=getattr(self.config, 'suggested_top_p', None)
                    )

            _tool_tag_seen = False
            for chunk in _stream_with_retry():
                accumulated += chunk
                
                # Check for thinking completion to stream actual content
                if "</think>" in accumulated:
                    if not thinking_done:
                        thinking_done = True
                        yield json.dumps({"type": "think_end"})
                    
                    _, answer = parse_thinking(accumulated)
                    # Once <tool_call> appears in the answer, stop streaming
                    # visible tokens — the backend will handle tool execution
                    if '<tool_call>' in answer or '<|tool_call|>' in answer:
                        if not _tool_tag_seen:
                            _tool_tag_seen = True
                            yield json.dumps({"type": "status", "data": "Writing code…"})
                    elif answer.strip():
                        yield json.dumps({"type": "token", "data": chunk})
                elif self.config.suggested_thinking:
                    content = accumulated
                    if "<think>" in content:
                        content = content[content.index("<think>") + len("<think>"):]
                    if content.strip():
                        yield json.dumps({"type": "think_token", "data": chunk})
                else:
                    # Non-thinking mode: also suppress tool_call XML
                    if '<tool_call>' in accumulated or '<|tool_call|>' in accumulated:
                        if not _tool_tag_seen:
                            _tool_tag_seen = True
                            yield json.dumps({"type": "status", "data": "Writing code…"})
                    else:
                        yield json.dumps({"type": "token", "data": chunk})

            # ── 2. Process complete generation ──
            thought, text = parse_thinking(accumulated)
            
            # Track accumulated response text across rounds (for anti-repeat)
            clean_for_tracking = re.sub(r'<tool_call>[\s\S]*?</tool_call>', '', text, flags=re.IGNORECASE)
            clean_for_tracking = re.sub(r'<tool_call>[\s\S]*$', '', clean_for_tracking, flags=re.IGNORECASE).strip()
            if clean_for_tracking:
                accumulated_response_text += ("\n\n" if accumulated_response_text else "") + clean_for_tracking
            
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
                        thinking=self.config.suggested_thinking,
                        temperature=getattr(self.config, 'suggested_temperature', None),
                        top_p=getattr(self.config, 'suggested_top_p', None)
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
                # Strip leaked </tool_call> tags with trailing text
                clean_text = re.sub(r'</tool_call>[\s\S]*', '', clean_text, flags=re.IGNORECASE)
                # Strip leaked </think> tags
                clean_text = re.sub(r'</think>', '', clean_text, flags=re.IGNORECASE)
                # Strip trailing JSON closers leaked from tool calls (e.g. '"}}')
                clean_text = re.sub(r'"\s*\}\s*\}\s*$', '', clean_text, flags=re.MULTILINE)
                clean_text = clean_text.strip()
                if not clean_text and text.strip():
                    clean_text = text.strip()
                # Auto-save tool activity to session notes for continuation
                if _tool_activity_log:
                    _auto_notes = "Tools used this session: " + ", ".join(_tool_activity_log)
                    _save_session_notes(notes=_auto_notes, mode="append")
                yield json.dumps({"type": "done", "data": clean_text})
                break
                
            # ── 3. Tool Execution Phase ──
            tool_name = tool_req.get("name", "")
            tool_args = tool_req.get("arguments", {})
            
            # Detect identical/near-identical code re-submissions (loop detection)
            if tool_name in ("execute_python", "execute_cpp") and "code" in tool_args:
                raw_code = tool_args["code"]
                # Normalize: strip whitespace, comments, blank lines for fuzzy matching
                normalized = re.sub(r'#[^\n]*', '', raw_code)  # strip comments
                normalized = re.sub(r'\s+', ' ', normalized).strip()  # collapse whitespace
                code_hash = hashlib.md5(normalized.encode()).hexdigest()
                if code_hash in _prev_code_hashes:
                    logger.warning(f"Identical/near-identical code re-submission detected (hash={code_hash[:8]}), forcing stop")
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

            # ── Interactive widget flow: request_user_input ──
            if tool_name == "request_user_input":
                widget_type = tool_args.get("widget_type", "choice")
                config = tool_args.get("config", {})
                # Models often put widget params at the top level instead of
                # nesting inside "config".  Merge any top-level keys that
                # aren't meta-keys so the frontend always gets the full payload.
                _META_KEYS = {"widget_type", "config"}
                for k, v in tool_args.items():
                    if k not in _META_KEYS and k not in config:
                        config[k] = v
                widget_id = str(uuid.uuid4())
                
                # Embed is display-only — no response needed
                if widget_type == "embed":
                    yield json.dumps({"type": "interactive", "data": {
                        "widget_id": widget_id, "widget_type": "embed", **config
                    }})
                    tool_result = "Embed displayed to user."
                    sandbox_images = []
                    html_artifact = ""
                else:
                    event = _register_interactive(widget_id)
                    yield json.dumps({"type": "interactive", "data": {
                        "widget_id": widget_id, "widget_type": widget_type, **config
                    }})
                    # Poll with keepalive pings so the SSE stream doesn't stall
                    KEEPALIVE_INTERVAL = 15  # seconds between pings
                    MAX_WAIT = 300  # 5 min total timeout
                    elapsed = 0
                    while elapsed < MAX_WAIT:
                        if event.wait(timeout=KEEPALIVE_INTERVAL):
                            break  # User responded
                        elapsed += KEEPALIVE_INTERVAL
                        yield json.dumps({"type": "keepalive", "data": {"waiting_for": widget_id}})
                    state = _pop_interactive(widget_id)
                    if state.get("dismissed"):
                        tool_result = "User dismissed/skipped the input widget. Continue without this input."
                    elif state.get("response") is not None:
                        resp = state["response"]
                        tool_result = f"User response: {json.dumps(resp) if isinstance(resp, (dict, list)) else str(resp)}"
                    else:
                        tool_result = "User input timed out. Continue without this input."
                    sandbox_images = []
                    html_artifact = ""
                
                result_data = {"name": tool_name, "result": tool_result, "images": []}
                yield json.dumps({"type": "tool_result", "data": result_data})
                current_history.append({"role": "assistant", "content": text.strip() or "[Requesting input...]"})
                current_history.append({"role": "user", "content": f"Tool result for {tool_name}: {tool_result}"})
                continue
            
            # Block dangerous tools for network (non-local) clients
            SHELL_TOOLS = {"run_command", "execute_python", "execute_cpp", "write_file"}
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
            
            # Update knowledge graph with tool result
            try:
                self.graph.set_round(tool_round)
                self.graph.add_tool_result(
                    tool_name, tool_args, str(tool_result),
                    has_images=bool(sandbox_images)
                )
                self.graph._prune_old_results()
            except Exception as kg_err:
                logger.debug(f"Knowledge graph update failed: {kg_err}")
            
            # ── 4. Build enriched context for next round ──
            is_failure = tool_result in ("(no output)", "") or str(tool_result).startswith("Error:") or "Traceback" in str(tool_result)
            consecutive_failures = consecutive_failures + 1 if is_failure else 0

            # Loop detection: if the model retries the exact same tool+args, force stop sooner
            call_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)[:200]}"
            if is_failure and call_sig in session_errors:
                consecutive_failures = max(consecutive_failures, 3)  # Immediate escalation for repeated identical failures

            # Error-pattern loop detection: same error type from same tool = stuck
            if is_failure and tool_name in ("execute_python", "execute_cpp"):
                # Extract the core error line (e.g. "ValueError: Invalid property...")
                err_lines = str(tool_result).strip().splitlines()
                core_err = err_lines[-1] if err_lines else ""
                err_pattern = f"{tool_name}::{core_err[:100]}"
                _error_patterns = getattr(self, '_error_patterns', [])
                if err_pattern in _error_patterns:
                    logger.warning(f"Same error pattern repeated: {core_err[:80]}")
                    consecutive_failures = max(consecutive_failures, 3)
                _error_patterns.append(err_pattern)
                self._error_patterns = _error_patterns

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
                result_context += "]"
                # Only force stop for image tasks if we're past early exploration
                if tool_round >= 2:
                    result_context += "\n[SYSTEM] ✅ Output is visible. Give a 1-2 sentence summary and STOP unless the user's request requires more steps."
            if html_artifact:
                result_context += "\n[SYSTEM] HTML artifact displayed to user. If this completes the request, give a brief summary. If more work is needed (e.g., user asked for multiple things), continue with the next step."
            if tool_name == "write_file" and not is_failure:
                result_context += "\n[SYSTEM] File written successfully. Do NOT re-read or re-write the same file. If the task is complete, summarize and STOP."
            if tool_name == "execute_python" and not is_failure and not sandbox_images and not html_artifact:
                result_context += "\n[SYSTEM] Code executed successfully. If the user's request is fulfilled, summarize and STOP. Do NOT re-run the same code."
            if tool_name == "execute_python" and "Traceback" in str(tool_result):
                result_context += "\n[IMPORTANT: Fix ONLY the specific error in your code — do NOT rewrite from scratch. Make a minimal targeted edit to the failing line(s).]"
            # Inject round counter so model knows budget
            result_context += f"\n[Tool round {tool_round + 1}/{MAX_TOOL_ROUNDS}]"
            # Inject knowledge map every 3 rounds so model sees cumulative structured progress
            if (tool_round + 1) % 3 == 0 and self.graph.nodes:
                _kmap = self.graph.get_compact_map(max_tokens=300)
                if _kmap:
                    result_context += _kmap
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
            # Use minimal placeholder for tool-only rounds to prevent model echoing
            # The frontend strips "(used tool)" via cleanContent regex
            if not history_text:
                history_text = "(used tool)"
            current_history.append({"role": "assistant", "content": history_text})
            
            # Auto-track tool activity for continuation context (independent of model calling save_notes)
            _tool_log_entry = f"{tool_name}"
            if tool_name in ("read_file", "write_file", "edit_file"):
                _tool_log_entry += f"({tool_args.get('path', '')})"
            elif tool_name in ("list_directory",):
                _tool_log_entry += f"({tool_args.get('path', '')})"
            elif tool_name in ("grep_code",):
                _tool_log_entry += f"(pattern={tool_args.get('pattern', '')})"
            elif tool_name in ("search_files",):
                _tool_log_entry += f"({tool_args.get('pattern', '')})"
            elif tool_name in ("run_command",):
                _tool_log_entry += f"({tool_args.get('command', '')[:50]})"
            _tool_activity_log.append(_tool_log_entry)
            
            # Anti-repeat: if model has generated substantial text across rounds, remind it
            if len(accumulated_response_text) > 200 and tool_round > 0:
                result_context += (
                    "\n[IMPORTANT: Your previous text is ALREADY visible to the user. "
                    "Do NOT repeat introductions, headings, or content you already wrote. "
                    "Continue naturally from where you left off — keep your next response SHORT and focused.]"
                )
            
            current_history.append({"role": "user", "content": result_context})
            
            if consecutive_failures >= 3:
                # Stream the final response instead of blocking generate
                final_text = ""
                for chunk in self.model_client.stream_generate(
                    messages=current_history,
                    max_tokens=self.config.suggested_tokens,
                    thinking=False,
                    temperature=getattr(self.config, 'suggested_temperature', None),
                    top_p=getattr(self.config, 'suggested_top_p', None)
                ):
                    final_text += chunk
                    yield json.dumps({"type": "token", "data": chunk})
                _, clean_final = parse_thinking(final_text)
                yield json.dumps({"type": "done", "data": clean_final})
                break
        else:
            # Auto-save tool activity before max-round summary
            if _tool_activity_log:
                _auto_notes = "Tools used this session: " + ", ".join(_tool_activity_log)
                _save_session_notes(notes=_auto_notes, mode="append")
            # Hit max rounds — produce a final summary (streaming)
            current_history.append({"role": "user", "content": "You have reached the maximum number of tool rounds. Summarize your findings and give your best final answer with the information gathered so far. Tell the user they can say 'continue' to keep going."})
            final_text = ""
            for chunk in self.model_client.stream_generate(
                messages=current_history,
                max_tokens=self.config.suggested_tokens,
                thinking=False,
                temperature=getattr(self.config, 'suggested_temperature', None),
                top_p=getattr(self.config, 'suggested_top_p', None)
            ):
                final_text += chunk
                yield json.dumps({"type": "token", "data": chunk})
            _, clean_final = parse_thinking(final_text)
            yield json.dumps({"type": "done", "data": clean_final})
        
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
