import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class Theme(BaseModel):
    accent_color: str = "#00ff88"
    screen_tint: str = "rgba(0, 255, 136, 0.02)"
    scanline_intensity: float = 0.15
    glow_color: str = "#00ff88"
    boot_animation: str = "fade"

class StackingRules(BaseModel):
    stackable: bool = True
    priority: int = 50
    role: str = "primary"
    conflicts_with: List[str] = []
    requires: List[str] = []
    merge_strategy: str = "append"

class WorkflowStep(BaseModel):
    name: str
    description: str
    steps: List[str]

class Cartridge(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    author: str
    version: str
    tags: List[str]
    system_prompt: str
    tools: List[str]
    theme: Theme = Field(default_factory=Theme)
    boot_message: Optional[str] = None
    stacking: StackingRules = Field(default_factory=StackingRules)
    workflows: List[WorkflowStep] = []
    suggested_prompts: List[str] = []
    suggested_tokens: int = 4096
    suggested_thinking: bool = True
    suggested_max_rounds: int = 6
    suggested_temperature: Optional[float] = None
    suggested_top_p: Optional[float] = None
    memory_enabled: bool = False
    suggested_model: Optional[str] = None
    # Sharing / distribution metadata (optional)
    long_description: Optional[str] = None
    repository: Optional[str] = None
    homepage: Optional[str] = None
    license: Optional[str] = None
    min_app_version: Optional[str] = None
    readme: Optional[str] = None

    class Config:
        extra = "allow"  # Forward-compatible: ignore unknown fields from newer versions

class LoadedConfig(BaseModel):
    merged_prompt: str
    tools: List[str]
    theme: Theme
    boot_messages: List[str]
    active_cartridge_ids: List[str]
    suggested_prompts: List[str]
    suggested_tokens: int
    suggested_thinking: bool
    suggested_max_rounds: int = 6
    suggested_temperature: Optional[float] = None
    suggested_top_p: Optional[float] = None
    suggested_model: Optional[str] = None
    input_methods: List[Dict[str, Any]] = []

class CartridgeLoader:
    def __init__(self, cartridges_dir: str = "cartridges/builtins"):
        self.builtins_dir = Path(cartridges_dir)
        self.user_dir = Path.home() / ".kasset" / "cartridges"
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.registry: Dict[str, Cartridge] = {}
        self._sources: Dict[str, str] = {}  # id -> "builtin" | "user"
        self._file_mtimes: Dict[str, float] = {}  # path -> last mtime
        self._path_to_id: Dict[str, str] = {}  # path -> cartridge id
        self.load_all()

    def load_all(self):
        """Load all cartridges from builtins and user directories."""
        self.registry.clear()
        self._sources.clear()
        self._load_from_dir(self.builtins_dir, "builtin")
        self._load_from_dir(self.user_dir, "user")

    def _refresh(self):
        """Incrementally refresh: only re-parse files whose mtime changed or are new.
        Also removes cartridges whose files were deleted."""
        current_files: Dict[str, tuple] = {}  # path_str -> (directory, source)
        for directory, source in [(self.builtins_dir, "builtin"), (self.user_dir, "user")]:
            if not directory.exists():
                continue
            for path in directory.glob("*.json"):
                current_files[str(path)] = (path, source)

        # Detect deleted files
        deleted_paths = set(self._file_mtimes.keys()) - set(current_files.keys())
        for dp in deleted_paths:
            cid = self._path_to_id.pop(dp, None)
            self._file_mtimes.pop(dp, None)
            if cid:
                self.registry.pop(cid, None)
                self._sources.pop(cid, None)

        # Load new or modified files
        changed = False
        for path_str, (path, source) in current_files.items():
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if path_str in self._file_mtimes and self._file_mtimes[path_str] == mtime:
                continue  # Unchanged
            # Parse and register
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                cart = Cartridge(**data)
                # If this path previously held a different cartridge id, remove the old one
                old_id = self._path_to_id.get(path_str)
                if old_id and old_id != cart.id:
                    self.registry.pop(old_id, None)
                    self._sources.pop(old_id, None)
                self.registry[cart.id] = cart
                self._sources[cart.id] = source
                self._file_mtimes[path_str] = mtime
                self._path_to_id[path_str] = cart.id
                changed = True
                logger.info(f"Refreshed {source} cartridge: {cart.id} v{cart.version}")
            except Exception as e:
                logger.error(f"Failed to load cartridge {path}: {e}")
        return changed

    def _load_from_dir(self, directory: Path, source: str):
        """Load cartridges from a directory."""
        if not directory.exists():
            return
        for path in directory.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                cart = Cartridge(**data)
                # Warn on ID collision between user and builtin
                if cart.id in self.registry and self._sources.get(cart.id) != source:
                    logger.warning(
                        f"User cartridge '{cart.id}' overrides builtin cartridge with same ID"
                    )
                self.registry[cart.id] = cart
                self._sources[cart.id] = source
                self._file_mtimes[str(path)] = path.stat().st_mtime
                self._path_to_id[str(path)] = cart.id
                logger.info(f"Loaded {source} cartridge: {cart.id} v{cart.version}")
            except Exception as e:
                logger.error(f"Failed to load cartridge {path}: {e}")

    def save_user_cartridge(self, data: dict) -> dict:
        """Save a user cartridge to ~/.kasset/cartridges/. Returns the saved data."""
        cart = Cartridge(**data)
        dest = self.user_dir / f"{cart.id}.json"
        dest.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.registry[cart.id] = cart
        self._sources[cart.id] = "user"
        logger.info(f"Saved user cartridge: {cart.id}")
        return data

    def delete_user_cartridge(self, cartridge_id: str) -> bool:
        """Delete a user cartridge. Cannot delete builtins."""
        if self._sources.get(cartridge_id) != "user":
            return False
        dest = self.user_dir / f"{cartridge_id}.json"
        if dest.exists():
            dest.unlink()
        self.registry.pop(cartridge_id, None)
        self._sources.pop(cartridge_id, None)
        return True

    def get_cartridge_source(self, cartridge_id: str) -> str:
        """Return 'builtin' or 'user' for a cartridge."""
        return self._sources.get(cartridge_id, "unknown")

    def get_cartridge_raw(self, cartridge_id: str) -> Optional[dict]:
        """Return the raw JSON for a cartridge (for editing)."""
        cart = self.registry.get(cartridge_id)
        if not cart:
            return None
        return json.loads(cart.model_dump_json())

    def get_workflows(self, cartridge_id: str) -> List[Dict[str, Any]]:
        """Return workflows for a cartridge."""
        cart = self.registry.get(cartridge_id)
        if not cart or not cart.workflows:
            return []
        return [
            {"name": w.name, "description": w.description, "steps": w.steps}
            for w in cart.workflows
        ]

    def list_available(self) -> List[Dict[str, Any]]:
        """Return list of available cartridges for the store/drawer UI."""
        return [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "icon": c.icon,
                "author": c.author,
                "version": c.version,
                "tags": c.tags,
                "role": c.stacking.role,
                "source": self._sources.get(c.id, "builtin"),
                "tools": c.tools,
                "workflows": [{"name": w.name, "description": w.description} for w in c.workflows],
                "theme": {
                    "accent_color": c.theme.accent_color,
                    "glow_color": c.theme.glow_color,
                },
                # Sharing metadata (optional — may be None)
                **({"repository": c.repository} if c.repository else {}),
                **({"homepage": c.homepage} if c.homepage else {}),
                **({"license": c.license} if c.license else {}),
                **({"readme": c.readme} if c.readme else {}),
                **({"long_description": c.long_description} if c.long_description else {}),
            }
            for c in self.registry.values()
        ]

    def load_stack(self, cartridge_ids: List[str]) -> LoadedConfig:
        """Merge a stack of cartridges into a single config."""
        self._refresh()  # Incrementally check for changed/new/deleted files
        carts = []
        for cid in cartridge_ids:
            if cid not in self.registry:
                raise ValueError(f"Cartridge '{cid}' not found")
            carts.append(self.registry[cid])

        if not carts:
            raise ValueError("No cartridges specified")

        # Enforce stacking constraints
        id_set = set(cartridge_ids)
        for c in carts:
            for conflict in c.stacking.conflicts_with:
                if conflict in id_set:
                    raise ValueError(
                        f"Cartridge '{c.id}' conflicts with '{conflict}' — they cannot be stacked together"
                    )
            for req in c.stacking.requires:
                if req not in id_set:
                    raise ValueError(
                        f"Cartridge '{c.id}' requires '{req}' to be loaded"
                    )

        # Sort by priority (higher priority = processed later = overwrites earlier)
        carts.sort(key=lambda c: c.stacking.priority)

        # Merge System Prompts
        merged_prompt = ""
        for c in carts:
            if c.stacking.merge_strategy == "append":
                merged_prompt = f"{merged_prompt}\n\n{c.system_prompt}" if merged_prompt else c.system_prompt
            elif c.stacking.merge_strategy == "prepend":
                merged_prompt = f"{c.system_prompt}\n\n{merged_prompt}" if merged_prompt else c.system_prompt
            elif c.stacking.merge_strategy == "replace":
                merged_prompt = c.system_prompt

        # Union Tools
        tools_set = set()
        for c in carts:
            tools_set.update(c.tools)

        # Theme (base from primary, accent from highest priority aux)
        primaries = [c for c in carts if c.stacking.role == "primary"]
        base_theme = primaries[0].theme if primaries else carts[0].theme
        final_theme = Theme(**base_theme.model_dump())
        
        # Apply accent from highest priority cartridge
        final_theme.accent_color = carts[-1].theme.accent_color
        final_theme.glow_color = carts[-1].theme.glow_color

        # Collect boot messages
        boot_messages = [c.boot_message for c in carts if c.boot_message]

        # Collect suggested prompts (primary cartridge first, then others)
        suggested_prompts: List[str] = []
        for c in carts:
            for p in c.suggested_prompts:
                if p not in suggested_prompts:
                    suggested_prompts.append(p)

        # Collect custom input method templates (optional)
        # Methods can be either inline dicts or string IDs referencing standalone input types
        input_methods: List[Dict[str, Any]] = []
        seen_method_ids = set()
        
        # Import input type loader for resolving string references
        try:
            from .input_type_loader import input_type_loader
        except ImportError:
            input_type_loader = None
        
        for c in carts:
            methods = getattr(c, "input_methods", []) or []
            if not isinstance(methods, list):
                continue
            for m in methods:
                # Resolve string IDs from InputTypeLoader
                if isinstance(m, str) and input_type_loader:
                    resolved = input_type_loader.resolve_input_method(m)
                    if resolved:
                        m = resolved
                    else:
                        continue
                if not isinstance(m, dict):
                    continue
                mid = str(m.get("id", "")).strip() or f"method-{len(input_methods)+1}"
                if mid in seen_method_ids:
                    continue
                seen_method_ids.add(mid)
                input_methods.append(m)

        # Validate tool IDs against known tools (warn, don't error — plugins may load later)
        try:
            from .tool_registry import BUILTIN_TOOLS
            from .plugin_loader import plugin_loader
            known_tools = set(BUILTIN_TOOLS.keys()) | set(plugin_loader.manifests.keys())
            for t in tools_set:
                if t not in known_tools:
                    logger.warning(f"Cartridge references unknown tool '{t}' — it may not work at runtime")
        except Exception:
            pass  # Don't fail stack loading if validation imports fail

        return LoadedConfig(
            merged_prompt=merged_prompt.strip(),
            tools=list(tools_set),
            theme=final_theme,
            boot_messages=boot_messages,
            active_cartridge_ids=cartridge_ids,
            suggested_prompts=suggested_prompts[:6],
            suggested_tokens=carts[-1].suggested_tokens,
            suggested_thinking=carts[-1].suggested_thinking,
            suggested_max_rounds=max(c.suggested_max_rounds for c in carts),
            suggested_temperature=next((c.suggested_temperature for c in reversed(carts) if c.suggested_temperature is not None), None),
            suggested_top_p=next((c.suggested_top_p for c in reversed(carts) if c.suggested_top_p is not None), None),
            suggested_model=next((c.suggested_model for c in reversed(carts) if c.suggested_model), None),
            input_methods=input_methods,
        )
