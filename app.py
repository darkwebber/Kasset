"""
app.py — Qwen 3.5 9B Chat UI (vision + text + tools)
Requires model_server.py running on port 7861.

Run order:
    1.  python model_server.py
    2.  python app.py
"""

import re
import json
import os
import ast
import math
import logging
import time
import shlex
import shutil
import operator
import platform
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import gradio as gr
from gradio_client import Client
from utils import validate_image_file, MAX_IMAGE_SIZE_MB

# Handle different gradio_client versions
try:
    from gradio_client.exceptions import NetworkError
except ImportError:
    # Fallback for older versions
    NetworkError = Exception

# ──────────────────────────────────────────
# 1. LOGGING AND CONFIGURATION
# ──────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SERVER_URL = "http://127.0.0.1:7861"
MAX_HISTORY_LENGTH = 50
VISION_CONTEXT_TURNS = 6     # Only send last N messages for vision tasks (speed optimization)
MAX_RETRIES = 3
RETRY_DELAY = 1.0

# ──────────────────────────────────────────
# 2. CONNECTION MANAGEMENT
# ──────────────────────────────────────────
class ModelServerManager:
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.client: Optional[Client] = None
        self.last_health_check = 0
        self.health_check_interval = 30  # seconds
        
    def is_healthy(self) -> bool:
        """Check if the model server is responsive (lightweight connection test)."""
        try:
            current_time = time.time()
            if current_time - self.last_health_check < self.health_check_interval:
                return self.client is not None
                
            # Lightweight health check — just verify the server accepts connections
            test_client = Client(self.server_url)
            self.last_health_check = current_time
            self.client = test_client
            return True
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            self.client = None
            return False
    
    def get_client(self) -> Client:
        """Get a healthy client connection with retry logic."""
        for attempt in range(MAX_RETRIES):
            try:
                if not self.is_healthy():
                    logger.info(f"Attempting to connect to model server (attempt {attempt + 1}/{MAX_RETRIES})")
                    self.client = Client(self.server_url)
                    logger.info("✅ Connected to model server.")
                return self.client
            except Exception as e:
                logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    raise ConnectionError(f"Failed to connect to model server after {MAX_RETRIES} attempts")

server_manager = ModelServerManager(SERVER_URL)

# ──────────────────────────────────────────
# 3. TOOLS (secure, read-only by default)
# ──────────────────────────────────────────
_ALLOWED_PATHS = lambda: [
    Path.home().resolve(),
    Path(os.getcwd()).resolve(),
    Path(tempfile.gettempdir()).resolve(),
]

def _check_path_access(path_obj: Path) -> str:
    """Return empty string if path is allowed, else an error message."""
    resolved = path_obj.resolve()
    for root in _ALLOWED_PATHS():
        if resolved == root or resolved.is_relative_to(root):
            return ""
    return f"Error: Access denied - path outside allowed directories"


def get_current_time() -> str:
    """Get the current local date and time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")


def list_directory(path: str = ".") -> str:
    """List directory contents with file sizes."""
    try:
        path_obj = Path(path).expanduser().resolve()
        err = _check_path_access(path_obj)
        if err:
            return err
        if not path_obj.exists():
            return f"Error: Path '{path}' does not exist"
        if not path_obj.is_dir():
            return f"Error: '{path}' is not a directory"

        entries = sorted(path_obj.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = []
        for e in entries[:40]:
            if e.is_dir():
                lines.append(f"  [dir]  {e.name}/")
            else:
                size = e.stat().st_size
                unit = "B"
                if size > 1024 * 1024:
                    size, unit = size / (1024 * 1024), "MB"
                elif size > 1024:
                    size, unit = size / 1024, "KB"
                lines.append(f"  {size:>6.0f} {unit}  {e.name}")
        header = f"Contents of {path_obj} ({len(entries)} items)"
        if len(entries) > 40:
            lines.append(f"  ... and {len(entries) - 40} more")
        return header + "\n" + "\n".join(lines)
    except Exception as e:
        return f"Error: {str(e)}"


def get_system_info() -> str:
    """Get system overview: OS, hardware, disk, uptime."""
    try:
        info = [
            f"OS:       {platform.system()} {platform.release()} ({platform.machine()})",
            f"Hostname: {platform.node()}",
            f"Python:   {platform.python_version()}",
        ]
        total, used, free = shutil.disk_usage("/")
        info.append(f"Disk (/): {used // (1024**3)}GB used, {free // (1024**3)}GB free of {total // (1024**3)}GB")
        try:
            up = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5)
            if up.returncode == 0:
                info.append(f"Uptime:   {up.stdout.strip()}")
        except Exception:
            pass
        return "\n".join(info)
    except Exception as e:
        return f"Error: {str(e)}"


def search_files(pattern: str, directory: str = "~") -> str:
    """Search for files matching a glob pattern (max 50 results)."""
    try:
        dir_path = Path(directory).expanduser().resolve()
        err = _check_path_access(dir_path)
        if err:
            return err
        if not dir_path.exists() or not dir_path.is_dir():
            return f"Error: '{directory}' is not a valid directory"

        matches = list(dir_path.rglob(pattern))[:50]
        if not matches:
            return f"No files matching '{pattern}' in {directory}"
        lines = [str(m.relative_to(dir_path)) for m in matches]
        suffix = "\n  ... (results capped at 50)" if len(matches) == 50 else ""
        return f"Found {len(matches)} match(es) in {dir_path}:\n" + "\n".join(f"  {l}" for l in lines) + suffix
    except Exception as e:
        return f"Error: {str(e)}"


def read_file_content(path: str, max_lines: int = 100) -> str:
    """Read a text file (max 100 lines / 50KB)."""
    try:
        fp = Path(path).expanduser().resolve()
        err = _check_path_access(fp)
        if err:
            return err
        if not fp.exists():
            return f"Error: '{path}' does not exist"
        if not fp.is_file():
            return f"Error: '{path}' is not a file"
        size = fp.stat().st_size
        if size > 50 * 1024:
            return f"Error: File too large ({size / 1024:.0f}KB, max 50KB). Try run_command with head/tail."
        try:
            content = fp.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "Error: Binary file detected - cannot display"
        lines = content.splitlines()
        max_lines = min(max(1, int(max_lines)), 200)
        if len(lines) > max_lines:
            content = "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
        return f"=== {fp.name} ({len(lines)} lines, {size} bytes) ===\n{content}"
    except Exception as e:
        return f"Error: {str(e)}"


def calculate(expression: str) -> str:
    """Safe math evaluator — supports +, -, *, /, **, %, sqrt, log, sin, cos, pi, e, etc."""
    _OPS = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv,
        ast.USub: operator.neg, ast.UAdd: operator.pos,
    }
    _FUNCS = {
        "abs": abs, "round": round, "min": min, "max": max, "pow": pow,
        "int": int, "float": float,
        "sqrt": math.sqrt, "log": math.log, "log10": math.log10, "log2": math.log2,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "asin": math.asin, "acos": math.acos, "atan": math.atan,
        "ceil": math.ceil, "floor": math.floor, "factorial": math.factorial,
    }
    _CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf}

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, complex)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
        if isinstance(node, ast.Name) and node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ValueError(f"Unsupported: {ast.dump(node)}")

    try:
        result = _eval(ast.parse(expression.strip(), mode="eval"))
        if isinstance(result, float) and result == int(result) and abs(result) < 1e15:
            return str(int(result))
        return str(result)
    except ZeroDivisionError:
        return "Error: Division by zero"
    except Exception as e:
        return f"Error: {e}"


# Whitelisted commands — read-only operations only
SAFE_COMMANDS = frozenset({
    # filesystem (read-only)
    "ls", "find", "file", "stat", "wc", "cat", "head", "tail", "grep",
    "du", "df", "tree", "realpath", "dirname", "basename",
    "sort", "uniq", "diff", "comm", "cut", "tr", "fold", "fmt",
    "xxd", "od", "strings", "md5", "shasum", "cksum",
    "xattr", "lsof",
    # system info
    "uname", "hostname", "whoami", "date", "uptime", "pwd", "id",
    "ps", "top", "sw_vers", "system_profiler", "sysctl", "vm_stat",
    "last", "w", "groups",
    # network info (read-only)
    "ifconfig", "ping", "dig", "nslookup", "curl", "netstat",
    "scutil", "networksetup",
    # macOS utilities (read-only)
    "mdfind", "mdls", "diskutil", "pmset", "ioreg",
    "pbpaste", "log", "csrutil", "spctl",
    "open", "say",
    # misc safe
    "echo", "which", "env", "printenv", "locale", "cal", "bc",
})

# Explicitly blocked — never allow even if somehow whitelisted
_BLOCKED_ARGS = frozenset({
    "sudo", "rm", "rmdir", "mkfs", "dd", "format",
    "shutdown", "reboot", "halt", "kill", "killall",
    "mv", "cp", "chmod", "chown", "chgrp", "mktemp",
})


def run_command(command: str) -> str:
    """Run whitelisted shell commands (read-only, 10s timeout, pipes allowed)."""
    try:
        # Pre-process: strip stderr redirects (handled at Python level)
        cleaned = re.sub(r'2>\s*/dev/null', '', command)

        # Block dangerous shell operators (but NOT pipes — we handle those safely)
        for bad in ["&&", "||", ";", "`", "$(", ">>", ">"]:
            # Skip > check if it's part of 2>&1 (harmless, we just ignore stderr merge)
            if bad == ">" and "2>&1" in cleaned:
                cleaned = cleaned.replace("2>&1", "")
                continue
            if bad in cleaned:
                return f"Error: Shell operator '{bad}' is not allowed for security"

        # Split on pipes and validate every stage
        stages = [s.strip() for s in cleaned.split("|")]
        parsed_stages = []
        for stage in stages:
            if not stage:
                continue
            parts = shlex.split(stage)
            if not parts:
                return "Error: Empty command in pipe chain"
            if parts[0] not in SAFE_COMMANDS:
                return (f"Error: '{parts[0]}' is not allowed.\n"
                        f"Allowed: {', '.join(sorted(SAFE_COMMANDS))}")
            if any(arg in _BLOCKED_ARGS for arg in parts):
                return "Error: Blocked keyword detected"
            parsed_stages.append(parts)

        if not parsed_stages:
            return "Error: Empty command"

        # Execute as a safe pipe chain (no shell=True)
        home = str(Path.home())
        run_env = {**os.environ, "LANG": "en_US.UTF-8"}
        suppress_stderr = "2>" in command  # original command had stderr redirect
        prev_stdout = None

        for i, parts in enumerate(parsed_stages):
            proc = subprocess.run(
                parts,
                input=prev_stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL if suppress_stderr else subprocess.PIPE,
                text=True, timeout=10,
                cwd=home, env=run_env,
            )
            prev_stdout = proc.stdout
            if not suppress_stderr and proc.returncode != 0 and proc.stderr:
                prev_stdout += f"\n[exit {proc.returncode}] {proc.stderr.strip()}"

        output = prev_stdout or ""
        if len(output) > 5000:
            output = output[:5000] + "\n... (truncated at 5000 chars)"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out (10s limit)"
    except Exception as e:
        return f"Error: {str(e)}"


AVAILABLE_TOOLS = {
    "get_current_time":  get_current_time,
    "list_directory":    list_directory,
    "get_system_info":   get_system_info,
    "search_files":      search_files,
    "read_file":         read_file_content,
    "run_command":       run_command,
    "calculate":         calculate,
}

def _build_system_prompt() -> str:
    """Build system prompt with current date/time."""
    now = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    return f"""You are Qwen, an advanced multimodal AI assistant running locally on Apple Silicon (MLX).
Current date/time: {now}.

Core behavior:
- Be concise and direct. Avoid unnecessary preamble.
- When shown an image containing a problem, math question, or coding task, **solve it completely** with a full working solution.
- Always wrap code in markdown fenced blocks (e.g. ```python ... ```).
- Use LaTeX ($..$ for inline, $$...$$ for display) for mathematical notation.
- When describing images, focus on what is relevant to the user's question.

Available tools:
1. `get_current_time` -- No arguments. Returns current date/time.
2. `list_directory` -- Args: "path" (string). List files in a directory.
3. `get_system_info` -- No arguments. Returns OS, disk, uptime info.
4. `search_files` -- Args: "pattern" (glob), "directory" (string, default "~"). Find files by name.
5. `read_file` -- Args: "path" (string), "max_lines" (int, default 100). Read a text file.
6. `run_command` -- Args: "command" (string). Run a safe shell command. Pipes are supported (e.g. "du -d 1 -h ~ | sort -rh | head -n 10"). Supports 2>/dev/null for stderr suppression.
7. `calculate` -- Args: "expression" (string). Safe math evaluator. Supports +, -, *, /, **, %, sqrt(), log(), sin(), cos(), pi, e, etc.

Tool call format:
<tool_call>{{"name": "tool_name", "arguments": {{"key": "value"}}}}</tool_call>

Tool rules:
- Use tools proactively when the user asks about their system, files, processes, time, calculations, or anything requiring real data.
- You may chain multiple tool calls across turns to complete a task. After receiving a tool result, if you need more data, call another tool immediately — do NOT ask the user to continue.
- Always use the `calculate` tool for arithmetic instead of computing in your head.
- Do NOT call tools for greetings, general knowledge, coding, or image analysis.
"""

SYSTEM_PROMPT = _build_system_prompt()

# ──────────────────────────────────────────
# 4. HELPERS
# ──────────────────────────────────────────
def _extract_text(content) -> str:
    """Extract plain text from Gradio 6 content (list of typed dicts) or plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def is_image_msg(content) -> bool:
    """Check if content contains an image (handles Gradio 6 list, gr.Image, FileData, dict)."""
    # Gradio 6 list format: [{'component': 'image', 'value': {'path': '...'}}]
    if isinstance(content, list):
        return any(
            isinstance(item, dict) and (
                item.get("component") == "image"
                or item.get("type") in ("image", "file")
            )
            for item in content
        )
    if isinstance(content, gr.Image):
        return True
    if hasattr(content, 'path') and hasattr(content, 'mime_type'):
        return True
    if isinstance(content, dict) and content.get("type") == "image":
        return True
    return False


def get_image_path(content) -> str:
    """Extract file path from any image content format."""
    # Gradio 6 list format: [{'component': 'image', 'value': {'path': '...'}}]
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            # Gradio 6: {'component': 'image', 'value': {'path': '...'}}
            if item.get("component") == "image":
                val = item.get("value", {})
                if isinstance(val, dict):
                    return val.get("path", val.get("url", ""))
                if isinstance(val, str):
                    return val
            # Alt format: {'type': 'image', 'file': {'path': '...'}}
            if item.get("type") in ("image", "file"):
                file_data = item.get("file", item)
                if isinstance(file_data, dict):
                    return file_data.get("path", file_data.get("url", ""))
                if hasattr(file_data, 'path'):
                    return file_data.path
        return ""
    if isinstance(content, gr.Image):
        val = content.value
        return val if isinstance(val, str) else getattr(val, 'path', '')
    if hasattr(content, 'path'):
        return content.path
    if isinstance(content, dict) and "path" in content:
        return content["path"]
    return ""


def _msg_role(msg) -> str:
    """Get role from a ChatMessage or dict."""
    return msg.role if isinstance(msg, gr.ChatMessage) else msg.get("role", "")


def _msg_content(msg):
    """Get content from a ChatMessage or dict, extracting text from Gradio 6 list format."""
    raw = msg.content if isinstance(msg, gr.ChatMessage) else msg.get("content", "")
    return _extract_text(raw)


def _msg_has_metadata(msg) -> bool:
    """Check if a message has metadata (thinking/tool display — model should not see these)."""
    if isinstance(msg, gr.ChatMessage):
        return bool(msg.metadata and msg.metadata.get("title"))
    if isinstance(msg, dict):
        meta = msg.get("metadata")
        return bool(meta and meta.get("title"))
    return False


def history_to_messages(history: List, has_vision: bool = False) -> List[Dict[str, str]]:
    """Convert UI history to clean message dicts for the model server.

    Per Qwen 3.5 best practices: historical model output should only include
    the final output — no thinking content, no formatted HTML.
    Messages with metadata (thinking / tool display) are skipped entirely.

    For vision tasks, only the last VISION_CONTEXT_TURNS messages are sent
    to avoid overwhelming the model with irrelevant context (huge speed win).
    """
    try:
        msgs = [{"role": "system", "content": _build_system_prompt()}]

        # For vision tasks, use a much shorter context window
        if has_vision:
            limited_history = history[-VISION_CONTEXT_TURNS:]
        else:
            limited_history = history[-MAX_HISTORY_LENGTH:] if len(history) > MAX_HISTORY_LENGTH else history

        for i, msg in enumerate(limited_history):
            # Skip thinking / tool-display messages
            if _msg_has_metadata(msg):
                continue

            role = _msg_role(msg)
            content = _msg_content(msg)

            raw_content = msg.content if isinstance(msg, gr.ChatMessage) else msg.get("content", "")

            if is_image_msg(raw_content):
                msgs.append({"role": role, "content": "[IMAGE]"})
            elif content:
                msgs.append({"role": role, "content": content})

        return msgs
    except Exception as e:
        logger.error(f"History conversion error: {e}")
        return [{"role": "system", "content": SYSTEM_PROMPT}]


def call_model(history: List, image_path: str = "", max_new_tokens: int = 4096, enable_thinking: bool = True) -> str:
    """Call the model server with error handling and retry logic."""
    try:
        has_vision = bool(image_path and image_path.strip())
        model_msgs = history_to_messages(history, has_vision=has_vision)
        logger.info(f"call_model: history_len={len(history)}, model_msgs={len(model_msgs)}, "
                    f"vision={has_vision}")
        messages_json = json.dumps(model_msgs)
        client = server_manager.get_client()
        
        t0 = time.time()
        result = client.predict(
            messages_json,
            image_path or "",
            int(max_new_tokens),
            enable_thinking,
            api_name="/chat",
        )
        elapsed = time.time() - t0
        logger.info(f"call_model: round-trip {elapsed:.1f}s")
        return result
    except (NetworkError, ConnectionError, json.JSONDecodeError) as e:
        logger.error(f"Model call failed: {e}")
        return f"❌ **Model Error:** Unable to connect to the model server. Please ensure the server is running on port 7861.\n\nDetails: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in model call: {e}")
        return f"❌ **Unexpected Error:** {str(e)}"


def call_model_stream(history: List, image_path: str = "", max_new_tokens: int = 4096, enable_thinking: bool = True):
    """Stream tokens from the model server. Yields accumulated text."""
    try:
        has_vision = bool(image_path and image_path.strip())
        model_msgs = history_to_messages(history, has_vision=has_vision)
        logger.info(f"call_model_stream: model_msgs={len(model_msgs)}, vision={has_vision}")
        messages_json = json.dumps(model_msgs)
        client = server_manager.get_client()

        job = client.submit(
            messages_json,
            image_path or "",
            int(max_new_tokens),
            enable_thinking,
            api_name="/chat_stream",
        )

        for result in job:
            yield result

    except Exception as e:
        logger.warning(f"Streaming failed, falling back to blocking call: {e}")
        result = call_model(history, image_path, max_new_tokens, enable_thinking)
        yield result


def parse_thinking(raw: str) -> Tuple[str, str]:
    """Extract thinking content from model output.
    
    Supports both Qwen 3.5 style (<think>...</think>) and
    legacy style (<|thinking|>...<|/thinking|>) tags.
    """
    try:
        # Try each tag pair in order of likelihood
        tag_pairs = [
            ("<think>", "</think>"),              # Qwen 3.5 native
            ("<|thinking|>", "<|/thinking|>"),     # legacy / other models
        ]

        for open_tag, close_tag in tag_pairs:
            if close_tag in raw:
                if open_tag in raw:
                    # Full pair found — extract between tags
                    start = raw.index(open_tag) + len(open_tag)
                    end = raw.index(close_tag)
                    thought = raw[start:end].strip()
                    answer = (raw[:raw.index(open_tag)] + raw[end + len(close_tag):]).strip()
                    return thought, answer
                else:
                    # Closing tag only (model sometimes omits the open tag)
                    parts = raw.split(close_tag, 1)
                    thought = parts[0].strip()
                    answer = parts[1].strip()
                    return thought, answer

        # Check for truncated thinking (open tag but no close tag — token exhaustion)
        for open_tag, _ in tag_pairs:
            if open_tag in raw:
                start = raw.index(open_tag) + len(open_tag)
                thought = raw[start:].strip()
                logger.warning(f"Truncated thinking detected ({len(thought)} chars, no close tag)")
                return thought, ""  # empty answer signals truncation

        # No thinking tags found
        return "", raw.strip()
    except Exception as e:
        logger.error(f"Thinking parsing error: {e}")
        return "", raw.strip()


def extract_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """Extract tool call with improved JSON parsing safety."""
    try:
        pattern = r"<tool_call>(.*?)</tool_call>"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            try:
                tool_json = match.group(1).strip()
                return json.loads(tool_json)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse tool call JSON: {e}")
                return None
        return None
    except Exception as e:
        logger.error(f"Tool call extraction error: {e}")
        return None


# ──────────────────────────────────────────
# 5. GRADIO ACTIONS
# ──────────────────────────────────────────
def user_action(message: Dict[str, Any], history: List) -> Tuple[Dict[str, Any], List]:
    """Handle user input with validation and error handling."""
    try:
        text = message.get("text", "").strip() if isinstance(message, dict) else str(message).strip()
        files = message.get("files", []) if isinstance(message, dict) else []

        # Validate image files
        image = None
        if files:
            image_path = files[0]
            is_valid, validation_msg = validate_image_file(image_path)
            if not is_valid:
                logger.warning(f"Image validation failed: {validation_msg}")
                return gr.update(value=None), history + [{
                    "role": "assistant",
                    "content": f"❌ **Image Error:** {validation_msg}"
                }]
            image = image_path

        # Empty message guard — don't trigger bot_action with nothing new
        if not image and not text:
            return gr.update(value=None), history

        # Add messages to history (gr.Image renders the image in the chatbot)
        if image:
            history.append({"role": "user", "content": gr.Image(value=image)})
        if text:
            history.append({"role": "user", "content": text})

        return gr.update(value=None), history
    except Exception as e:
        logger.error(f"User action error: {e}")
        return gr.update(value=None), history + [{
            "role": "assistant",
            "content": f"❌ **Input Error:** {str(e)}"
        }]


def bot_action(history: List, max_tokens: int, thinking_on: bool):
    """Streaming bot response with real-time thinking display.

    Yields updated history progressively so the user sees tokens as they
    arrive instead of waiting for the full response.
    """
    try:
        if not history:
            yield history
            return

        last_role = _msg_role(history[-1])
        if last_role != "user":
            yield history
            return

        # Find image from CURRENT turn
        last_assistant_idx = max(
            (i for i, m in enumerate(history) if _msg_role(m) == "assistant"),
            default=-1,
        )
        image_path = ""
        for i, msg in enumerate(history):
            raw = msg.content if isinstance(msg, gr.ChatMessage) else msg.get("content", "")
            role = _msg_role(msg)
            if role == "user" and is_image_msg(raw):
                if i > last_assistant_idx:
                    image_path = get_image_path(raw)
                    break

        # Snapshot history before we start appending
        base_history = list(history)

        t0 = time.time()
        accumulated = ""
        token_count = 0
        thinking_done = False

        for full_text in call_model_stream(base_history, image_path, max_tokens, thinking_on):
            accumulated = full_text
            token_count += 1

            # Throttle UI updates (every 3 tokens)
            if token_count % 3 != 0:
                continue

            # ── Real-time streaming display ──
            if "</think>" in accumulated:
                # Thinking complete — stream only the answer text
                # (the thinking accordion is added once in post-processing)
                if not thinking_done:
                    thinking_done = True
                _, answer = parse_thinking(accumulated)
                if answer.strip():
                    yield base_history + [{"role": "assistant", "content": answer}]
            elif thinking_on:
                # Still thinking — show single pending indicator
                content = accumulated
                if "<think>" in content:
                    content = content[content.index("<think>") + len("<think>"):]
                content = content.strip()
                if content:
                    yield base_history + [gr.ChatMessage(
                        role="assistant", content=content,
                        metadata={"title": "🧠 Thinking...", "status": "pending"},
                    )]
            else:
                # CoT disabled — streaming answer directly
                if accumulated.strip():
                    yield base_history + [{"role": "assistant", "content": accumulated}]

        gen_time = time.time() - t0

        # ── Post-stream processing ──────────────────
        if not accumulated:
            yield base_history + [{"role": "assistant", "content": "❌ **Error:** No response received."}]
            return

        if accumulated.startswith("❌ **"):
            yield base_history + [{"role": "assistant", "content": accumulated}]
            return

        # Final parse
        thought, text = parse_thinking(accumulated)

        final = list(base_history)
        if thought:
            is_truncated = not text
            final.append(gr.ChatMessage(
                role="assistant", content=thought,
                metadata={
                    "title": "🧠 Thinking" + (" ⚠️ truncated" if is_truncated else ""),
                    "status": "done",
                },
            ))
            if is_truncated:
                final.append({
                    "role": "assistant",
                    "content": (
                        "⚠️ **Response truncated** -- the model used all available tokens "
                        "on reasoning and couldn't produce a final answer.\n\n"
                        "**Try:** Increase *Max new tokens* (e.g. 8192 or higher) "
                        "or disable *Enable thinking (CoT)* for a direct answer."
                    ),
                })
                final.append(gr.ChatMessage(
                    role="assistant",
                    content=f"Generated in **{gen_time:.1f}s**",
                    metadata={"title": f"⏱️ {gen_time:.1f}s", "status": "done"},
                ))
                yield final
                return

        # ── Multi-step tool loop (auto-continue up to 5 rounds) ──
        MAX_TOOL_ROUNDS = 5
        current_text = text

        for tool_round in range(MAX_TOOL_ROUNDS):
            tool_req = extract_tool_call(current_text)
            if not tool_req:
                # No tool call — this is the final answer
                final.append({"role": "assistant", "content": current_text})
                break

            tool_name = tool_req.get("name", "")
            tool_args = tool_req.get("arguments", {})

            if tool_name not in AVAILABLE_TOOLS:
                tool_result = f"Error: unknown tool '{tool_name}'. Available: {list(AVAILABLE_TOOLS.keys())}"
            else:
                try:
                    tool_result = AVAILABLE_TOOLS[tool_name](**tool_args)
                except Exception as e:
                    logger.error(f"Tool execution error: {e}")
                    tool_result = f"Error executing tool '{tool_name}': {str(e)}"

            final.append(gr.ChatMessage(
                role="assistant",
                content=f"`{tool_name}({tool_args})` → `{tool_result}`",
                metadata={"title": f"🛠️ Tool: {tool_name}", "status": "done"},
            ))
            yield final

            # Ask model for next step (non-streaming, usually fast)
            synthesis_history = final + [
                {"role": "assistant", "content": current_text},
                {"role": "user", "content": (
                    f"Tool result for {tool_name}: {tool_result}\n\n"
                    "Use this result to continue. If you need more data, "
                    "call another tool. Otherwise give the final answer."
                )},
            ]
            raw_next = call_model(synthesis_history, "", max_tokens, enable_thinking=False)

            if raw_next.startswith("❌ **"):
                final.append({"role": "assistant", "content": raw_next})
                break

            _, next_text = parse_thinking(raw_next)
            current_text = next_text
            logger.info(f"Tool round {tool_round + 1}: checking for follow-up tool call")
        else:
            # Exhausted max rounds
            if current_text:
                final.append({"role": "assistant", "content": current_text})

        # Timing
        final.append(gr.ChatMessage(
            role="assistant",
            content=f"Generated in **{gen_time:.1f}s**"
                    + (f" | Vision (768px, {max_tokens} max tokens)" if image_path else ""),
            metadata={"title": f"⏱️ {gen_time:.1f}s", "status": "done"},
        ))
        yield final

    except Exception as e:
        logger.error(f"Bot action error: {e}")
        yield history + [{"role": "assistant", "content": f"❌ **Processing Error:** {str(e)}"}]


# ──────────────────────────────────────────
# 6. UI THEME AND CUSTOM CSS
# ──────────────────────────────────────────
CUSTOM_CSS = """
/* ── Base layout ── */
#main-container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 10px 8px 0;
}

/* ── Status badge ── */
#status-badge {
    display: inline-block;
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 0.85em;
    font-weight: 600;
    white-space: nowrap;
}
.status-connected { background: rgba(30,142,62,0.15); color: #4ade80; border: 1px solid rgba(74,222,128,0.3); }
.status-disconnected { background: rgba(217,48,37,0.15); color: #f87171; border: 1px solid rgba(248,113,113,0.3); }

/* ── Chatbot ── */
.gradio-chatbot { border-radius: 12px !important; }
#chatbot-area > label { display: none !important; }
#chatbot-area { min-height: 300px; }

/* ── Side panel ── */
.gradio-accordion { border-radius: 10px !important; overflow: hidden; margin-bottom: 8px; }

/* ── Action buttons ── */
.action-btn {
    border: 1px solid var(--border-color-primary) !important;
    background: transparent !important;
    box-shadow: none !important;
    color: var(--body-text-color-subdued) !important;
    font-size: 0.9em !important;
    min-height: 36px !important;
}
.action-btn:hover {
    background: var(--background-fill-secondary) !important;
    color: var(--body-text-color) !important;
}

/* ── Responsive: tablets (≤1024px) ── */
@media (max-width: 1024px) {
    #main-container { padding: 6px 4px 0; }
    #chatbot-area .gradio-chatbot { height: 60vh !important; }
}

/* ── Responsive: mobile (≤768px) ── */
@media (max-width: 768px) {
    /* Stack layout vertically */
    #main-container .main-row { flex-direction: column !important; }
    #main-container .main-row > .gr-column { max-width: 100% !important; flex: 1 1 100% !important; }

    /* Compact header */
    #main-container h1 { font-size: 1.3em !important; }
    #main-container .header-desc { font-size: 0.8em !important; }
    #status-badge { font-size: 0.75em; padding: 4px 10px; }

    /* Chatbot fills available space */
    #chatbot-area .gradio-chatbot { height: 55vh !important; }

    /* Larger touch targets */
    .action-btn { min-height: 42px !important; font-size: 1em !important; }
}

/* ── Responsive: small phones (≤480px) ── */
@media (max-width: 480px) {
    #main-container { padding: 2px 2px 0; }
    #main-container h1 { font-size: 1.1em !important; letter-spacing: -0.3px; }
    #chatbot-area .gradio-chatbot { height: 50vh !important; }
    #status-badge { font-size: 0.7em; padding: 3px 8px; }
}

/* ── Prevent horizontal overflow on all sizes ── */
.gradio-chatbot .message-content { overflow-wrap: break-word; word-break: break-word; }
.gradio-chatbot pre { overflow-x: auto; max-width: 100%; }
.gradio-chatbot code { word-break: break-all; }
"""

# ──────────────────────────────────────────
# 7. UI LAYOUT
# ──────────────────────────────────────────
theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="blue",
    neutral_hue="slate",
    spacing_size="sm",
    radius_size="lg",
)

with gr.Blocks(title="Qwen 3.5 9B Local Studio") as demo:
    with gr.Column(elem_id="main-container"):
        # -- Header --
        with gr.Row():
            with gr.Column(scale=4):
                gr.HTML(
                    """
                    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 4px;">
                        <span style="font-size: 2.1em;">🧠</span>
                        <h1 style="margin: 0; font-size: 1.9em; font-weight: 800; letter-spacing: -0.5px;">Qwen 3.5 9B Local Studio</h1>
                    </div>
                    <p style="margin: 0; opacity: 0.65; font-size: 0.92em;">
                        Running locally on Apple Silicon &middot; MLX 4-bit &middot; Features <b>Vision</b>, <b>Agentic Tool Calling</b>, and <b>Reasoning</b>.
                    </p>
                    """
                )
            with gr.Column(scale=1, min_width=150):
                status_box = gr.HTML(
                    '<div id="status-badge" class="status-connected">🟢 Checking connection...</div>'
                )

        gr.Markdown("---")

        # -- Main Content --
        with gr.Row(elem_classes="main-row"):
            # Left Column: Chat
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    height="72vh",
                    render_markdown=True,
                    show_label=False,
                    elem_id="chatbot-area",
                    latex_delimiters=[
                        {"left": "$$", "right": "$$", "display": True},
                        {"left": "$", "right": "$", "display": False},
                        {"left": "\\(", "right": "\\)", "display": False},
                        {"left": "\\[", "right": "\\]", "display": True},
                    ],
                )
                with gr.Row(elem_id="chat-input-row"):
                    chat_input = gr.MultimodalTextbox(
                        interactive=True,
                        file_types=["image"],
                        placeholder="Ask a question, upload an image, or request a tool...",
                        show_label=False,
                        scale=1
                    )

            # Right Column: Settings & Info
            with gr.Column(scale=1):
                with gr.Accordion("⚙️ Generation Settings", open=True):
                    max_tokens = gr.Slider(
                        1, 32768, value=4096, step=64,
                        label="Max new tokens",
                        info="Maximum length of the model's response."
                    )
                    thinking_cb = gr.Checkbox(
                        value=True, 
                        label="Enable thinking (CoT)",
                        info="Model will reason step-by-step before answering."
                    )
                
                with gr.Accordion("🛠️ Active Tools", open=False):
                    gr.HTML("""
                        <div style="font-size: 0.85em; line-height: 1.7;">
                            <div>🕒 <code>get_current_time</code> <span style="opacity:0.5;">- date & time</span></div>
                            <div>📁 <code>list_directory</code> <span style="opacity:0.5;">- browse files</span></div>
                            <div>💻 <code>get_system_info</code> <span style="opacity:0.5;">- OS, disk, uptime</span></div>
                            <div>🔍 <code>search_files</code> <span style="opacity:0.5;">- find by pattern</span></div>
                            <div>📄 <code>read_file</code> <span style="opacity:0.5;">- read text files</span></div>
                            <div>⚡ <code>run_command</code> <span style="opacity:0.5;">- shell cmds + pipes</span></div>
                            <div>🧮 <code>calculate</code> <span style="opacity:0.5;">- math evaluator</span></div>
                        </div>
                    """)

                with gr.Accordion("📊 System Info", open=False):
                    gr.HTML(f"""
                        <ul style="list-style-type: none; padding: 0; margin: 0; font-size: 0.85em;">
                            <li style="margin-bottom: 4px;"><b>History Limit:</b> {MAX_HISTORY_LENGTH} messages</li>
                            <li style="margin-bottom: 4px;"><b>Max Image Size:</b> {MAX_IMAGE_SIZE_MB}MB</li>
                            <li style="margin-bottom: 4px;"><b>Max Vision Res:</b> 768px</li>
                            <li><b>Server:</b> <a href="{SERVER_URL}" target="_blank" style="color: #818cf8; text-decoration: none;">{SERVER_URL}</a></li>
                        </ul>
                    """)
                
                # Action Buttons
                with gr.Row():
                    retry_btn = gr.Button("Retry Last", elem_classes="action-btn", size="sm")
                    clear = gr.Button("Clear Chat", elem_classes="action-btn", size="sm")

    # Event handlers with improved error handling
    def check_server_status():
        """Check and update server status using aesthetic HTML badge."""
        try:
            if server_manager.is_healthy():
                return '<div id="status-badge" class="status-connected">🟢 Connected to server</div>'
            else:
                return '<div id="status-badge" class="status-disconnected">🔴 Server disconnected</div>'
        except Exception:
            return '<div id="status-badge" class="status-disconnected">🔴 Connection error</div>'
    
    # Periodic status check
    demo.load(check_server_status, outputs=status_box)
    
    chat_input.submit(
        user_action,
        inputs=[chat_input, chatbot],
        outputs=[chat_input, chatbot],
        queue=False,
    ).then(
        bot_action,
        inputs=[chatbot, max_tokens, thinking_cb],
        outputs=[chatbot],
    ).then(
        check_server_status,
        outputs=[status_box]
    )

    def retry_last_response(history, max_tok, think_on):
        """Retry: strip everything after the last user message, then re-generate."""
        if not history:
            yield history
            return
        # Find the last user message
        for i in range(len(history) - 1, -1, -1):
            if _msg_role(history[i]) == "user":
                trimmed = history[: i + 1]
                # First yield: visually remove the old response immediately
                yield trimmed
                # Then stream the new response
                yield from bot_action(trimmed, max_tok, think_on)
                return
        yield history

    retry_btn.click(
        retry_last_response,
        inputs=[chatbot, max_tokens, thinking_cb],
        outputs=[chatbot],
    ).then(
        check_server_status,
        outputs=[status_box],
    )

    clear.click(
        fn=lambda: [],
        inputs=[],
        outputs=[chatbot],
        queue=False,
    )

if __name__ == "__main__":
    try:
        logger.info("Starting Qwen 3.5 9B Local Studio...")
        demo.launch(
            server_port=7860,
            server_name="0.0.0.0",
            share=False,
            show_error=True,
            quiet=False,
            theme=theme,
            css=CUSTOM_CSS,
        )
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        print(f"❌ **Startup Error:** {e}")
        print("Please check if port 7860 is available and try again.")
