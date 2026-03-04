import re
import json
import os
import ast
import glob as glob_module
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
from .sandbox import execute_python_sandbox

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────
# SECURE PATH HANDLING
# ──────────────────────────────────────────
def _ALLOWED_PATHS():
    return [
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


# ──────────────────────────────────────────
# TOOLS
# ──────────────────────────────────────────
def get_current_time() -> str:
    """Get the current local date and time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")


def list_directory(path: str = ".") -> str:
    """List directory contents with file sizes."""
    try:
        path_obj = Path(path).expanduser().resolve()
        err = _check_path_access(path_obj)
        if err: return err
        if not path_obj.exists(): return f"Error: Path '{path}' does not exist"
        if not path_obj.is_dir(): return f"Error: '{path}' is not a directory"

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
        if err: return err
        if not dir_path.exists() or not dir_path.is_dir():
            return f"Error: '{directory}' is not a valid directory"

        matches = list(dir_path.rglob(pattern))[:50]
        if not matches: return f"No files matching '{pattern}' in {directory}"
        lines = [str(m.relative_to(dir_path)) for m in matches]
        suffix = "\n  ... (results capped at 50)" if len(matches) == 50 else ""
        return f"Found {len(matches)} match(es) in {dir_path}:\n" + "\n".join(f"  {l}" for l in lines) + suffix
    except Exception as e:
        return f"Error: {str(e)}"


def read_file(path: str, max_lines: int = 100) -> str:
    """Read a text file (max 200 lines / 50KB)."""
    try:
        fp = Path(path).expanduser().resolve()
        err = _check_path_access(fp)
        if err: return err
        if not fp.exists(): return f"Error: '{path}' does not exist"
        if not fp.is_file(): return f"Error: '{path}' is not a file"
        
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
    """Safe math evaluator."""
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
        if isinstance(node, ast.Expression): return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, complex)): return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS: return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS: return _OPS[type(node.op)](_eval(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
        if isinstance(node, ast.Name) and node.id in _CONSTS: return _CONSTS[node.id]
        raise ValueError(f"Unsupported: {ast.dump(node)}")

    try:
        result = _eval(ast.parse(expression.strip(), mode="eval"))
        if isinstance(result, float) and result == int(result) and abs(result) < 1e15:
            return str(int(result))
        return str(result)
    except Exception as e:
        return f"Error: {e}"


SAFE_COMMANDS = frozenset({
    "ls", "find", "file", "stat", "wc", "cat", "head", "tail", "grep",
    "du", "df", "tree", "realpath", "dirname", "basename",
    "sort", "uniq", "diff", "comm", "cut", "tr", "fold", "fmt",
    "xxd", "od", "strings", "md5", "shasum", "cksum", "xattr", "lsof",
    "uname", "hostname", "whoami", "date", "uptime", "pwd", "id",
    "ps", "top", "sw_vers", "system_profiler", "sysctl", "vm_stat",
    "last", "w", "groups",
    "ifconfig", "ping", "dig", "nslookup", "curl", "netstat",
    "scutil", "networksetup",
    "mdfind", "mdls", "diskutil", "pmset", "ioreg",
    "pbpaste", "log", "csrutil", "spctl", "open", "say",
    "echo", "which", "env", "printenv", "locale", "cal", "bc",
})

_BLOCKED_ARGS = frozenset({
    "sudo", "rm", "rmdir", "mkfs", "dd", "format",
    "shutdown", "reboot", "halt", "kill", "killall",
    "mv", "cp", "chmod", "chown", "chgrp", "mktemp",
})

def _expand_arg(arg: str) -> list:
    if arg.startswith("~"):
        arg = str(Path.home()) + arg[1:]
    if any(c in arg for c in ("*", "?", "[")):
        matches = sorted(glob_module.glob(arg))
        return matches if matches else [arg]
    return [arg]

def run_command(command: str) -> str:
    """Run whitelisted shell commands (read-only, 30s timeout, pipes allowed)."""
    try:
        cleaned = re.sub(r'2>\s*/dev/null', '', command)
        for bad in ["&&", "||", ";", "`", "$(", ">>", ">"]:
            if bad == ">" and "2>&1" in cleaned:
                cleaned = cleaned.replace("2>&1", "")
                continue
            if bad in cleaned: return f"Error: Shell operator '{bad}' is not allowed"

        stages = [s.strip() for s in cleaned.split("|")]
        parsed_stages = []
        for stage in stages:
            if not stage: continue
            raw_parts = shlex.split(stage)
            if not raw_parts: return "Error: Empty command in pipe chain"
            if raw_parts[0] not in SAFE_COMMANDS:
                return f"Error: '{raw_parts[0]}' is not allowed."
            if any(arg in _BLOCKED_ARGS for arg in raw_parts):
                return "Error: Blocked keyword detected"
            expanded = [raw_parts[0]]
            for arg in raw_parts[1:]: expanded.extend(_expand_arg(arg))
            parsed_stages.append(expanded)

        if not parsed_stages: return "Error: Empty command"

        home = str(Path.home())
        run_env = {**os.environ, "LANG": "en_US.UTF-8"}
        suppress_stderr = "2>" in command
        prev_stdout = None

        for i, parts in enumerate(parsed_stages):
            proc = subprocess.run(
                parts, input=prev_stdout, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL if suppress_stderr else subprocess.PIPE,
                text=True, timeout=30, cwd=home, env=run_env,
            )
            prev_stdout = proc.stdout
            if not suppress_stderr and proc.returncode != 0 and proc.stderr:
                prev_stdout += f"\n[exit {proc.returncode}] {proc.stderr.strip()}"

        output = prev_stdout or ""
        if len(output) > 5000: output = output[:5000] + "\n... (truncated)"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out (30s limit)"
    except Exception as e:
        return f"Error: {str(e)}"

# ──────────────────────────────────────────
# REGISTRY
# ──────────────────────────────────────────
def execute_python(code: str) -> str:
    """Execute Python code in a sandbox. Captures stdout/stderr and matplotlib plots."""
    result = execute_python_sandbox(code)
    return result  # Returns dict; agent.py handles structured output


AVAILABLE_TOOLS = {
    "get_current_time": get_current_time,
    "list_directory": list_directory,
    "get_system_info": get_system_info,
    "search_files": search_files,
    "read_file": read_file,
    "run_command": run_command,
    "calculate": calculate,
    "execute_python": execute_python,
}

def execute_tool(name: str, args: dict) -> str:
    if name not in AVAILABLE_TOOLS:
        return f"Error: unknown tool '{name}'"
    try:
        return AVAILABLE_TOOLS[name](**args)
    except Exception as e:
        return f"Error executing tool '{name}': {str(e)}"
