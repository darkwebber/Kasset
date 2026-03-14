import json
import hashlib
import logging
import random
import re
import uuid
import threading
from pathlib import Path
from typing import List, Dict, Any, Generator, Tuple, Optional
from .tool_registry import execute_tool, run_approved_command, get_session_notes, clear_session_notes, save_notes as _save_session_notes, set_graph_ref as _set_graph_ref
from .tool_executor import ToolExecutor
from .adaptive_sampler import AdaptiveSampler
from .plugin_loader import plugin_loader
from .input_type_loader import input_type_loader
from .sandbox import _BASE_GLOBALS as _sandbox_globals, get_session as _get_sandbox_session
from .persistence import user_memory, prompt_cache, chat_store
from .context_manager import (
    user_settings, SessionSummarizer, CartridgeContext, GlobalProfile,
    ContextAssembler,
)
from .knowledge_graph import ConversationGraph, PersistentGraph
from .user_profiling import detect_expertise, get_tone_hint
from .tool_parser import (
    parse_thinking, extract_tool_call, has_tool_call_attempt,
    diagnose_tool_call_error, enrich_tool_error, auto_resolve_error,
)

logger = logging.getLogger(__name__)

# ─── Quirky loading messages shown while the model thinks ───
_LOADING_MESSAGES = [
    "Brewing thoughts...",
    "Consulting the silicon oracle...",
    "Rearranging neurons...",
    "Summoning the muse...",
    "Crunching the multiverse...",
    "Warming up the tensor cores...",
    "Channeling cosmic energy...",
    "Asking the rubber duck...",
    "Spinning up hamster wheels...",
    "Shaking the magic 8-ball...",
    "Aligning the stars...",
    "Polishing the crystal ball...",
    "Feeding the gremlins...",
    "Calibrating the flux capacitor...",
    "Downloading more RAM...",
    "Consulting Stack Overflow...",
    "Untangling spaghetti code...",
    "Reticulating splines...",
    "Compiling thoughts...",
    "Defragmenting brain cells...",
]

_TOOL_LOADING_MESSAGES = [
    "Writing code...",
    "Hacking the mainframe...",
    "Typing furiously...",
    "Building something cool...",
    "Crafting artisanal code...",
    "Assembling the bits...",
    "Wrangling some syntax...",
    "Deploying semicolons...",
]

def _pick_loading_msg(tool: bool = False) -> str:
    pool = _TOOL_LOADING_MESSAGES if tool else _LOADING_MESSAGES
    return random.choice(pool)

# ─── Consent state for commands requiring user approval ───
# Global registry keyed by consent_id. Each Agent instance creates unique IDs,
# so concurrent streams never collide.
_consent_registry: Dict[str, dict] = {}  # consent_id -> {"event": Event, "approved": bool}
_consent_lock = threading.Lock()

def _cleanup_stale_registries():
    """Remove consent/interactive entries older than 30 minutes to prevent memory leaks."""
    import time as _time
    cutoff = _time.time() - 1800  # 30 minutes
    with _consent_lock:
        stale = [k for k, v in _consent_registry.items() if v.get("created_at", 0) < cutoff]
        for k in stale:
            _consent_registry.pop(k, None)
    with _interactive_lock:
        stale = [k for k, v in _interactive_registry.items() if v.get("created_at", 0) < cutoff]
        for k in stale:
            pid = _interactive_registry[k].get("persistent_id")
            if pid:
                _persistent_id_map.pop(pid, None)
            _interactive_registry.pop(k, None)

def _register_consent(consent_id: str) -> threading.Event:
    """Register a new consent entry. Returns the Event to wait on."""
    import time as _time
    _cleanup_stale_registries()
    event = threading.Event()
    with _consent_lock:
        _consent_registry[consent_id] = {"event": event, "approved": False, "created_at": _time.time()}
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
# Supports: choice, slider, editor, form, embed, diff
# Persistent widgets stay alive across turns via persistent_id.
_interactive_registry: Dict[str, dict] = {}   # keyed by widget_id
_persistent_id_map: Dict[str, str] = {}        # persistent_id → widget_id
_interactive_lock = threading.Lock()

def _register_interactive(widget_id: str, persistent_id: str | None = None) -> threading.Event:
    """Register an interactive widget request. Returns Event to wait on."""
    import time as _time
    event = threading.Event()
    with _interactive_lock:
        _interactive_registry[widget_id] = {
            "event": event, "response": None, "dismissed": False,
            "persistent_id": persistent_id, "finalized": False,
            "created_at": _time.time(),
        }
        if persistent_id:
            _persistent_id_map[persistent_id] = widget_id
    return event

def _get_and_reset_interactive(widget_id: str) -> dict:
    """Get response and reset event for next round (persistent) or pop (one-shot)."""
    with _interactive_lock:
        entry = _interactive_registry.get(widget_id)
        if not entry:
            return {}
        state = {
            "response": entry["response"],
            "dismissed": entry["dismissed"],
            "finalized": entry.get("finalized", False),
            "persistent_id": entry.get("persistent_id"),
        }
        if entry.get("persistent_id") and not entry.get("finalized"):
            # Persistent widget: reset for next interaction round
            entry["event"] = threading.Event()
            entry["response"] = None
            entry["dismissed"] = False
        else:
            # One-shot or finalized: remove from registry
            pid = entry.get("persistent_id")
            if pid:
                _persistent_id_map.pop(pid, None)
            _interactive_registry.pop(widget_id, None)
        return state

def _pop_interactive(widget_id: str) -> dict:
    """Remove and return an interactive entry (backwards compat)."""
    with _interactive_lock:
        entry = _interactive_registry.pop(widget_id, {})
        if entry:
            pid = entry.get("persistent_id")
            if pid:
                _persistent_id_map.pop(pid, None)
        return entry

def _lookup_persistent_widget(persistent_id: str) -> str | None:
    """Return widget_id for a persistent_id, if still alive."""
    with _interactive_lock:
        return _persistent_id_map.get(persistent_id)

def respond_interactive(widget_id: str, response_data: Any, finalize: bool = False):
    """Called by api.py when user submits a widget response."""
    with _interactive_lock:
        entry = _interactive_registry.get(widget_id)
        if entry:
            entry["response"] = response_data
            if finalize:
                entry["finalized"] = True
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
        self.ctx = ContextAssembler()     # Structured memory blocks for context

    _token_cache: Dict[str, int] = {}  # class-level cache: hash(text[:1000]) -> token count

    def _estimate_tokens(self, text: str) -> int:
        """Token count using actual tokenizer if available, heuristic fallback.
        
        Cached by hash of first 1000 chars to avoid redundant tokenizer calls
        during repeated _trim_context invocations.
        """
        cache_key = hashlib.md5(text[:1000].encode()).hexdigest()
        cached = Agent._token_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            proc = getattr(self.model_client, "processor", None)
            tokenizer = getattr(proc, "tokenizer", None) if proc else None
            if tokenizer and hasattr(tokenizer, "encode"):
                result = len(tokenizer.encode(text))
                Agent._token_cache[cache_key] = result
                # Evict old entries if cache grows too large
                if len(Agent._token_cache) > 500:
                    keys = list(Agent._token_cache.keys())
                    for k in keys[:250]:
                        del Agent._token_cache[k]
                return result
        except Exception:
            pass
        result = max(1, int(len(text) / Agent.CHARS_PER_TOKEN))
        Agent._token_cache[cache_key] = result
        return result

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

        # Second pass: observation masking — compress old tool results to
        # free up token budget before resorting to dropping entire messages
        trimmed_history = self._mask_old_observations(trimmed_history, keep_recent=4)

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

    # ─── Observation Masking ────────────────────────────
    # Based on JetBrains/OpenHands research: masking verbose tool observations
    # while preserving reasoning + action history is as effective as LLM
    # summarization but significantly cheaper. Key insight: the agent's
    # decision history matters more than raw tool output.
    _MASKED_OBS_RE = re.compile(r'^Tool result for \S+: \[(ok|error|done)\] ')

    def _mask_old_observations(self, messages: List[Dict[str, str]], keep_recent: int = 3) -> List[Dict[str, str]]:
        """Compress old tool result messages, keeping only recent ones in full.
        
        Preserves: assistant reasoning, action choices (tool name + args)
        Masks: verbose observations (file contents, command output, search results)
        
        This prevents context distraction where the model gets overwhelmed
        by stale, irrelevant tool outputs from earlier rounds.
        """
        # Find unmasked tool result indices
        tool_result_indices = []
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            if (msg.get("role") == "user"
                and content.startswith("Tool result for ")
                and not self._MASKED_OBS_RE.match(content)):
                tool_result_indices.append(i)

        if len(tool_result_indices) <= keep_recent:
            return messages

        to_mask = set(tool_result_indices[:-keep_recent])

        result = []
        for i, msg in enumerate(messages):
            if i in to_mask:
                result.append({**msg, "content": self._create_observation_mask(msg["content"])})
            else:
                result.append(msg)
        return result

    @staticmethod
    def _create_observation_mask(content: str) -> str:
        """Create a compact 1-line mask for a verbose tool result message.
        
        Strips appended system directives and knowledge maps (regenerated
        each round in the system prompt). Keeps tool name and outcome summary.
        """
        if not content.startswith("Tool result for "):
            return content[:200]

        after_prefix = content[len("Tool result for "):]
        colon_idx = after_prefix.find(":")
        if colon_idx <= 0:
            return content[:200]

        tool_name = after_prefix[:colon_idx].strip()
        full_result = after_prefix[colon_idx + 1:].strip()

        # Strip appended system directives and knowledge maps
        clean_result = re.split(
            r'\n\[(?:Tool round|Round |SYSTEM|IMPORTANT|Previous errors)', full_result
        )[0]
        clean_result = re.split(r'\n\n## Session Knowledge Map', clean_result)[0].strip()

        # Determine status and build summary
        result_lower = clean_result.lower()
        if any(kw in result_lower for kw in ("error:", "traceback", "exception", "failed")):
            status = "error"
            err_lines = [l.strip() for l in clean_result.splitlines() if l.strip()]
            summary = err_lines[-1][:150] if err_lines else "(error)"
        elif clean_result in ("(no output)", ""):
            status = "done"
            summary = "(no output)"
        else:
            status = "ok"
            lines = [l.strip() for l in clean_result.split('\n') if l.strip()]
            first_line = lines[0][:150] if lines else "(empty)"
            line_count = len(lines)
            summary = first_line
            if line_count > 3:
                summary += f" (+{line_count - 1} lines)"

        return f"Tool result for {tool_name}: [{status}] {summary}"

    @staticmethod
    def _strip_old_thinking(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Strip <think>...</think> blocks from all but the last assistant message.
        
        Implements the 'rolling checkpoint' pattern from Qwen3.5 best practices:
        thinking content from previous turns wastes context budget and can
        confuse the model. Only the most recent thinking is preserved.
        """
        # Find the last assistant message index
        last_asst = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                last_asst = i
                break

        result = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "assistant" and i != last_asst:
                content = msg["content"]
                # Strip complete thinking blocks
                stripped = re.sub(r'<think>[\s\S]*?</think>\s*', '', content).strip()
                # Strip unclosed thinking blocks (model was cut off mid-think)
                stripped = re.sub(r'<think>[\s\S]*$', '', stripped).strip()
                if not stripped:
                    stripped = "(reasoning omitted)"
                result.append({**msg, "content": stripped})
            else:
                result.append(msg)
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
        "save_notes": {"desc": "Save structured notes to your scratchpad. Notes survive across tool rounds and are automatically available when user says 'continue'. Categories help organize multi-step work.", "params": {"notes": "Text to save (findings, analysis, plans, progress)", "category": "'finding' (discoveries), 'plan' (next steps), 'todo' (remaining tasks), 'progress' (completed items), 'observation' (general)", "mode": "'append' (default — add to existing) or 'replace' (overwrite)"}},
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
                "Args: prompt (instruction), content (initial text), language (code language or 'text' or 'markdown').\n"
                "  - **outline**: Present a structured outline with sortable, editable, deletable blocks. "
                "User can reorder, edit, add, or remove sections. Returns the final block list + action ('approve'/'revise'). "
                "Args: prompt (instruction), items (array of strings or {title, description} objects).\n"
                "  - **form**: Collect multiple structured fields. "
                "Args: prompt (title), fields (array of {name, label, type: 'text'|'number'|'select'|'toggle', options?, default?}).\n"
                "  - **diff**: Show proposed code/text changes for user to accept/reject per change. "
                "Args: prompt (description), changes (array of {id, label, original, proposed}), file_path (optional), context_before/context_after (optional).\n"
                "  - **embed**: Display embedded content (YouTube, webpage). Display-only, no response. "
                "Args: url (URL to embed), title (display title), embed_type ('youtube'|'iframe')."
            ),
            "params": {
                "widget_type": "One of: choice, slider, editor, outline, form, diff, embed",
                "config": "Widget configuration object (varies by type — see description)",
                "persistent_id": "(optional) Unique ID to track this widget across turns. Re-use same ID to update the same editing session.",
            },
        },
    }

    def _build_system_message(self, tool_round: int = 0) -> Dict[str, str]:
        """Build the system message with tiered detail.
        Round 0: Full tool descriptions, all rules, full context.
        Round 1+: Compact tool signatures, minimal rules, updated graph.
        """
        # Build tool descriptions — compact on round 1+
        all_descriptions = dict(self.TOOL_DESCRIPTIONS)
        all_descriptions.update(plugin_loader.get_tool_descriptions())

        tool_lines = []
        for t in self.config.tools:
            info = all_descriptions.get(t, {"desc": t, "params": {}})
            if tool_round == 0:
                # Full descriptions on first round
                params_str = ", ".join(f'{k}: {v}' for k, v in info["params"].items())
                tool_lines.append(f"- **{t}**({params_str}): {info['desc']}")
            else:
                # Compact: just name(params): first sentence
                params_str = ", ".join(info["params"].keys())
                short_desc = info['desc'].split('.')[0]
                tool_lines.append(f"- `{t}`({params_str}): {short_desc}")
        
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

        if tool_round > 0:
            # Compact mode for round 1+: just format reminder + tool list
            tools_block = (
                f"\n\n## Tools (round {tool_round + 1})\n"
                f"Format: `<tool_call>{{\"name\": \"...\", \"arguments\": {{...}}}}</tool_call>` — one tool per message, stop after tag.\n"
                f"Available: {tool_id_list}\n\n"
                + code_mode_block
                + input_methods_block
                + "\n".join(tool_lines)
            )
        else:
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
            "### Agentic Behavior — Plan, Act, Observe, Adapt\n"
            "You are an autonomous agent with persistent working memory. Follow this cycle:\n"
            "1. **Plan** — In `<think>`, decompose the task into subgoals. For 3+ step tasks, call `save_notes(category='plan')` to persist your plan.\n"
            "2. **Act** — Execute one tool call. Keep code SHORT (<40 lines).\n"
            "3. **Observe** — Analyze the result. Save key findings: `save_notes(category='finding')`.\n"
            "4. **Adapt** — On failure, try a DIFFERENT approach. On success, check if the task is done.\n"
            "5. **Synthesize** — When done, give a SHORT summary (1-3 sentences) and STOP.\n\n"
            "**Working memory**: `save_notes` persists across rounds and 'continue' messages. Use it for:\n"
            "- Plans and progress (what's done, what's next)\n"
            "- Key findings (facts you'll need later)\n"
            "- Decisions (why you chose approach X over Y)\n\n"
            "### Task Completion (CRITICAL)\n"
            "After EACH tool result: **Is the task done?**\n"
            "- Image/plot displayed, file written, code succeeded → DONE. Summarize and STOP.\n"
            "- **NEVER** call the same tool with identical arguments twice.\n"
            "- **NEVER** re-verify your own work. The tool result already confirms success.\n"
            "- On error: fix the specific error, don't rewrite from scratch. After 2 failures with the same error, stop and explain.\n\n"
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
            "### Intellectual Honesty (CRITICAL)\n"
            "- **Never start with validation phrases** like 'Great question!', 'You're absolutely right!', 'That's a great idea!'. Jump straight to the substance.\n"
            "- **Correct incorrect statements** — if the user says something factually wrong, politely but clearly correct them. Do not agree to avoid conflict.\n"
            "- **Express uncertainty explicitly** — say 'I'm not sure' or 'I think, but I'm not certain' when you genuinely don't know. Never fabricate confidence.\n"
            "- **Acknowledge trade-offs** — when recommending an approach, briefly mention its downsides. Don't present everything as perfect.\n\n"
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
        
        # ── Structured Context Assembly via Memory Blocks ──
        # Load read-only context from existing sources into bounded blocks
        memory_block = user_memory.get_context_block()
        cartridge_block = ""
        if user_settings.get("context", "use_cartridge_context"):
            cid = self.config.active_cartridge_ids[0] if self.config.active_cartridge_ids else None
            if cid:
                cartridge_block = CartridgeContext.get_context_block(cid)
        global_block = ""
        if user_settings.get("context", "use_global_profile") and tool_round == 0:
            global_block = GlobalProfile.get_context_block()

        self.ctx.load_readonly_blocks(
            user_memory_block=memory_block,
            cartridge_block=cartridge_block,
            global_block=global_block,
        )

        # Load focused knowledge graph into task_state block
        # Uses relevance-filtered map (only active intents, errors, recent notes)
        graph_map = self.graph.get_focused_map(max_tokens=400) if self.graph.nodes else ""
        if graph_map:
            self.ctx.update_block("task_state", graph_map)

        # Load scratchpad notes into working_notes block (replace, not append,
        # since this is called every round and scratchpad already has all notes)
        scratchpad = self.graph.get_scratchpad_view() if self.graph.nodes else ""
        if scratchpad:
            self.ctx.update_block("working_notes", scratchpad)

        # Assemble all blocks with priority-based budget
        context_budget = int(self.MAX_CONTEXT_TOKENS * 3.5 * 0.30)
        context_blocks = self.ctx.assemble(total_budget_chars=context_budget)

        # Collaboration protocol for kassets with collaboration_mode
        collab_block = ""
        if getattr(self.config, 'collaboration_mode', False):
            collab_block = (
                "\n\n## Collaboration Protocol (MANDATORY)\n"
                "1. **INTAKE FIRST** — First tool call MUST be `request_user_input` (form/choice) to collect preferences.\n"
                "2. **PERSISTENT EDITING** — Use `persistent_id` to keep the same widget alive across turns.\n"
                "3. **SHOW DIFFS** — When refining, use `request_user_input(diff)`. Let user accept/reject each change.\n"
                "4. **RESPECT REJECTION** — Never repeat rejected patterns.\n"
                "5. **PERSIST PROGRESS** — Use `save_notes(category='progress')` to track what's done.\n"
            )

        # User expertise detection — inject tone hint
        expertise_hint = ""
        if hasattr(self, '_expertise_hint'):
            expertise_hint = self._expertise_hint or ""

        # Assemble system message
        system_content = (
            self.config.merged_prompt
            + tools_block
            + collab_block
            + expertise_hint
            + context_blocks
        )

        return {
            "role": "system",
            "content": system_content,
        }

    def chat_stream(
        self, 
        history: List[Dict[str, str]], 
        image_path: str = None,
        chat_id: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
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
        
        # Detect user expertise level and cache tone hint for system message
        expertise = detect_expertise(processed_history)
        self._expertise_hint = get_tone_hint(expertise) or ""
        
        base_history = [self._build_system_message()] + processed_history
        
        # Strip thinking from old assistant messages (rolling checkpoint)
        base_history = self._strip_old_thinking(base_history)
        
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
        tool_exec = ToolExecutor(
            allowed_tools=list(self.config.tools),
            allow_shell=self.allow_shell,
            session_id=chat_id,
        )
        
        current_history = list(base_history)
        
        # Build knowledge graph from conversation history
        if not self.graph.nodes:
            # Try loading persisted graph from disk first
            saved_graph = chat_store.load_graph(chat_id) if chat_id else None
            if saved_graph:
                self.graph = ConversationGraph.from_dict(saved_graph)
            else:
                self.graph = ConversationGraph.from_messages(processed_history)
        # Set graph reference for graph-backed save_notes
        _set_graph_ref(self.graph)
        # Capture user intent from the latest message
        if processed_history and processed_history[-1].get("role") == "user":
            intent_id = self.graph.add_user_intent(processed_history[-1]["content"])
            # Initialize/Update Working Memory with the latest intent
            self.graph.update_working_memory(
                intent=processed_history[-1]["content"][:200],
                state="Starting new reasoning turn..."
            )
        
        # Inject current working image context for multi-turn image editing
        _session_globals = _get_sandbox_session(chat_id).globals if chat_id else _sandbox_globals
        _cimg = _session_globals.get('_current_image_path')
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
        _is_continue = (
            len(last_user_msg.split()) <= 6
            and any(w in {"continue", "proceed", "keep", "go", "carry", "resume", "more", "next"}
                    for w in last_user_msg.split())
        ) if last_user_msg else False
        if _is_continue and user_msg_count > 1:
            # Build continuation context — session notes are the primary
            # working memory. Knowledge map is already in system prompt via
            # ContextAssembler, so no need to duplicate it here.
            _notes = get_session_notes()
            _continuation_ctx = "\n\n[CONTINUATION: Resume your previous work.\n"
            if _notes:
                _continuation_ctx += f"Your working notes:\n{_notes}\n"
            _continuation_ctx += "Pick up where you left off. Do NOT restart or re-read files already processed.]"
            for i in range(len(current_history) - 1, -1, -1):
                if current_history[i].get('role') == 'user':
                    current_history[i] = {
                        **current_history[i],
                        'content': current_history[i]['content'] + _continuation_ctx
                    }
                    break
        # else: non-continue — session notes are loaded via ContextAssembler
        # into the working_notes memory block (system prompt), no inline injection needed
        
        # ── AGENTS.md / .cursorrules detection (first turn only) ──
        if user_msg_count <= 1:
            _convention_files = ["AGENTS.md", "CLAUDE.md", ".cursorrules", ".github/copilot-instructions.md"]
            _project_roots: set = set()
            # Extract project root candidates from file paths mentioned in messages
            for msg in processed_history:
                for token in msg.get("content", "").split():
                    if "/" in token and not token.startswith("http"):
                        # Clean potential file paths
                        clean = token.strip("\"'`[](),;:")
                        p = Path(clean)
                        if p.is_absolute() and len(p.parts) >= 3:
                            # Walk up to find a directory with common project markers
                            for ancestor in [p.parent] + list(p.parents):
                                if any((ancestor / m).exists() for m in [".git", "package.json", "Cargo.toml", "pyproject.toml", "go.mod"]):
                                    _project_roots.add(str(ancestor))
                                    break
            # Also check cwd
            _project_roots.add(str(Path.cwd()))
            _convention_ctx = ""
            for root in list(_project_roots)[:3]:
                for cf in _convention_files:
                    cf_path = Path(root) / cf
                    if cf_path.exists() and cf_path.stat().st_size < 8000:
                        try:
                            content = cf_path.read_text(encoding="utf-8")[:4000]
                            _convention_ctx += f"\n[Project convention file: {cf_path}]\n{content}\n"
                            logger.info(f"Loaded project convention file: {cf_path}")
                        except Exception:
                            pass
            if _convention_ctx:
                # Inject into last user message as context
                for i in range(len(current_history) - 1, -1, -1):
                    if current_history[i].get('role') == 'user':
                        current_history[i] = {
                            **current_history[i],
                            'content': current_history[i]['content'] + _convention_ctx
                        }
                        break

        accumulated_response_text = ""  # Track ALL text generated across rounds for anti-repeat
        _tool_activity_log: List[str] = []  # Auto-track tool calls for continuation context
        self._trunc_retry_count = 0  # Reset truncation retry guard per run
        
        def _is_cancelled():
            return cancel_event is not None and cancel_event.is_set()

        for tool_round in range(MAX_TOOL_ROUNDS):
            if _is_cancelled():
                logger.info("Agent cancelled before tool round %d", tool_round)
                yield json.dumps({"type": "done", "data": "cancelled"})
                return
            # ── 0. Refresh Context & Working Memory ──
            self.graph.set_round(tool_round)
            # Inject latest knowledge graph into system prompt
            current_history[0] = self._build_system_message(tool_round=tool_round)
            
            # Observation masking: progressively compress old tool results
            # to prevent context distraction in long tool sessions
            if tool_round >= 2:
                current_history = self._mask_old_observations(current_history, keep_recent=3)
            
            # ── 1. Stream Model Generation ──
            accumulated = ""
            thinking_done = False
            is_retry_gen = False  # set True during parse-retry re-generations
            yield json.dumps({"type": "status", "data": _pick_loading_msg()})
            
            # Resolve adaptive sampling parameters for this round
            _user_msg = history[-1]["content"] if history and history[-1].get("role") == "user" else ""
            _sampling = AdaptiveSampler.resolve(
                cartridge_ids=getattr(self.config, 'active_cartridge_ids', None),
                user_message=_user_msg,
                tool_round=tool_round,
                is_retry=False,
                override_temp=getattr(self.config, 'suggested_temperature', None),
                override_top_p=getattr(self.config, 'suggested_top_p', None),
            )

            # Retry wrapper: one automatic retry on transient inference failures
            # Multi-turn vision: always provide the most current image to the VLM.
            # Round 0: prefer user-attached image, fall back to current working image.
            # Round N>0: use current working image (may have been updated by tools).
            _cimg_now = _session_globals.get('_current_image_path')
            _cimg_valid = _cimg_now if _cimg_now and Path(_cimg_now).exists() else None
            if tool_round == 0:
                _active_image = image_path or _cimg_valid
            else:
                _active_image = _cimg_valid

            def _stream_with_retry():
                try:
                    yield from self.model_client.stream_generate(
                        messages=current_history,
                        image=_active_image,
                        max_tokens=self.config.suggested_tokens,
                        thinking=self.config.suggested_thinking,
                        temperature=_sampling.temperature,
                        top_p=_sampling.top_p,
                    )
                except Exception as inf_err:
                    logger.warning(f"Inference failed (attempt 1): {inf_err}, retrying...")
                    import gc; gc.collect()
                    yield from self.model_client.stream_generate(
                        messages=current_history,
                        image=_active_image,
                        max_tokens=self.config.suggested_tokens,
                        thinking=self.config.suggested_thinking,
                        temperature=_sampling.temperature,
                        top_p=_sampling.top_p,
                    )

            _tool_tag_seen = False
            _think_repeat_check_len = 0  # last length at which we checked for repeats
            _think_repeat_broken = False
            for chunk in _stream_with_retry():
                if _is_cancelled():
                    logger.info("Agent cancelled during model generation (round %d)", tool_round)
                    yield json.dumps({"type": "done", "data": "cancelled"})
                    return
                accumulated += chunk
                
                # ── Thinking repetition detection ──
                # Every 500 new chars of thinking, check if a 150+ char block repeats 3+ times
                if not thinking_done and not _think_repeat_broken and "<think>" in accumulated and "</think>" not in accumulated:
                    think_content = accumulated
                    if "<think>" in think_content:
                        think_content = think_content[think_content.index("<think>") + 7:]
                    if len(think_content) - _think_repeat_check_len > 500:
                        _think_repeat_check_len = len(think_content)
                        # Check for repeated blocks: take a 150-char window and count occurrences
                        if len(think_content) > 600:
                            # Sample from the middle of the content
                            mid = len(think_content) // 2
                            sample = think_content[mid:mid+150].strip()
                            if len(sample) > 80 and think_content.count(sample) >= 3:
                                logger.warning(
                                    f"Thinking repetition detected (round {tool_round}): "
                                    f"'{sample[:60]}...' repeated {think_content.count(sample)}x — force-breaking"
                                )
                                _think_repeat_broken = True
                                # Force-close the thinking and let the agent produce an answer
                                accumulated += "\n</think>\n"
                                thinking_done = True
                                yield json.dumps({"type": "think_end"})
                                break
                
                # Check for thinking completion to stream actual content
                if "</think>" in accumulated:
                    if not thinking_done:
                        thinking_done = True
                        yield json.dumps({"type": "think_end"})
                        # ── Update Working Memory with thinking ──
                        thinking_text, _ = parse_thinking(accumulated)
                        if thinking_text:
                            wm = self.graph.nodes.get("working_memory")
                            if wm:
                                self.graph.update_working_memory(intent=wm.content, state=thinking_text[:500])
                                
                        # Periodic episodic summarization
                        if tool_round > 0 and tool_round % 5 == 0:
                            self.graph.add_episode(f"Consolidated progress after {tool_round} tool rounds.")
                    
                    _, answer = parse_thinking(accumulated)
                    # Once tool call tags appear in the answer, stop streaming
                    # visible tokens — the backend will handle tool execution
                    if '<tool_call>' in answer or '<|tool_call|>' in answer or '<function=' in answer:
                        if not _tool_tag_seen:
                            _tool_tag_seen = True
                            yield json.dumps({"type": "status", "data": _pick_loading_msg(tool=True)})
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
                    if '<tool_call>' in accumulated or '<|tool_call|>' in accumulated or '<function=' in accumulated:
                        if not _tool_tag_seen:
                            _tool_tag_seen = True
                            yield json.dumps({"type": "status", "data": _pick_loading_msg(tool=True)})
                    else:
                        yield json.dumps({"type": "token", "data": chunk})
            
            # ── Handle thinking repetition break ──
            if _think_repeat_broken:
                logger.info("Recovering from thinking loop — injecting recovery nudge")
                # Extract whatever useful thinking existed before the loop
                thought, _ = parse_thinking(accumulated)
                _summary = thought[:300] if thought else "(thinking loop detected)"
                current_history.append({"role": "assistant", "content": f"<think>{_summary}</think>"})
                current_history.append({"role": "user", "content": (
                    "[SYSTEM] Your reasoning entered a repetition loop. Stop re-analyzing. "
                    "Based on your analysis so far, take the SINGLE most important next action. "
                    "If the task is already complete from a previous tool call, just confirm and STOP. "
                    "Do NOT re-explain what you already figured out."
                )})
                yield json.dumps({"type": "status", "data": "Refocusing..."})
                continue
            
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
                    # Guard against infinite truncation loops (max 3 retries)
                    _trunc_retries = getattr(self, '_trunc_retry_count', 0)
                    if _trunc_retries >= 3:
                        logger.warning("Max truncation retries reached — delivering partial text")
                        clean_text = re.sub(r'<tool_call>[\s\S]*$', '', text, flags=re.IGNORECASE).strip()
                        if clean_text:
                            # Just deliver whatever text was generated before the tool call
                            yield json.dumps({"type": "token", "data": clean_text})
                        break
                    self._trunc_retry_count = _trunc_retries + 1
                    
                    # Detect WHICH tool was being called to give targeted recovery advice
                    _partial_call = text[text.rfind('<tool_call>'):]
                    _is_ui_tool = any(kw in _partial_call for kw in ['request_user_input', 'widget_type', 'config'])
                    
                    if _is_ui_tool:
                        yield json.dumps({"type": "status", "data": "Widget config too large — simplifying…"})
                        clean_text = re.sub(r'<tool_call>[\s\S]*$', '', text, flags=re.IGNORECASE).strip()
                        current_history.append({"role": "assistant", "content": clean_text or "(attempted tool call)"})
                        current_history.append({"role": "user", "content": (
                            "Tool call truncated. Retry with: prompt ≤10 words, ≤4 fields/options, no narration before the call, minimal <think>."
                        )})
                    else:
                        yield json.dumps({"type": "status", "data": "Code was too long — requesting shorter version…"})
                        clean_text = re.sub(r'<tool_call>[\s\S]*$', '', text, flags=re.IGNORECASE).strip()
                        current_history.append({"role": "assistant", "content": clean_text or "(attempted tool call)"})
                        current_history.append({"role": "user", "content": (
                            "Tool call truncated. Retry with: code <30 lines, break into smaller steps, use library functions."
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
                    
                    # Re-generate with thinking visible to user (retry sampling)
                    _retry_sampling = AdaptiveSampler.resolve(
                        cartridge_ids=getattr(self.config, 'active_cartridge_ids', None),
                        user_message=_user_msg, tool_round=tool_round, is_retry=True,
                        override_temp=getattr(self.config, 'suggested_temperature', None),
                        override_top_p=getattr(self.config, 'suggested_top_p', None),
                    )
                    accumulated = ""
                    thinking_done = False
                    for chunk in self.model_client.stream_generate(
                        messages=current_history,
                        max_tokens=self.config.suggested_tokens,
                        thinking=self.config.suggested_thinking,
                        temperature=_retry_sampling.temperature,
                        top_p=_retry_sampling.top_p,
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
                # Strip Qwen3-Coder XML format tags
                clean_text = re.sub(r'<function=\w+>[\s\S]*?</function>', '', clean_text)
                clean_text = re.sub(r'<function=\w+>[\s\S]*$', '', clean_text)
                # Strip leaked </tool_call> tags with trailing text
                clean_text = re.sub(r'</tool_call>[\s\S]*', '', clean_text, flags=re.IGNORECASE)
                # Strip leaked </think> tags
                clean_text = re.sub(r'</think>', '', clean_text, flags=re.IGNORECASE)
                # Strip leaked <answer> tags (Qwen3.5 sometimes wraps answers)
                clean_text = re.sub(r'</?answer>', '', clean_text, flags=re.IGNORECASE)
                # Strip trailing JSON closers leaked from tool calls (e.g. '"}}')
                clean_text = re.sub(r'"\s*\}\s*\}\s*$', '', clean_text, flags=re.MULTILINE)
                clean_text = clean_text.strip()
                if not clean_text and text.strip():
                    clean_text = text.strip()
                # Auto-save meaningful progress for continuation
                if _tool_activity_log:
                    _auto_notes = "Progress: " + " → ".join(_tool_activity_log[-8:])
                    if clean_text:
                        _auto_notes += f"\nLast response: {clean_text[:200]}"
                    _save_session_notes(notes=_auto_notes, category="progress", mode="replace")
                yield json.dumps({"type": "done", "data": clean_text})
                break
                
            # ── 3. Tool Execution Phase ──
            tool_name = tool_req.get("name")
            tool_args = tool_req.get("arguments", {})
            # Model sometimes outputs flat JSON without an "arguments" key: 
            # e.g., {"name": "request_user_input", "widget_type": "form", ...}
            if not tool_args and len(tool_req) > 1:
                tool_args = {k: v for k, v in tool_req.items() if k != "name" and k != "arguments"}
            
            # Detect identical/near-identical code re-submissions (loop detection)
            if tool_exec.check_code_dedup(tool_name, tool_args):
                logger.warning("Identical/near-identical code re-submission detected, forcing stop")
                yield json.dumps({"type": "status", "data": "Detected repeated code — stopping loop."})
                current_history.append({"role": "assistant", "content": "(repeated identical code)"})
                current_history.append({"role": "user", "content": (
                    "[SYSTEM] You just submitted nearly IDENTICAL code to what you already ran. This is a loop. "
                    "The previous output is ALREADY VISIBLE to the user. "
                    "STOP calling tools. Summarize what you've done and STOP."
                )})
                tool_exec.consecutive_failures = max(tool_exec.consecutive_failures, 3)
                continue
            
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
                _META_KEYS = {"widget_type", "config", "persistent_id"}
                for k, v in tool_args.items():
                    if k not in _META_KEYS and k not in config:
                        config[k] = v
                persistent_id = tool_args.get("persistent_id") or config.get("persistent_id")
                config.pop("persistent_id", None)  # Don't send as config key
                
                # Validate widget config — check form BEFORE choice so that
                # a form call that was misclassified as choice doesn't get a
                # confusing "choice needs options" error.
                _validation_error = None
                if widget_type == "form" and not config.get("fields"):
                    _validation_error = (
                        f"Error: form widget (received widget_type='{widget_type}') requires 'fields' — "
                        "an array of {{\"name\": str, \"label\": str, \"type\": str}} objects. "
                        "Example: {\"name\": \"request_user_input\", \"arguments\": {\"widget_type\": \"form\", "
                        "\"config\": {\"prompt\": \"Fill out\", \"fields\": ["
                        "{\"name\": \"title\", \"label\": \"Title\", \"type\": \"text\"}]}}}"
                    )
                elif widget_type == "choice" and not config.get("options"):
                    _validation_error = (
                        f"Error: choice widget (received widget_type='{widget_type}') requires 'options' — "
                        "an array of {{\"label\": str, \"value\": str}} objects. "
                        "Example: {\"name\": \"request_user_input\", \"arguments\": {\"widget_type\": \"choice\", "
                        "\"config\": {\"prompt\": \"Pick one\", \"options\": ["
                        "{\"label\": \"Option A\", \"value\": \"a\"}, {\"label\": \"Option B\", \"value\": \"b\"}]}}}"
                    )
                if _validation_error:
                    tool_result = _validation_error
                    sandbox_images = []
                    html_artifact = ""
                    result_data = {"name": tool_name, "result": tool_result, "images": []}
                    yield json.dumps({"type": "tool_result", "data": result_data})
                    current_history.append({"role": "assistant", "content": text.strip() or f"[Called {tool_name}: {widget_type}]"})
                    current_history.append({"role": "user", "content": f"Tool result for {tool_name}: {tool_result}"})
                    continue
                
                # Check if a persistent widget already exists for this persistent_id
                existing_wid = _lookup_persistent_widget(persistent_id) if persistent_id else None
                
                if existing_wid:
                    # Update existing persistent widget in-place
                    widget_id = existing_wid
                    event_data = {
                        "widget_id": widget_id, "widget_type": widget_type,
                        "persistent_id": persistent_id, "update": True, **config
                    }
                    # Reset the event for the existing widget so we can wait again
                    with _interactive_lock:
                        entry = _interactive_registry.get(widget_id)
                        if entry:
                            entry["event"] = threading.Event()
                            entry["response"] = None
                            entry["dismissed"] = False
                            event = entry["event"]
                        else:
                            event = _register_interactive(widget_id, persistent_id)
                    yield json.dumps({"type": "interactive_update", "data": event_data})
                else:
                    widget_id = str(uuid.uuid4())
                    event_data = {
                        "widget_id": widget_id, "widget_type": widget_type, **config
                    }
                    if persistent_id:
                        event_data["persistent_id"] = persistent_id
                    
                    # Embed is display-only — no response needed
                    if widget_type == "embed":
                        yield json.dumps({"type": "interactive", "data": event_data})
                        tool_result = "Embed displayed to user."
                        sandbox_images = []
                        html_artifact = ""
                        result_data = {"name": tool_name, "result": tool_result, "images": []}
                        yield json.dumps({"type": "tool_result", "data": result_data})
                        current_history.append({"role": "assistant", "content": text.strip() or "[Requesting input...]"})
                        current_history.append({"role": "user", "content": f"Tool result for {tool_name}: {tool_result}"})
                        continue
                    
                    event = _register_interactive(widget_id, persistent_id)
                    yield json.dumps({"type": "interactive", "data": event_data})
                
                # Wait for user response (shared for new + updated persistent widgets)
                # User may be actively editing — don't time out prematurely.
                # Keepalive pings prevent SSE disconnection.
                KEEPALIVE_INTERVAL = 15  # seconds between pings
                MAX_WAIT = 86400  # 24h — effectively no timeout for user interaction
                elapsed = 0
                while elapsed < MAX_WAIT:
                    if event.wait(timeout=KEEPALIVE_INTERVAL):
                        break  # User responded
                    elapsed += KEEPALIVE_INTERVAL
                    yield json.dumps({"type": "keepalive", "data": {"waiting_for": widget_id}})
                state = _get_and_reset_interactive(widget_id)
                if state.get("dismissed"):
                    tool_result = "User dismissed/skipped the input widget. Continue without this input."
                elif state.get("finalized"):
                    resp = state.get("response")
                    tool_result = f"User FINALIZED this widget. Final response: {json.dumps(resp) if isinstance(resp, (dict, list)) else str(resp)}"
                elif state.get("response") is not None:
                    resp = state["response"]
                    prefix = ""
                    if persistent_id:
                        prefix = f"[Persistent widget '{persistent_id}' — widget stays active for further edits] "
                    tool_result = f"{prefix}User response: {json.dumps(resp) if isinstance(resp, (dict, list)) else str(resp)}"
                else:
                    tool_result = "User input timed out. Continue without this input."
                sandbox_images = []
                html_artifact = ""
                
                result_data = {"name": tool_name, "result": tool_result, "images": []}
                yield json.dumps({"type": "tool_result", "data": result_data})
                current_history.append({"role": "assistant", "content": text.strip() or "[Requesting input...]"})
                current_history.append({"role": "user", "content": f"Tool result for {tool_name}: {tool_result}"})
                continue
            
            # ── Tool execution via ToolExecutor ──
            tool_result, sandbox_images, html_artifact = tool_exec.execute(tool_name, tool_args)

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
                    tool_result, sandbox_images, html_artifact = tool_exec.execute_approved(cmd)
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
                if chat_id:
                    chat_store.save_graph(chat_id, self.graph.to_dict())
            except Exception as kg_err:
                logger.debug(f"Knowledge graph update failed: {kg_err}")
            
            # ── 4. Build enriched context for next round ──
            result_context = tool_exec.build_result_context(
                tool_name, tool_args, tool_result,
                sandbox_images, html_artifact,
                tool_round, MAX_TOOL_ROUNDS,
                _get_sandbox_session(chat_id).globals if chat_id else _sandbox_globals,
            )
            if tool_exec.should_force_stop:
                yield json.dumps({"type": "status", "data": "Multiple tools failed. Generating final response…"})
                
            # Append interaction to history — strip tool call tags from assistant text
            # Handles both JSON format and Qwen3-Coder XML format
            history_text = re.sub(r'<tool_call>[\s\S]*?</tool_call>', '', text, flags=re.IGNORECASE)
            history_text = re.sub(r'<tool_call>[\s\S]*$', '', history_text, flags=re.IGNORECASE)
            history_text = re.sub(r'<\|tool_call\|>[\s\S]*$', '', history_text)
            # Also strip native XML function tags that may appear outside <tool_call>
            history_text = re.sub(r'<function=\w+>[\s\S]*?</function>', '', history_text)
            history_text = re.sub(r'<function=\w+>[\s\S]*$', '', history_text)
            history_text = history_text.strip()
            if not history_text:
                # Build a meaningful summary instead of "(used tool)" which the model echoes
                _arg_hint = ""
                if tool_name in ("read_file", "write_file", "edit_file"):
                    _arg_hint = f": {tool_args.get('path', '')}"
                elif tool_name in ("list_directory",):
                    _arg_hint = f": {tool_args.get('path', '')}"
                elif tool_name in ("grep_code",):
                    _arg_hint = f": pattern={tool_args.get('pattern', '')[:60]}"
                elif tool_name in ("run_command",):
                    _arg_hint = f": {tool_args.get('command', '')[:60]}"
                elif tool_name in ("execute_python",):
                    _arg_hint = f" ({len(tool_args.get('code', ''))} chars)"
                elif tool_name in ("request_user_input",):
                    _arg_hint = f": {tool_args.get('widget_type', 'input')}"
                elif tool_name in ("search_files",):
                    _arg_hint = f": {tool_args.get('pattern', '')}"
                history_text = f"[Called {tool_name}{_arg_hint}]"
            current_history.append({"role": "assistant", "content": history_text})
            
            # Auto-track tool activity for continuation context
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
            elif tool_name in ("request_user_input",):
                _wt = tool_args.get('config', {}).get('widget_type', tool_args.get('widget_type', 'input'))
                _tool_log_entry += f"({_wt}→got response)"
            elif tool_name in ("execute_python",):
                _ok = "error" not in str(tool_result).lower()[:100] and "Traceback" not in str(tool_result)[:100]
                _tool_log_entry += f"({'ok' if _ok else 'error'})"
                if html_artifact:
                    _tool_log_entry += "[HTML rendered]"
            _tool_activity_log.append(_tool_log_entry)
            
            current_history.append({"role": "user", "content": result_context})
            
            if tool_exec.should_force_stop:
                # Stream the final response instead of blocking generate
                final_text = ""
                for chunk in self.model_client.stream_generate(
                    messages=current_history,
                    max_tokens=self.config.suggested_tokens,
                    thinking=False,
                    temperature=_sampling.temperature,
                    top_p=_sampling.top_p,
                ):
                    final_text += chunk
                    yield json.dumps({"type": "token", "data": chunk})
                _, clean_final = parse_thinking(final_text)
                yield json.dumps({"type": "done", "data": clean_final})
                break
        else:
            # Auto-save meaningful progress for continuation
            if _tool_activity_log:
                _auto_notes = "Progress: " + " → ".join(_tool_activity_log[-8:])
                _save_session_notes(notes=_auto_notes, category="progress", mode="replace")
            # Hit max rounds — produce a final summary (streaming)
            current_history.append({"role": "user", "content": "You have reached the maximum number of tool rounds. Summarize your findings and give your best final answer with the information gathered so far. Tell the user they can say 'continue' to keep going."})
            _final_sampling = AdaptiveSampler.resolve(
                cartridge_ids=getattr(self.config, 'active_cartridge_ids', None),
                user_message=_user_msg, tool_round=MAX_TOOL_ROUNDS,
                override_temp=getattr(self.config, 'suggested_temperature', None),
                override_top_p=getattr(self.config, 'suggested_top_p', None),
            )
            final_text = ""
            for chunk in self.model_client.stream_generate(
                messages=current_history,
                max_tokens=self.config.suggested_tokens,
                thinking=False,
                temperature=_final_sampling.temperature,
                top_p=_final_sampling.top_p,
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
                    CartridgeContext.update_from_chat(cid, history, chat_title=title, graph=self.graph)
                    GlobalProfile.update_from_chat(cid, history)
                    # Merge session graph into cartridge-level persistent graph
                    try:
                        graph_dir = Path.home() / ".kasset" / "graphs"
                        persistent = PersistentGraph(store_path=str(graph_dir / f"{cid}.graph.json"))
                        persistent.merge_session(self.graph)
                        persistent.save()
                    except Exception as pg_err:
                        logger.debug(f"Persistent graph merge failed: {pg_err}")
            except Exception as e:
                logger.warning(f"Context update failed: {e}")

        threading.Thread(target=_post_conversation_tasks, daemon=True).start()

        # Cleanup temp image files created during inference
        self.model_client.cleanup_temp_files()
