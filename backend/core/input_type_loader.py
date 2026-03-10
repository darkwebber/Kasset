"""
Input Type Loader — manages standalone, shareable input types.

Input types are user-created widgets (forms, sliders, editors, choices)
that can be independently shared and referenced by kassets by ID.

Storage: ~/.kasset/input_types/<type-id>/manifest.json
Optional: ~/.kasset/input_types/<type-id>/handler.py (custom validation)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

INPUT_TYPES_DIR = Path.home() / ".kasset" / "input_types"
INPUT_TYPES_DIR.mkdir(parents=True, exist_ok=True)

# Builtin input types shipped with the app
BUILTIN_INPUT_TYPES_DIR = Path(__file__).resolve().parent.parent.parent / "cartridges" / "builtins" / "input_types"


class InputTypeLoader:
    """
    Loads and manages standalone input type manifests.
    
    Follows the same pattern as PluginLoader:
    - Each input type is a directory with manifest.json
    - Optional handler.py for custom validation
    - Supports CRUD operations for the Forge API
    """

    def __init__(self, input_types_dir: Path = INPUT_TYPES_DIR, builtin_dir: Path = BUILTIN_INPUT_TYPES_DIR):
        self.base_dir = input_types_dir
        self.builtin_dir = builtin_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.manifests: Dict[str, dict] = {}
        self._builtin_ids: set = set()
        self.load_all()

    def _load_from_dir(self, directory: Path, source: str = "user") -> int:
        """Load input type manifests from a directory. Returns count loaded."""
        count = 0
        if not directory.exists():
            return 0

        for type_dir in sorted(directory.iterdir()):
            if not type_dir.is_dir():
                continue
            manifest_path = type_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text())
                type_id = manifest.get("id") or type_dir.name
                manifest["id"] = type_id
                manifest["_path"] = str(type_dir)
                manifest["_source"] = source
                self.manifests[type_id] = manifest
                if source == "builtin":
                    self._builtin_ids.add(type_id)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to load input type from {type_dir}: {e}")
        return count

    def load_all(self) -> int:
        """Load all input type manifests. Builtins first, then user (user overrides)."""
        self.manifests.clear()
        self._builtin_ids.clear()

        builtin_count = self._load_from_dir(self.builtin_dir, source="builtin")
        user_count = self._load_from_dir(self.base_dir, source="user")
        total = len(self.manifests)

        logger.info(f"Loaded {total} input types ({builtin_count} builtin, {user_count} user)")
        return total

    def reload(self) -> int:
        """Reload all manifests from disk."""
        return self.load_all()

    def list_types(self) -> List[dict]:
        """List all input types as manifest dicts (without internal fields)."""
        return [
            {**{k: v for k, v in m.items() if not k.startswith("_")}, "source": m.get("_source", "user")}
            for m in self.manifests.values()
        ]

    def get_manifest(self, type_id: str) -> Optional[dict]:
        """Get a specific input type manifest."""
        m = self.manifests.get(type_id)
        if m:
            return {k: v for k, v in m.items() if not k.startswith("_")}
        return None

    def get_descriptions(self) -> Dict[str, dict]:
        """Get short descriptions of all types, suitable for system prompt injection."""
        descs = {}
        for tid, m in self.manifests.items():
            descs[tid] = {
                "name": m.get("name", tid),
                "widget_type": m.get("widget_type", "custom"),
                "description": m.get("description", ""),
            }
        return descs

    def resolve_input_method(self, method_ref) -> Optional[dict]:
        """
        Resolve an input method reference.
        
        - If method_ref is a string: look up by ID from loaded manifests
        - If method_ref is a dict: return as-is (inline definition)
        """
        if isinstance(method_ref, dict):
            return method_ref
        if isinstance(method_ref, str):
            manifest = self.manifests.get(method_ref)
            if manifest:
                # Convert manifest to input_method format
                return {
                    "id": method_ref,
                    "name": manifest.get("name", method_ref),
                    "description": manifest.get("description", ""),
                    "widget_type": manifest.get("widget_type", "custom"),
                    "example": manifest.get("config_template"),
                }
            logger.warning(f"Input type '{method_ref}' not found in loader")
        return None

    # ─── CRUD for Forge API ──────────────────────

    def create_or_update(self, manifest: dict) -> dict:
        """Create or update an input type. Returns saved manifest."""
        type_id = manifest.get("id")
        if not type_id:
            raise ValueError("Input type manifest must have an 'id' field")

        # Sanitize ID
        import re
        type_id = re.sub(r'[^a-z0-9_-]', '-', type_id.lower().strip())
        manifest["id"] = type_id

        # Ensure required fields
        manifest.setdefault("name", type_id)
        manifest.setdefault("version", "1.0.0")
        manifest.setdefault("widget_type", "form")
        manifest.setdefault("author", "user")

        # Save to disk
        type_dir = self.base_dir / type_id
        type_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = type_dir / "manifest.json"
        
        # Remove internal fields before saving
        save_data = {k: v for k, v in manifest.items() if not k.startswith("_")}
        manifest_path.write_text(json.dumps(save_data, indent=2, ensure_ascii=False))

        # Reload into memory
        manifest["_path"] = str(type_dir)
        self.manifests[type_id] = manifest
        
        logger.info(f"Saved input type: {type_id}")
        return save_data

    def delete(self, type_id: str) -> bool:
        """Delete a user input type. Builtin types cannot be deleted."""
        if type_id in self._builtin_ids:
            raise ValueError(f"Cannot delete builtin input type '{type_id}'")
        type_dir = self.base_dir / type_id
        if type_dir.exists():
            import shutil
            shutil.rmtree(type_dir)
            self.manifests.pop(type_id, None)
            logger.info(f"Deleted input type: {type_id}")
            return True
        return False

    def save_handler(self, type_id: str, handler_code: str) -> bool:
        """Save a custom handler.py for an input type."""
        type_dir = self.base_dir / type_id
        if not type_dir.exists():
            return False
        handler_path = type_dir / "handler.py"
        handler_path.write_text(handler_code)
        return True


# Singleton instance
input_type_loader = InputTypeLoader()
