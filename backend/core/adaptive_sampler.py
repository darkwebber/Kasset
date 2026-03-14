"""
adaptive_sampler.py — Adaptive sampling parameter control for Qwen3.5.

Selects optimal temperature/top_p/top_k based on task context:
- Code generation: low temp (0.6) for precision
- Creative writing: higher temp (0.9) for variety
- General chat: moderate temp (0.7)
- Tool calling: low temp (0.6) for reliable JSON/XML

Based on Qwen3.5 official recommendations:
- Thinking + precise coding: temp=0.6, top_p=0.95, top_k=20
- Thinking + general: temp=0.7, top_p=0.95, top_k=20
- Creative: temp=0.9, top_p=0.95, top_k=40
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


@dataclass
class SamplingParams:
    """Resolved sampling parameters for a generation call."""
    temperature: float
    top_p: float
    top_k: int
    repetition_penalty: float = 1.0

    def as_dict(self) -> dict:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "repetition_penalty": self.repetition_penalty,
        }


# Named presets
PRESETS = {
    "code": SamplingParams(temperature=0.6, top_p=0.95, top_k=20),
    "precise": SamplingParams(temperature=0.6, top_p=0.95, top_k=20),
    "general": SamplingParams(temperature=0.7, top_p=0.95, top_k=20),
    "creative": SamplingParams(temperature=0.9, top_p=0.95, top_k=40),
    "tool_retry": SamplingParams(temperature=0.5, top_p=0.90, top_k=15),
}

# Cartridge ID → preset mapping
_CARTRIDGE_PRESETS: Dict[str, str] = {
    "code-pilot": "code",
    "3d-visualizer": "code",
    "data-analyst": "code",
    "devops": "code",
    "image-editor": "code",
    "tutor": "general",
    "writer": "creative",
    "web-pilot": "general",
    "general-assistant": "general",
}

# Patterns in user messages that suggest code tasks
_CODE_PATTERNS = [
    r'\b(write|create|generate|implement|code|script|function|class|debug|fix|refactor)\b.*\b(code|program|script|function|class|module|api|endpoint|component)\b',
    r'\b(python|javascript|typescript|cpp|c\+\+|rust|java|html|css|sql)\b',
    r'\b(execute|run|compile|build|deploy|test)\b',
]

_CREATIVE_PATTERNS = [
    r'\b(write|draft|compose|create)\b.*\b(story|poem|essay|article|blog|letter|email|novel|song|lyrics)\b',
    r'\b(creative|imaginative|poetic|literary|narrative)\b',
    r'\b(brainstorm|ideate|inspire)\b',
]


class AdaptiveSampler:
    """Selects sampling parameters based on context."""

    @classmethod
    def resolve(
        cls,
        cartridge_ids: Optional[List[str]] = None,
        user_message: str = "",
        tool_round: int = 0,
        is_retry: bool = False,
        override_temp: Optional[float] = None,
        override_top_p: Optional[float] = None,
    ) -> SamplingParams:
        """Resolve the best sampling parameters for this generation.

        Priority order:
        1. Explicit overrides from cartridge config (override_temp/override_top_p)
        2. Retry preset (lower temp for more deterministic retry)
        3. Cartridge preset mapping
        4. User message content analysis
        5. Default (general)
        """
        # Start with default
        preset_name = "general"

        # Check cartridge preset
        if cartridge_ids:
            for cid in cartridge_ids:
                if cid in _CARTRIDGE_PRESETS:
                    preset_name = _CARTRIDGE_PRESETS[cid]
                    break

        # Content analysis (only if not already matched by cartridge)
        if preset_name == "general" and user_message:
            msg_lower = user_message.lower()
            for pattern in _CODE_PATTERNS:
                if re.search(pattern, msg_lower):
                    preset_name = "code"
                    break
            if preset_name == "general":
                for pattern in _CREATIVE_PATTERNS:
                    if re.search(pattern, msg_lower):
                        preset_name = "creative"
                        break

        # Retry override: use lower temp for more deterministic output
        if is_retry:
            preset_name = "tool_retry"

        # Tool rounds 2+: slightly lower temp for consistency
        params = SamplingParams(**PRESETS[preset_name].__dict__)
        if tool_round >= 2 and preset_name != "tool_retry":
            params.temperature = max(0.5, params.temperature - 0.1)

        # Apply explicit overrides (cartridge-level config takes highest priority)
        if override_temp is not None:
            params.temperature = override_temp
        if override_top_p is not None:
            params.top_p = override_top_p

        logger.debug(
            f"AdaptiveSampler: preset={preset_name}, "
            f"temp={params.temperature}, top_p={params.top_p}, "
            f"round={tool_round}, retry={is_retry}"
        )
        return params
