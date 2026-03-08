"""
Plugin Loader — discovers, validates, and executes custom tool plugins for Kasset.

Tool Plugin Standard:
    ~/.kasset/tools/<tool-id>/
    ├── manifest.json       # Tool metadata, params, description, UI hints
    └── handler.py          # Python function implementation

manifest.json format:
{
    "id": "my_tool",
    "name": "My Tool",
    "version": "1.0.0",
    "description": "What the tool does (shown to the model)",
    "author": "user",
    "icon": "wrench",          # Lucide icon name
    "color": "#60a5fa",        # Hex color for UI
    "parameters": {
        "param_name": {
            "type": "string",
            "description": "Description shown to the model",
            "required": true
        }
    },
    "output_type": "text",     # "text" | "html" | "image" | "mixed"
    "handler": "handler.py",
    "entry_point": "execute",
    "sandbox": {
        "timeout": 30,
        "imports": ["plotly"],
        "pre_run": "import plotly.graph_objects as go"
    }
}

handler.py must export the entry_point function. Return value:
    str             -> treated as text output
    dict            -> { "output": str, "images": [str], "html": str }
"""

import json
import logging
import subprocess
import traceback
import sys
import importlib
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

USER_TOOLS_DIR = Path.home() / ".kasset" / "tools"


# The runner script is a fixed template — no string interpolation of user data.
# All dynamic values (handler_path, entry_point, pre_run, args) are passed via JSON on stdin.
_RUNNER_SCRIPT = '''
import sys, json, importlib.util, io, contextlib

# Read all dynamic config + args from stdin (safe — no string interpolation)
payload = json.loads(sys.stdin.read())
handler_path = payload["handler_path"]
entry_point = payload["entry_point"]
pre_run_code = payload.get("pre_run", "")
args = payload.get("args", {})

# Pre-run imports if specified (executed in controlled subprocess)
if pre_run_code:
    exec(pre_run_code)

# Load handler module
spec = importlib.util.spec_from_file_location("_plugin_handler", handler_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

fn = getattr(mod, entry_point, None)
if fn is None:
    print(json.dumps({"error": f"Entry point '{entry_point}' not found"}))
    sys.exit(1)

# Capture stdout from the handler
capture = io.StringIO()
with contextlib.redirect_stdout(capture):
    result = fn(**args)

captured = capture.getvalue()

# Normalize and output as JSON
if result is None:
    out = captured.strip() or "Tool executed successfully (no output)."
    print(out)
elif isinstance(result, dict):
    if captured:
        result["output"] = (captured + "\n" + result.get("output", "")).strip()
    print(json.dumps(result))
elif isinstance(result, str):
    combined = (captured + "\n" + result).strip() if captured else result
    print(combined)
else:
    print(str(result))
'''


class ToolManifest:
    """Parsed and validated tool manifest."""

    REQUIRED_FIELDS = {"id", "name", "description", "parameters"}
    VALID_OUTPUT_TYPES = {"text", "html", "image", "mixed"}

    def __init__(self, data: dict, directory: Path):
        self.raw = data
        self.directory = directory
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.version: str = data.get("version", "1.0.0")
        self.description: str = data["description"]
        self.author: str = data.get("author", "user")
        self.icon: str = data.get("icon", "wrench")
        self.color: str = data.get("color", "#60a5fa")
        self.parameters: Dict[str, dict] = data.get("parameters", {})
        self.output_type: str = data.get("output_type", "text")
        self.handler_file: str = data.get("handler", "handler.py")
        self.entry_point: str = data.get("entry_point", "execute")
        self.sandbox: dict = data.get("sandbox", {})
        self.tags: List[str] = data.get("tags", [])
        self.dependencies: List[str] = data.get("dependencies", [])

    @classmethod
    def validate(cls, data: dict) -> List[str]:
        """Return list of validation errors (empty = valid)."""
        errors = []
        for field in cls.REQUIRED_FIELDS:
            if field not in data:
                errors.append(f"Missing required field: '{field}'")
        if "id" in data:
            if not isinstance(data["id"], str) or not data["id"].replace("_", "").replace("-", "").isalnum():
                errors.append("'id' must be alphanumeric with underscores/hyphens")
        if "parameters" in data and not isinstance(data["parameters"], dict):
            errors.append("'parameters' must be an object")
        if "output_type" in data and data["output_type"] not in cls.VALID_OUTPUT_TYPES:
            errors.append(f"'output_type' must be one of {cls.VALID_OUTPUT_TYPES}")
        return errors

    def get_param_descriptions(self) -> Dict[str, str]:
        """Return {param_name: description} for agent prompt building."""
        return {
            k: v.get("description", k)
            for k, v in self.parameters.items()
        }

    def to_frontend_meta(self) -> dict:
        """Return metadata for frontend TOOL_META rendering."""
        return {
            "icon": self.icon,
            "label": self.name,
            "color": self.color,
            "output_type": self.output_type,
        }

    def to_dict(self) -> dict:
        """Serialize for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "icon": self.icon,
            "color": self.color,
            "parameters": self.parameters,
            "output_type": self.output_type,
            "handler": self.handler_file,
            "entry_point": self.entry_point,
            "sandbox": self.sandbox,
            "tags": self.tags,
            "dependencies": self.dependencies,
        }


class PluginLoader:
    """Discovers and manages custom tool plugins."""

    def __init__(self, tools_dir: Path = USER_TOOLS_DIR):
        self.tools_dir = tools_dir
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        self.manifests: Dict[str, ToolManifest] = {}
        self.load_all()

    def load_all(self):
        """Discover and load all tool plugins from the tools directory."""
        self.manifests.clear()

        if not self.tools_dir.exists():
            return

        for tool_dir in sorted(self.tools_dir.iterdir()):
            if not tool_dir.is_dir():
                continue
            manifest_path = tool_dir / "manifest.json"
            if not manifest_path.exists():
                logger.warning(f"Plugin dir {tool_dir.name} missing manifest.json, skipping")
                continue
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                errors = ToolManifest.validate(data)
                if errors:
                    logger.error(f"Invalid manifest in {tool_dir.name}: {errors}")
                    continue
                manifest = ToolManifest(data, tool_dir)
                self.manifests[manifest.id] = manifest
                logger.info(f"Loaded tool plugin: {manifest.id} v{manifest.version}")
            except Exception as e:
                logger.error(f"Failed to load plugin {tool_dir.name}: {e}")

    def reload(self):
        """Re-scan and reload all plugins."""
        self.load_all()

    def list_tools(self) -> List[dict]:
        """Return list of all loaded tool manifests for API."""
        return [m.to_dict() for m in self.manifests.values()]

    def get_manifest(self, tool_id: str) -> Optional[ToolManifest]:
        """Get manifest for a specific tool."""
        return self.manifests.get(tool_id)

    def get_tool_meta(self) -> Dict[str, dict]:
        """Return {tool_id: frontend_meta} for all plugins."""
        return {
            tid: m.to_frontend_meta()
            for tid, m in self.manifests.items()
        }

    def get_tool_descriptions(self) -> Dict[str, dict]:
        """Return {tool_id: {desc, params}} for agent prompt building."""
        return {
            tid: {
                "desc": m.description,
                "params": m.get_param_descriptions(),
            }
            for tid, m in self.manifests.items()
        }

    def check_dependencies(self, tool_id: str) -> Dict[str, bool]:
        """Check which dependencies are installed for a plugin.
        Returns {package_spec: is_installed}."""
        manifest = self.manifests.get(tool_id)
        if not manifest:
            return {}
        result = {}
        for dep in manifest.dependencies:
            # Extract package name from spec like "plotly>=5.0"
            pkg_name = dep.split(">=")[0].split("<=")[0].split("==")[0].split(">")[0].split("<")[0].split("!=")[0].strip()
            try:
                importlib.import_module(pkg_name.replace("-", "_"))
                result[dep] = True
            except ImportError:
                result[dep] = False
        return result

    def install_dependencies(self, tool_id: str) -> Dict[str, str]:
        """Install missing dependencies for a plugin.
        Returns {package_spec: "installed" | "already_installed" | error_message}.
        Note: This runs pip synchronously. Call via run_in_executor from async context."""
        manifest = self.manifests.get(tool_id)
        if not manifest:
            return {"error": f"Plugin '{tool_id}' not found"}

        status = self.check_dependencies(tool_id)
        results = {}
        for dep, installed in status.items():
            if installed:
                results[dep] = "already_installed"
                continue
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "pip", "install", dep],
                    capture_output=True, text=True, timeout=120,
                )
                if proc.returncode == 0:
                    results[dep] = "installed"
                    logger.info(f"Installed dependency '{dep}' for plugin '{tool_id}'")
                else:
                    results[dep] = f"failed: {proc.stderr.strip()[:200]}"
                    logger.error(f"Failed to install '{dep}' for '{tool_id}': {proc.stderr.strip()[:200]}")
            except subprocess.TimeoutExpired:
                results[dep] = "failed: installation timed out"
            except Exception as e:
                results[dep] = f"failed: {str(e)}"
        return results

    def execute_tool(self, tool_id: str, args: dict) -> Any:
        """Execute a plugin tool in an isolated subprocess.

        Communication: JSON over stdin → subprocess runs handler → JSON over stdout.
        Timeout: manifest.sandbox.timeout (default 30s).

        Returns:
            str or dict with keys: output, images (optional), html (optional)
        """
        manifest = self.manifests.get(tool_id)
        if not manifest:
            return f"Error: Plugin tool '{tool_id}' not found"

        handler_path = (manifest.directory / manifest.handler_file).resolve()
        # Prevent path traversal — handler must be inside the tool directory
        if not str(handler_path).startswith(str(manifest.directory.resolve())):
            logger.error(f"Plugin '{tool_id}': handler path traversal blocked: {manifest.handler_file}")
            return f"Error: Handler path '{manifest.handler_file}' escapes tool directory"
        if not handler_path.exists():
            return f"Error: Handler not found: {handler_path}"

        # Filter args to only declared parameters
        valid_args = {k: v for k, v in args.items() if k in manifest.parameters}

        timeout = manifest.sandbox.get("timeout", 30)
        pre_run = manifest.sandbox.get("pre_run", "")

        # Build payload with all dynamic values — passed via stdin, not string interpolation
        payload = json.dumps({
            "handler_path": str(handler_path),
            "entry_point": manifest.entry_point,
            "pre_run": pre_run,
            "args": valid_args,
        })

        try:
            proc = subprocess.run(
                [sys.executable, "-c", _RUNNER_SCRIPT],
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(manifest.directory),
            )

            if proc.returncode != 0:
                stderr = proc.stderr.strip()
                # Truncate long tracebacks
                if len(stderr) > 2000:
                    stderr = stderr[-2000:]
                logger.error(f"Plugin '{tool_id}' failed (exit {proc.returncode}): {stderr}")
                return f"Error executing plugin '{tool_id}': {stderr}"

            stdout = proc.stdout.strip()
            if not stdout:
                return "Tool executed successfully (no output)."

            # Try to parse JSON result from the subprocess
            try:
                result = json.loads(stdout)
                # Merge any stderr warnings into output
                if proc.stderr.strip():
                    warnings = proc.stderr.strip()[:500]
                    if isinstance(result, dict):
                        result["output"] = (result.get("output", "") + f"\n[warnings: {warnings}]").strip()
                return result
            except json.JSONDecodeError:
                # Plain text output
                return stdout

        except subprocess.TimeoutExpired:
            logger.error(f"Plugin '{tool_id}' timed out after {timeout}s")
            return f"Error: Plugin '{tool_id}' timed out after {timeout} seconds. Try simplifying the operation."
        except Exception as e:
            logger.error(f"Plugin execution error for {tool_id}: {traceback.format_exc()}")
            return f"Error executing plugin '{tool_id}': {str(e)}"


# Singleton instance
plugin_loader = PluginLoader()
