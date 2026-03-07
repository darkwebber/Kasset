"""
Plugin Loader — discovers, validates, and executes custom tool plugins for Kasset.

Tool Plugin Standard:
    ~/.qwen-studio/tools/<tool-id>/
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
import importlib.util
import traceback
import sys
import io
import contextlib
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

USER_TOOLS_DIR = Path.home() / ".qwen-studio" / "tools"


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
        }


class PluginLoader:
    """Discovers and manages custom tool plugins."""

    def __init__(self, tools_dir: Path = USER_TOOLS_DIR):
        self.tools_dir = tools_dir
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        self.manifests: Dict[str, ToolManifest] = {}
        self._loaded_modules: Dict[str, Any] = {}
        self.load_all()

    def load_all(self):
        """Discover and load all tool plugins from the tools directory."""
        self.manifests.clear()
        self._loaded_modules.clear()

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

    def _load_handler_module(self, manifest: ToolManifest):
        """Dynamically load the handler Python module."""
        handler_path = manifest.directory / manifest.handler_file
        if not handler_path.exists():
            raise FileNotFoundError(f"Handler not found: {handler_path}")

        module_name = f"_qwen_plugin_{manifest.id}"

        # Remove old module if reloading
        if module_name in sys.modules:
            del sys.modules[module_name]

        spec = importlib.util.spec_from_file_location(module_name, str(handler_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {handler_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        # Pre-run sandbox imports if specified
        sandbox_cfg = manifest.sandbox
        if sandbox_cfg.get("pre_run"):
            exec(sandbox_cfg["pre_run"], module.__dict__)

        spec.loader.exec_module(module)
        self._loaded_modules[manifest.id] = module
        return module

    def execute_tool(self, tool_id: str, args: dict) -> Any:
        """Execute a plugin tool with the given arguments.

        Returns:
            str or dict with keys: output, images (optional), html (optional)
        """
        manifest = self.manifests.get(tool_id)
        if not manifest:
            return f"Error: Plugin tool '{tool_id}' not found"

        try:
            # Load module if not cached
            if tool_id not in self._loaded_modules:
                self._load_handler_module(manifest)

            module = self._loaded_modules[tool_id]
            entry_fn = getattr(module, manifest.entry_point, None)
            if entry_fn is None:
                return f"Error: Entry point '{manifest.entry_point}' not found in handler"

            # Filter args to only declared parameters
            valid_args = {}
            for k, v in args.items():
                if k in manifest.parameters:
                    valid_args[k] = v

            # Capture stdout
            output_capture = io.StringIO()
            result = None
            with contextlib.redirect_stdout(output_capture):
                result = entry_fn(**valid_args)

            stdout = output_capture.getvalue()

            # Normalize result
            if result is None:
                return stdout.strip() or "Tool executed successfully (no output)."
            if isinstance(result, str):
                combined = (stdout + "\n" + result).strip() if stdout else result
                return combined
            if isinstance(result, dict):
                # Merge stdout into output
                if stdout:
                    result["output"] = (stdout + "\n" + result.get("output", "")).strip()
                return result

            return str(result)

        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Plugin execution error for {tool_id}: {tb}")
            return f"Error executing plugin '{tool_id}': {str(e)}"


# Singleton instance
plugin_loader = PluginLoader()
