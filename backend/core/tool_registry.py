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
import requests
from bs4 import BeautifulSoup
import markdownify
from ddgs import DDGS
from .sandbox import execute_python_sandbox
from .plugin_loader import plugin_loader

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


def _extract_code_structure(content: str, ext: str) -> str:
    """Extract structural overview from a large code file: imports, class/function signatures, exports."""
    lines = content.splitlines()
    sections = []
    
    # Collect imports (first contiguous block)
    imports = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('/*'):
            if imports:
                break
            continue
        if any(stripped.startswith(kw) for kw in ('import ', 'from ', 'require(', 'const ', 'using ', '#include')):
            imports.append(line)
        elif imports:
            break
    if imports:
        sections.append("── Imports ──\n" + "\n".join(imports[:30]))
    
    # Extract class/function/interface/type signatures
    sigs = []
    sig_patterns = [
        # Python
        (r'^\s*(class\s+\w+[^:]*:)', 'py'),
        (r'^\s*((?:async\s+)?def\s+\w+\s*\([^)]*\)[^:]*:)', 'py'),
        # TypeScript/JavaScript
        (r'^(export\s+(?:default\s+)?(?:class|function|const|interface|type|enum)\s+\w+[^{;]*)', 'ts'),
        (r'^((?:export\s+)?interface\s+\w+[^{]*)', 'ts'),
        (r'^((?:export\s+)?type\s+\w+\s*=)', 'ts'),
        (r'^((?:export\s+)?enum\s+\w+)', 'ts'),
        # C/C++/Rust
        (r'^(\w[\w\s\*&:<>]*\s+\w+\s*\([^)]*\)\s*(?:const\s*)?(?:override\s*)?(?:noexcept\s*)?)\s*\{?', 'c'),
        (r'^(struct\s+\w+)', 'c'),
    ]
    
    for i, line in enumerate(lines):
        for pattern, _ in sig_patterns:
            m = re.match(pattern, line)
            if m:
                sig = m.group(1).rstrip('{').rstrip(':').strip()
                # Add line number for reference
                sigs.append(f"  L{i+1}: {sig}")
                break
    
    if sigs:
        sections.append("── Signatures (" + str(len(sigs)) + ") ──\n" + "\n".join(sigs[:60]))
    
    # Exports (for JS/TS)
    if ext in ('.ts', '.tsx', '.js', '.jsx', '.mjs'):
        exports = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('export default') or stripped.startswith('module.exports'):
                exports.append(f"  L{i+1}: {stripped[:120]}")
        if exports:
            sections.append("── Exports ──\n" + "\n".join(exports[:10]))
    
    return "\n\n".join(sections)


def read_file(path: str, max_lines: int = 100) -> str:
    """Read a text file. For files over 50KB, returns a structural overview instead of erroring."""
    try:
        fp = Path(path).expanduser().resolve()
        err = _check_path_access(fp)
        if err: return err
        if not fp.exists(): return f"Error: '{path}' does not exist"
        if not fp.is_file(): return f"Error: '{path}' is not a file"
        
        size = fp.stat().st_size
        if size > 500 * 1024:
            return f"Error: File too large ({size / 1024:.0f}KB, max 500KB). Try run_command with head/tail."
        
        try:
            content = fp.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "Error: Binary file detected - cannot display"
        
        lines = content.splitlines()
        
        # Large file: return structural overview instead of erroring
        if size > 50 * 1024:
            ext = fp.suffix.lower()
            overview = _extract_code_structure(content, ext)
            header = f"=== {fp.name} ({len(lines)} lines, {size // 1024}KB) — STRUCTURAL OVERVIEW ===\n"
            header += f"(File too large for full read. Showing imports, signatures, and exports.)\n\n"
            if overview:
                result = header + overview
                # Also show first 20 and last 10 lines for context
                head = "\n".join(lines[:20])
                tail = "\n".join(lines[-10:])
                result += f"\n\n── First 20 lines ──\n{head}"
                result += f"\n\n── Last 10 lines ──\n{tail}"
                return result
            else:
                # Fallback: show head + tail
                head = "\n".join(lines[:50])
                tail = "\n".join(lines[-20:])
                return header + head + f"\n\n... ({len(lines) - 70} lines omitted) ...\n\n" + tail
            
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


# ──────────────────────────────────────────
# COMMAND SECURITY — Blocklist + Consent
# ──────────────────────────────────────────
# Instead of whitelisting safe commands, we block dangerous ones
# and require user consent for write/modify operations.
# Everything else is auto-executed.

BLOCKED_COMMANDS = frozenset({
    # Privilege escalation
    "sudo", "su", "doas",
    # File destruction
    "rm", "rmdir", "shred", "unlink", "srm",
    # Disk / partition operations
    "mkfs", "dd", "format", "fdisk",
    # System control
    "shutdown", "reboot", "halt", "poweroff", "init",
    # User / group management
    "passwd", "chpasswd", "useradd", "userdel", "usermod",
    "groupadd", "groupdel", "groupmod", "visudo",
    # Network security
    "iptables", "pfctl", "ufw",
    # Mount
    "mount", "umount",
    # Service management
    "systemctl", "service",
})

# Commands that ALWAYS need user consent (modify files/state)
CONSENT_COMMANDS = frozenset({
    "mkdir", "touch", "cp", "mv", "ln", "install",
    "chmod", "chown", "chgrp",
    "tee", "truncate",
    "rsync", "scp",
    "crontab",
    "launchctl",
    "wget",
    # Process management — needs user consent instead of hard block
    "kill", "killall", "pkill",
})

# Multi-command tools: only specific subcommands need consent
CONSENT_SUBCOMMANDS = {
    "git":    frozenset({"commit", "push", "pull", "merge", "rebase", "reset", "checkout", "switch",
                         "stash", "cherry-pick", "revert", "init", "clone", "add", "rm", "mv",
                         "clean", "tag", "fetch", "restore"}),
    "pip":    frozenset({"install", "uninstall"}),
    "pip3":   frozenset({"install", "uninstall"}),
    "npm":    frozenset({"install", "uninstall", "update", "init", "publish", "link", "ci"}),
    "yarn":   frozenset({"add", "remove", "install", "upgrade"}),
    "brew":   frozenset({"install", "uninstall", "update", "upgrade", "remove", "tap", "untap"}),
    "docker": frozenset({"run", "exec", "build", "push", "pull", "rm", "rmi", "stop",
                         "kill", "create", "start", "restart", "compose"}),
    "defaults": frozenset({"write", "delete"}),
    "xattr":    frozenset({"write", "delete", "clear"}),
    "diskutil": frozenset({"erase", "partition", "mount", "unmount", "rename"}),
}

# Shell wrappers that can execute arbitrary commands
_SHELL_INTERPRETERS = frozenset({
    "bash", "sh", "zsh", "ksh", "csh", "tcsh", "fish", "dash",
})

# Scripting interpreters that can execute arbitrary code
_SCRIPT_INTERPRETERS = frozenset({
    "python", "python3", "python2", "perl", "ruby", "node", "php",
})

# Command wrappers that pass-through to other commands
_COMMAND_WRAPPERS = frozenset({
    "env", "nice", "nohup", "time", "timeout", "strace", "ltrace",
    "xargs", "watch",
})

def _extract_inner_command(parts: list) -> list:
    """Extract the actual command from wrapper patterns like 'env cmd', 'bash -c "cmd"', etc."""
    if not parts:
        return parts
    cmd = parts[0]

    # Handle command wrappers: strip wrapper and recurse
    if cmd in _COMMAND_WRAPPERS:
        # Skip flags and find the actual command
        rest = parts[1:]
        while rest and rest[0].startswith('-'):
            rest = rest[1:]
        if rest:
            return _extract_inner_command(rest)
        return parts

    # Handle shell -c "command": parse the inner command string
    if cmd in _SHELL_INTERPRETERS:
        for i, arg in enumerate(parts[1:], 1):
            if arg in ('-c', '--'):
                # The next argument is the actual command string
                if i + 1 < len(parts):
                    inner_cmd = parts[i + 1]
                    try:
                        return shlex.split(inner_cmd)
                    except ValueError:
                        return inner_cmd.split()
                return parts
        # Shell without -c (e.g., "bash script.sh") — needs consent
        return parts

    # Handle script interpreters: python -c "code", perl -e "code"
    if cmd in _SCRIPT_INTERPRETERS:
        for arg in parts[1:]:
            if arg in ('-c', '-e'):
                return parts  # Will be caught by consent below

    return parts

def _check_command_safety(segment: str) -> str:
    """Check safety of a single command segment.
    Returns: 'safe', 'consent', or 'Error: ...' message."""
    segment = segment.strip()
    if not segment:
        return "safe"
    try:
        parts = shlex.split(segment)
    except ValueError:
        return f"Error: Could not parse: {segment}"
    if not parts:
        return "safe"

    cmd = parts[0]

    # Hard block on the outer command
    if cmd in BLOCKED_COMMANDS:
        return f"Error: '{cmd}' is blocked for safety."

    # Unwrap wrappers and check the inner command too
    inner_parts = _extract_inner_command(parts)
    if inner_parts and inner_parts is not parts:
        inner_cmd = inner_parts[0]
        if inner_cmd in BLOCKED_COMMANDS:
            return f"Error: '{inner_cmd}' is blocked for safety (detected inside wrapper)."
        # Check inner arguments for blocked commands
        for arg in inner_parts[1:]:
            if arg in BLOCKED_COMMANDS:
                return f"Error: '{arg}' is blocked (detected inside wrapper)."
        # Check inner command for consent requirements
        if inner_cmd in CONSENT_COMMANDS:
            return "consent"
        if inner_cmd in CONSENT_SUBCOMMANDS and len(inner_parts) > 1:
            subcmd = inner_parts[1].lstrip("-")
            if subcmd in CONSENT_SUBCOMMANDS[inner_cmd]:
                return "consent"

    # Shell interpreters with -c flag always need consent (arbitrary code execution)
    if cmd in _SHELL_INTERPRETERS:
        for arg in parts[1:]:
            if arg == '-c':
                return "consent"

    # Script interpreters with inline code always need consent
    if cmd in _SCRIPT_INTERPRETERS:
        for arg in parts[1:]:
            if arg in ('-c', '-e'):
                return "consent"

    # Check arguments for blocked commands (prevent tricks like 'env sudo ...')
    for arg in parts[1:]:
        if arg in BLOCKED_COMMANDS:
            return f"Error: '{arg}' is blocked."

    # Full-command consent
    if cmd in CONSENT_COMMANDS:
        return "consent"
    # Subcommand-level consent
    if cmd in CONSENT_SUBCOMMANDS and len(parts) > 1:
        subcmd = parts[1].lstrip("-")
        if subcmd in CONSENT_SUBCOMMANDS[cmd]:
            return "consent"
    return "safe"

def _validate_redirects(command: str) -> str:
    """Check for dangerous shell operators. Returns error or empty string."""
    cleaned = re.sub(r'2>\s*/dev/null', '', command)
    for bad in ["`", "$("]:
        if bad in cleaned:
            return f"Error: Shell operator '{bad}' is not allowed"
    test_str = re.sub(r'2>&1', '', cleaned)
    if ">>" in test_str:
        return "Error: Append redirection '>>' is not allowed"
    remaining = re.sub(r'2>\s*/dev/null', '', test_str)
    if ">" in remaining:
        return "Error: Output redirection '>' is not allowed"
    return ""

def run_command(command: str) -> str:
    """Run shell commands. Dangerous commands are blocked; write operations need user consent."""
    try:
        redirect_err = _validate_redirects(command)
        if redirect_err:
            return redirect_err

        cleaned = re.sub(r'2>\s*/dev/null', '', command)
        chain_segments = re.split(r'\s*(?:&&|\|\||;)\s*', cleaned)

        needs_consent = False
        for chain_seg in chain_segments:
            pipe_parts = [s.strip() for s in chain_seg.split("|")]
            for part in pipe_parts:
                if not part:
                    continue
                safety = _check_command_safety(part)
                if safety.startswith("Error:"):
                    return safety
                if safety == "consent":
                    needs_consent = True

        if needs_consent:
            return (
                f"[CONSENT_REQUIRED] `{command}` — This command may modify files or system state. "
                f"The user must approve it before it can run."
            )

        return _execute_shell(command)
    except Exception as e:
        return f"Error: {str(e)}"


def _execute_shell(command: str) -> str:
    """Execute a shell command and return output."""
    try:
        home = str(Path.home())
        run_env = {**os.environ, "LANG": "en_US.UTF-8"}
        suppress_stderr = "2>" in command

        proc = subprocess.run(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if suppress_stderr else subprocess.PIPE,
            text=True,
            timeout=30,
            cwd=home,
            env=run_env,
        )

        output = proc.stdout or ""
        if not suppress_stderr and proc.stderr and proc.stderr.strip():
            prefix = f"[exit {proc.returncode}] " if proc.returncode != 0 else "[stderr] "
            output += f"\n{prefix}{proc.stderr.strip()}"

        if len(output) > 8000:
            output = output[:8000] + "\n... (truncated)"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out (30s limit)"
    except Exception as e:
        return f"Error: {str(e)}"


def run_approved_command(command: str) -> str:
    """Execute a user-approved command. Still blocks truly dangerous commands."""
    redirect_err = _validate_redirects(command)
    if redirect_err:
        return redirect_err
    cleaned = re.sub(r'2>\s*/dev/null', '', command)
    chain_segments = re.split(r'\s*(?:&&|\|\||;)\s*', cleaned)
    for chain_seg in chain_segments:
        pipe_parts = [s.strip() for s in chain_seg.split("|")]
        for part in pipe_parts:
            if not part:
                continue
            try:
                parts = shlex.split(part.strip())
            except ValueError:
                return f"Error: Could not parse: {part}"
            if parts and parts[0] in BLOCKED_COMMANDS:
                return f"Error: '{parts[0]}' is blocked."
            for arg in parts[1:]:
                if arg in BLOCKED_COMMANDS:
                    return f"Error: '{arg}' is blocked."
    return _execute_shell(command)

# ──────────────────────────────────────────
# REGISTRY
# ──────────────────────────────────────────
def execute_python(code: str) -> str:
    """Execute Python code in a sandbox. Captures stdout/stderr and matplotlib plots."""
    result = execute_python_sandbox(code)
    return result  # Returns dict; agent.py handles structured output


def execute_cpp(code: str, stdin_input: str = "") -> str:
    """Compile and run C++ code. Returns compilation errors or program output."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = os.path.join(tmpdir, "main.cpp")
            bin_path = os.path.join(tmpdir, "main")

            with open(src_path, "w") as f:
                f.write(code)

            # Find compiler
            compiler = None
            for cc in ["g++", "clang++"]:
                if shutil.which(cc):
                    compiler = cc
                    break
            if not compiler:
                return "Error: No C++ compiler found (g++ or clang++ required)"

            # Compile
            compile_result = subprocess.run(
                [compiler, "-std=c++17", "-O2", "-o", bin_path, src_path],
                capture_output=True, text=True, timeout=30
            )
            if compile_result.returncode != 0:
                return f"Compilation Error:\n{compile_result.stderr.strip()}"

            # Run
            run_result = subprocess.run(
                [bin_path],
                input=stdin_input if stdin_input else None,
                capture_output=True, text=True, timeout=30
            )
            output = ""
            if run_result.stdout:
                output += run_result.stdout
            if run_result.stderr:
                output += ("\nStderr:\n" + run_result.stderr) if output else run_result.stderr
            if run_result.returncode != 0:
                output += f"\n(exit code: {run_result.returncode})"
            return output.strip() if output.strip() else "(no output)"

    except subprocess.TimeoutExpired:
        return "Error: Execution timed out (30s limit)"
    except Exception as e:
        return f"Error: {str(e)}"


def search_web(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo."""
    try:
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "No results found."
        
        output = f"Search results for: '{query}'\n\n"
        for i, r in enumerate(results, 1):
            output += f"{i}. {r.get('title', 'No Title')}\n"
            output += f"   URL: {r.get('href', 'No URL')}\n"
            output += f"   Snippet: {r.get('body', 'No snippet available')}\n\n"
        return output.strip()
    except Exception as e:
        return f"Error performing web search: {str(e)}"

def _clean_web_content(html_text: str, max_chars: int = 8000) -> str:
    """Preprocess extracted web content: strip boilerplate, ads, navs, and compress to useful info."""
    soup = BeautifulSoup(html_text, 'html.parser')
    
    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript",
                     "aside", "form", "button", "svg", "figure", "figcaption"]):
        tag.decompose()
    
    # Remove ad/tracking divs by common class/id patterns
    ad_patterns = re.compile(r'(ad[sv]?[-_]|banner|popup|modal|cookie|consent|newsletter|subscribe|sidebar|widget|social|share|comment|related)', re.I)
    for el in soup.find_all(attrs={"class": ad_patterns}):
        el.decompose()
    for el in soup.find_all(attrs={"id": ad_patterns}):
        el.decompose()
    
    # Remove empty elements
    for el in soup.find_all():
        if not el.get_text(strip=True) and el.name not in ('img', 'br', 'hr'):
            el.decompose()
    
    markdown_text = markdownify.markdownify(str(soup), heading_style="ATX")
    
    # Clean up
    clean = re.sub(r'\n{3,}', '\n\n', markdown_text)
    clean = re.sub(r'(\[.*?\]\(javascript:.*?\))', '', clean)  # JS links
    clean = re.sub(r'!\[.*?\]\(data:.*?\)', '', clean)  # data URIs
    clean = re.sub(r'\[([^\]]*)\]\(\s*\)', r'\1', clean)  # empty links
    clean = re.sub(r'^\s*[\*\-]\s*$', '', clean, flags=re.MULTILINE)  # empty list items
    clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
    
    if len(clean) > max_chars:
        return clean[:max_chars] + "\n\n... (Content truncated)"
    return clean


def read_url(url: str) -> str:
    """Read and extract text content from a webpage URL with smart content preprocessing."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return _clean_web_content(response.text)
    except requests.RequestException as e:
        return f"Error fetching URL: {str(e)}"
    except Exception as e:
        return f"Error processing webpage: {str(e)}"


def read_rss(url: str, max_items: int = 10) -> str:
    """Read and parse an RSS/Atom feed. Returns structured feed entries."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; KassetBot/1.0)"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'xml')
        
        # Try RSS format first
        items = soup.find_all('item')
        if not items:
            # Try Atom format
            items = soup.find_all('entry')
        
        if not items:
            return f"No feed items found at {url}. Is this a valid RSS/Atom feed URL?"
        
        feed_title = ""
        channel = soup.find('channel')
        if channel and channel.find('title'):
            feed_title = channel.find('title').get_text(strip=True)
        elif soup.find('feed') and soup.find('feed').find('title'):
            feed_title = soup.find('feed').find('title').get_text(strip=True)
        
        output = f"📡 Feed: {feed_title}\n{'─' * 40}\n\n" if feed_title else ""
        
        for i, item in enumerate(items[:max_items], 1):
            title = item.find('title')
            link = item.find('link')
            pub_date = item.find('pubDate') or item.find('published') or item.find('updated')
            desc = item.find('description') or item.find('summary') or item.find('content')
            
            title_text = title.get_text(strip=True) if title else "No title"
            link_text = link.get_text(strip=True) if link and link.string else (link.get('href', '') if link else '')
            date_text = pub_date.get_text(strip=True) if pub_date else ""
            
            # Clean description HTML
            desc_text = ""
            if desc:
                desc_soup = BeautifulSoup(desc.get_text(), 'html.parser')
                desc_text = desc_soup.get_text(strip=True)[:200]
            
            output += f"{i}. **{title_text}**\n"
            if date_text:
                output += f"   📅 {date_text}\n"
            if link_text:
                output += f"   🔗 {link_text}\n"
            if desc_text:
                output += f"   {desc_text}\n"
            output += "\n"
        
        return output.strip()
    except Exception as e:
        return f"Error reading RSS feed: {str(e)}"


def get_location() -> str:
    """Get approximate location based on IP geolocation. Returns city, region, country, timezone."""
    try:
        response = requests.get("http://ip-api.com/json/?fields=status,message,country,regionName,city,timezone,lat,lon,query", timeout=5)
        data = response.json()
        if data.get("status") == "success":
            return (
                f"Location: {data.get('city', '?')}, {data.get('regionName', '?')}, {data.get('country', '?')}\n"
                f"Timezone: {data.get('timezone', '?')}\n"
                f"Coordinates: {data.get('lat', '?')}, {data.get('lon', '?')}\n"
                f"IP: {data.get('query', '?')}"
            )
        return f"Could not determine location: {data.get('message', 'unknown error')}"
    except Exception as e:
        return f"Error getting location: {str(e)}"

BUILTIN_TOOLS = {
    "get_current_time": get_current_time,
    "get_location": get_location,
    "list_directory": list_directory,
    "get_system_info": get_system_info,
    "search_files": search_files,
    "read_file": read_file,
    "run_command": run_command,
    "calculate": calculate,
    "execute_python": execute_python,
    "execute_cpp": execute_cpp,
    "search_web": search_web,
    "read_url": read_url,
    "read_rss": read_rss,
}

# Backwards compat
AVAILABLE_TOOLS = BUILTIN_TOOLS


def get_all_tool_ids() -> list:
    """Return IDs of all available tools (built-in + plugins)."""
    ids = list(BUILTIN_TOOLS.keys())
    ids.extend(plugin_loader.manifests.keys())
    return ids


def execute_tool(name: str, args: dict):
    """Execute a tool by name. Checks built-ins first, then plugins."""
    if name in BUILTIN_TOOLS:
        try:
            return BUILTIN_TOOLS[name](**args)
        except Exception as e:
            return f"Error executing tool '{name}': {str(e)}"

    # Check plugin tools
    if name in plugin_loader.manifests:
        return plugin_loader.execute_tool(name, args)

    return f"Error: unknown tool '{name}'"
