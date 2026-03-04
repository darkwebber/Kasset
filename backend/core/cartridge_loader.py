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
    suggested_tokens: int = 4096
    suggested_thinking: bool = True
    memory_enabled: bool = False

class LoadedConfig(BaseModel):
    merged_prompt: str
    tools: List[str]
    theme: Theme
    boot_messages: List[str]
    active_cartridge_ids: List[str]
    suggested_tokens: int
    suggested_thinking: bool

class CartridgeLoader:
    def __init__(self, cartridges_dir: str = "cartridges/builtins"):
        self.cartridges_dir = Path(cartridges_dir)
        self.registry: Dict[str, Cartridge] = {}
        self.load_all()

    def load_all(self):
        """Load all cartridges from disk."""
        if not self.cartridges_dir.exists():
            logger.warning(f"Cartridge directory {self.cartridges_dir} not found")
            return
            
        for path in self.cartridges_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                cart = Cartridge(**data)
                self.registry[cart.id] = cart
                logger.info(f"Loaded cartridge: {cart.id} v{cart.version}")
            except Exception as e:
                logger.error(f"Failed to load cartridge {path}: {e}")

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
                "role": c.stacking.role
            }
            for c in self.registry.values()
        ]

    def load_stack(self, cartridge_ids: List[str]) -> LoadedConfig:
        """Merge a stack of cartridges into a single config."""
        carts = []
        for cid in cartridge_ids:
            if cid not in self.registry:
                raise ValueError(f"Cartridge '{cid}' not found")
            carts.append(self.registry[cid])

        if not carts:
            raise ValueError("No cartridges specified")

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

        return LoadedConfig(
            merged_prompt=merged_prompt.strip(),
            tools=list(tools_set),
            theme=final_theme,
            boot_messages=boot_messages,
            active_cartridge_ids=cartridge_ids,
            suggested_tokens=carts[-1].suggested_tokens,
            suggested_thinking=carts[-1].suggested_thinking
        )
