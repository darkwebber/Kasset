"""
Multi-layer context management system.

Three layers of context:
1. Session Context — in-session summarization when conversations get long
2. Cartridge Context — persistent understanding per cartridge across chats
3. Global Profile — app-wide user understanding across all cartridges

Each layer can be toggled on/off by the user via UserSettings.
"""

import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from backend.core.shared import (
    atomic_write_json as _atomic_write_json,
    CONTEXT_DIR, GLOBAL_PROFILE_FILE, SETTINGS_FILE,
)

logger = logging.getLogger(__name__)

CARTRIDGE_CONTEXT_DIR = CONTEXT_DIR / "cartridges"


# ═══════════════════════════════════════════
# USER SETTINGS
# ═══════════════════════════════════════════

class UserSettings:
    """User preferences and toggles for context management."""

    DEFAULT_RSS_FEEDS = [
        {"name": "Hacker News", "url": "https://news.ycombinator.com/rss"},
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
        {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
        {"name": "BBC News", "url": "http://feeds.bbci.co.uk/news/rss.xml"},
    ]

    DEFAULTS = {
        "context": {
            "use_session_summary": True,
            "use_cartridge_context": True,
            "use_global_profile": True,
        },
    }

    def __init__(self):
        self._settings: Dict[str, Any] = {}
        self._load()

    def _load(self):
        if SETTINGS_FILE.exists():
            try:
                self._settings = json.loads(SETTINGS_FILE.read_text())
            except Exception:
                self._settings = {}
        # Merge with defaults
        for key, defaults in self.DEFAULTS.items():
            if key not in self._settings:
                self._settings[key] = dict(defaults)
            else:
                for dk, dv in defaults.items():
                    if dk not in self._settings[key]:
                        self._settings[key][dk] = dv

    def _save(self):
        _atomic_write_json(SETTINGS_FILE, self._settings)

    def get(self, section: str, key: str) -> Any:
        return self._settings.get(section, {}).get(
            key, self.DEFAULTS.get(section, {}).get(key)
        )

    def set(self, section: str, key: str, value: Any):
        if section not in self._settings:
            self._settings[section] = {}
        self._settings[section][key] = value
        self._save()

    def get_all(self) -> Dict[str, Any]:
        return dict(self._settings)

    def update_section(self, section: str, values: Dict[str, Any]):
        if section not in self._settings:
            self._settings[section] = {}
        self._settings[section].update(values)
        self._save()

    def get_rss_feeds(self) -> list:
        feeds = self._settings.get("rss_feeds", [])
        if not feeds:
            return list(self.DEFAULT_RSS_FEEDS)
        return feeds

    def set_rss_feeds(self, feeds: list):
        self._settings["rss_feeds"] = feeds
        self._save()


# ═══════════════════════════════════════════
# SESSION SUMMARIZER
# ═══════════════════════════════════════════

class SessionSummarizer:
    """
    Manages in-session context compression.
    When a conversation gets too long, creates a structured summary
    of older messages to free up context space while preserving key information.
    """

    @staticmethod
    def summarize_messages(messages: List[Dict[str, str]], max_chars: int = 2000) -> str:
        """
        Create a structured summary of messages.
        Extracts: user intents, tool actions, key conclusions.
        Heuristic-based (no model call needed — fast).
        """
        user_intents = []
        tool_actions = []
        key_results = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                if content.startswith("Tool result for "):
                    # Extract tool name and result preview
                    after = content[len("Tool result for "):]
                    colon = after.find(":")
                    if colon > 0:
                        tool_name = after[:colon].strip()
                        result_preview = after[colon + 1:colon + 201].strip()
                        tool_actions.append(f"{tool_name} → {result_preview}")
                else:
                    clean = content.strip()
                    clean = re.sub(r'\[Attached file:.*?\]', '[file]', clean)
                    clean = re.sub(
                        r'<attached_context.*?</attached_context>', '',
                        clean, flags=re.DOTALL
                    ).strip()
                    if clean and len(clean) > 5:
                        user_intents.append(clean[:150])

            elif role == "assistant":
                lines = content.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if (line and not line.startswith('<')
                            and not line.startswith('{') and len(line) > 20):
                        key_results.append(line[:150])
                        break

        parts = []
        if user_intents:
            parts.append("User asked: " + "; ".join(user_intents[-4:]))
        if tool_actions:
            parts.append("Tools used: " + "; ".join(tool_actions[-6:]))
        if key_results:
            parts.append("Key results: " + "; ".join(key_results[-3:]))

        summary = " | ".join(parts) if parts else "General conversation"

        if len(summary) > max_chars:
            summary = summary[:max_chars] + "..."

        return summary

    @staticmethod
    def create_summary_message(
        dropped_messages: List[Dict], dropped_count: int
    ) -> Dict[str, str]:
        """Create a system message containing the summary of dropped messages."""
        summary = SessionSummarizer.summarize_messages(dropped_messages)
        return {
            "role": "system",
            "content": (
                f"[Session context — {dropped_count} earlier messages summarized: "
                f"{summary}]"
            ),
        }


# ═══════════════════════════════════════════
# CARTRIDGE CONTEXT
# ═══════════════════════════════════════════

class CartridgeContext:
    """
    Persistent context for each cartridge.
    Tracks what the user has done with this cartridge across multiple chats.
    Gives the agent continuity and understanding of the user's relationship
    with this role.
    """

    MAX_TOPICS = 30
    MAX_LEARNINGS = 20

    @staticmethod
    def _path(cartridge_id: str) -> Path:
        return CARTRIDGE_CONTEXT_DIR / f"{cartridge_id}.json"

    @staticmethod
    def load(cartridge_id: str) -> Dict[str, Any]:
        path = CartridgeContext._path(cartridge_id)
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
        return {
            "cartridge_id": cartridge_id,
            "chat_count": 0,
            "first_used": None,
            "last_used": None,
            "topics": [],
            "learnings": [],
        }

    @staticmethod
    def save(cartridge_id: str, data: Dict[str, Any]):
        path = CartridgeContext._path(cartridge_id)
        _atomic_write_json(path, data)

    @staticmethod
    def update_from_chat(
        cartridge_id: str, messages: List[Dict], chat_title: str = "", graph: Optional[Any] = None
    ):
        """
        Update cartridge context after a chat session.
        Extracts topics and user intents from the conversation.
        If a graph is provided, distills high-importance discoveries into cross-session learnings.
        """
        ctx = CartridgeContext.load(cartridge_id)
        now = datetime.now().isoformat()

        ctx["chat_count"] = ctx.get("chat_count", 0) + 1
        if not ctx.get("first_used"):
            ctx["first_used"] = now
        ctx["last_used"] = now

        existing_topics = {t["text"].lower().strip() for t in ctx.get("topics", [])}

        # Add chat title as a topic
        if chat_title and chat_title != "New conversation":
            if chat_title.lower().strip() not in existing_topics:
                ctx.setdefault("topics", []).append(
                    {"text": chat_title, "date": now}
                )
                existing_topics.add(chat_title)

        # Extract key intents from user messages
        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if content.startswith("Tool result"):
                continue
            clean = re.sub(r'\[Attached file:.*?\]', '', content).strip()
            clean = re.sub(
                r'<attached_context.*?</attached_context>', '',
                clean, flags=re.DOTALL
            ).strip()
            if clean and len(clean) > 15:
                topic = clean[:80]
                if topic.lower().strip() not in existing_topics:
                    ctx.setdefault("topics", []).append(
                        {"text": topic, "date": now}
                    )
                    existing_topics.add(topic)

        # Trim to max entries
        if len(ctx.get("topics", [])) > CartridgeContext.MAX_TOPICS:
            ctx["topics"] = ctx["topics"][-CartridgeContext.MAX_TOPICS:]

        # Distill Knowledge Graph into cross-session learnings
        if graph:
            from .knowledge_graph import ConversationGraph
            if isinstance(graph, ConversationGraph):
                existing_learnings = {str(l).lower().strip() for l in ctx.get("learnings", []) if isinstance(l, str)}
                for nid, node in graph.nodes.items():
                    if node.type in ("concept", "note"):
                        # Only distill high importance concepts or explicit notes
                        if node.type == "note" or node.importance >= 0.7:
                            learning_text = f"Discovered: {node.content} ({node.type})"
                            if learning_text.lower().strip() not in existing_learnings:
                                ctx.setdefault("learnings", []).append(learning_text)
                                existing_learnings.add(learning_text.lower().strip())
                
                if len(ctx.get("learnings", [])) > CartridgeContext.MAX_LEARNINGS:
                    ctx["learnings"] = ctx["learnings"][-CartridgeContext.MAX_LEARNINGS:]

        CartridgeContext.save(cartridge_id, ctx)
        logger.info(
            f"Cartridge context '{cartridge_id}': "
            f"{ctx['chat_count']} chats, {len(ctx.get('topics', []))} topics"
        )

    @staticmethod
    def add_learning(cartridge_id: str, learning: str):
        """Add a specific learning about the user for this cartridge."""
        ctx = CartridgeContext.load(cartridge_id)
        existing = {str(l) for l in ctx.get("learnings", []) if isinstance(l, str)}
        if learning not in existing:
            ctx.setdefault("learnings", []).append(learning)
            if len(ctx["learnings"]) > CartridgeContext.MAX_LEARNINGS:
                ctx["learnings"] = ctx["learnings"][-CartridgeContext.MAX_LEARNINGS:]
            CartridgeContext.save(cartridge_id, ctx)

    @staticmethod
    def get_context_block(cartridge_id: str) -> str:
        """Build a context block string to inject into system prompts."""
        ctx = CartridgeContext.load(cartridge_id)

        if ctx.get("chat_count", 0) == 0:
            return ""

        parts = [
            f"\n\n## Cartridge History "
            f"({ctx['chat_count']} previous sessions)"
        ]

        if ctx.get("topics"):
            recent = ctx["topics"][-10:]
            texts = [t["text"] for t in recent]
            parts.append(f"**Recent topics:** {'; '.join(texts)}")

        if ctx.get("learnings"):
            parts.append("**Learnings about this user:**")
            for l in ctx["learnings"][-5:]:
                parts.append(f"- {l}")

        # Inject feedback patterns from saved chats for this cartridge
        try:
            feedback_block = CartridgeContext._get_feedback_patterns(cartridge_id)
            if feedback_block:
                parts.append(feedback_block)
        except Exception:
            pass

        return "\n".join(parts)

    # TTL cache for feedback pattern scans (avoids re-scanning 50 files every call)
    _feedback_cache: dict = {}  # {cartridge_id: {"result": str, "ts": float}}
    _FEEDBACK_CACHE_TTL = 300  # 5 minutes

    @staticmethod
    def _get_feedback_patterns(cartridge_id: str) -> str:
        """Extract recent negative feedback patterns for this cartridge from saved chats."""
        import time as _time
        cache = CartridgeContext._feedback_cache.get(cartridge_id)
        if cache and (_time.time() - cache["ts"]) < CartridgeContext._FEEDBACK_CACHE_TTL:
            return cache["result"]

        from backend.core.shared import CHATS_DIR
        down_snippets = []
        up_count = 0
        down_count = 0

        for f in sorted(CHATS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:50]:
            try:
                import json as _json
                data = _json.loads(f.read_text())
                # Only process chats that used this cartridge
                if cartridge_id not in data.get("cartridge_ids", []):
                    continue
                feedback = data.get("feedback", {})
                messages = data.get("messages", [])
                for idx_str, fb in feedback.items():
                    if fb.get("rating") == "up":
                        up_count += 1
                    elif fb.get("rating") == "down":
                        down_count += 1
                        idx = int(idx_str)
                        # Get the user message BEFORE the downvoted assistant message
                        if idx > 0 and idx < len(messages):
                            user_msg = ""
                            for i in range(idx - 1, -1, -1):
                                if messages[i].get("role") == "user":
                                    user_msg = messages[i].get("content", "")[:100]
                                    break
                            assistant_msg = messages[idx].get("content", "")[:100]
                            if user_msg and not user_msg.startswith("Tool result"):
                                down_snippets.append(f"Q: {user_msg} → Response disliked")
            except Exception:
                continue

        if not down_snippets and up_count == 0:
            return ""

        parts = []
        total = up_count + down_count
        if total >= 3:
            rate = round(up_count / total * 100)
            parts.append(f"**Feedback:** {rate}% satisfaction ({up_count}↑ {down_count}↓)")

        if down_snippets:
            parts.append("**Avoid repeating these patterns (user disliked):**")
            for s in down_snippets[-5:]:
                parts.append(f"- {s}")

        result = "\n".join(parts) if parts else ""
        CartridgeContext._feedback_cache[cartridge_id] = {"result": result, "ts": _time.time()}
        return result

    @staticmethod
    def clear(cartridge_id: str):
        path = CartridgeContext._path(cartridge_id)
        if path.exists():
            path.unlink()


# ═══════════════════════════════════════════
# GLOBAL USER PROFILE
# ═══════════════════════════════════════════

class GlobalProfile:
    """
    App-wide user understanding aggregated across all cartridges.
    Provides a high-level view of who the user is, what they do,
    and how they interact with the system.
    """

    @staticmethod
    def load() -> Dict[str, Any]:
        if GLOBAL_PROFILE_FILE.exists():
            try:
                return json.loads(GLOBAL_PROFILE_FILE.read_text())
            except Exception:
                pass
        return {
            "total_chats": 0,
            "total_messages": 0,
            "cartridges_used": {},
            "first_seen": None,
            "last_seen": None,
            "languages": [],
            "profile_notes": [],
        }

    @staticmethod
    def save(data: Dict[str, Any]):
        _atomic_write_json(GLOBAL_PROFILE_FILE, data)

    @staticmethod
    def update_from_chat(cartridge_id: str, messages: List[Dict]):
        """Update global profile after any chat session."""
        profile = GlobalProfile.load()
        now = datetime.now().isoformat()

        profile["total_chats"] = profile.get("total_chats", 0) + 1
        profile["total_messages"] = (
            profile.get("total_messages", 0) + len(messages)
        )

        if not profile.get("first_seen"):
            profile["first_seen"] = now
        profile["last_seen"] = now

        # Track cartridge usage
        carts = profile.get("cartridges_used", {})
        carts[cartridge_id] = carts.get(cartridge_id, 0) + 1
        profile["cartridges_used"] = carts

        # Detect language from user messages (simple Unicode-range heuristic)
        lang_ranges = {
            "Hindi": (0x0900, 0x097F),
            "Telugu": (0x0C00, 0x0C7F),
            "Tamil": (0x0B80, 0x0BFF),
            "Kannada": (0x0C80, 0x0CFF),
            "Malayalam": (0x0D00, 0x0D7F),
            "Bengali": (0x0980, 0x09FF),
            "Arabic": (0x0600, 0x06FF),
            "Chinese": (0x4E00, 0x9FFF),
            "Japanese": (0x3040, 0x30FF),
            "Korean": (0xAC00, 0xD7AF),
        }
        existing_langs = set(profile.get("languages", []))
        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if content.startswith("Tool result"):
                continue
            for lang, (lo, hi) in lang_ranges.items():
                if lang not in existing_langs:
                    # Require >= 5% of characters in the range to avoid false positives
                    lang_chars = sum(1 for c in content if lo <= ord(c) <= hi)
                    if len(content) > 0 and lang_chars / len(content) >= 0.05:
                        profile.setdefault("languages", []).append(lang)
                        existing_langs.add(lang)

        GlobalProfile.save(profile)
        logger.info(
            f"Global profile: {profile['total_chats']} chats, "
            f"{profile.get('total_messages', 0)} messages"
        )

    @staticmethod
    def add_note(note: str):
        """Add a high-level observation about the user."""
        profile = GlobalProfile.load()
        existing = set(profile.get("profile_notes", []))
        if note not in existing:
            profile.setdefault("profile_notes", []).append(note)
            if len(profile["profile_notes"]) > 20:
                profile["profile_notes"] = profile["profile_notes"][-20:]
            GlobalProfile.save(profile)

    @staticmethod
    def get_context_block() -> str:
        """Build a context block string to inject into system prompts."""
        profile = GlobalProfile.load()

        if profile.get("total_chats", 0) == 0:
            return ""

        parts = ["\n\n## Global User Profile"]

        parts.append(
            f"**Usage:** {profile['total_chats']} conversations, "
            f"{profile.get('total_messages', 0)} messages"
        )

        if profile.get("cartridges_used"):
            sorted_c = sorted(
                profile["cartridges_used"].items(),
                key=lambda x: x[1], reverse=True
            )
            top = [f"{c[0]} ({c[1]}x)" for c in sorted_c[:5]]
            parts.append(f"**Most used:** {', '.join(top)}")

        if profile.get("languages"):
            parts.append(
                f"**Languages used:** {', '.join(profile['languages'])}"
            )

        if profile.get("profile_notes"):
            parts.append("**About user:**")
            for note in profile["profile_notes"][-5:]:
                parts.append(f"- {note}")

        return "\n".join(parts)

    @staticmethod
    def clear():
        if GLOBAL_PROFILE_FILE.exists():
            GLOBAL_PROFILE_FILE.unlink()


# ═══════════════════════════════════════════
# MEMORY BLOCKS — Structured Context Units
# ═══════════════════════════════════════════
# Inspired by Letta/MemGPT: break the context window into discrete,
# labeled, size-limited blocks. Each block has a purpose, a budget,
# and a priority. Under pressure, low-priority blocks are trimmed first.

class MemoryBlock:
    """A discrete unit of agent context with a size budget.
    
    Attributes:
        label: Purpose identifier (e.g. 'task_state', 'working_notes')
        value: Current content string
        max_chars: Size limit in characters
        priority: Higher = more important, kept under budget pressure
        editable: Whether the agent can modify this block
    """
    __slots__ = ('label', 'value', 'max_chars', 'priority', 'editable', 'description')

    def __init__(self, label: str, max_chars: int = 500, priority: int = 5,
                 editable: bool = True, description: str = ""):
        self.label = label
        self.value = ""
        self.max_chars = max_chars
        self.priority = priority
        self.editable = editable
        self.description = description

    def update(self, new_value: str):
        """Replace block content, enforcing size limit."""
        if len(new_value) > self.max_chars:
            new_value = new_value[:self.max_chars - 3] + "..."
        self.value = new_value

    def append(self, text: str):
        """Append to block content, trimming oldest content if over limit."""
        combined = (self.value + "\n" + text.strip()) if self.value else text.strip()
        if len(combined) > self.max_chars:
            # Keep the most recent content that fits
            lines = combined.split('\n')
            kept = []
            total = 0
            for line in reversed(lines):
                if total + len(line) + 1 > self.max_chars:
                    break
                kept.insert(0, line)
                total += len(line) + 1
            combined = '\n'.join(kept)
        self.value = combined

    def is_empty(self) -> bool:
        return not self.value.strip()

    def char_count(self) -> int:
        return len(self.value)


class ContextAssembler:
    """Assembles memory blocks into a structured context string.
    
    Manages named blocks with priority-based budget allocation.
    When total content exceeds the budget, lower-priority blocks
    are trimmed first. This replaces flat concatenation of context
    layers with a principled, bounded approach.
    """

    # Default block definitions for agent conversations
    DEFAULT_BLOCKS = {
        "task_state": {
            "max_chars": 600, "priority": 10, "editable": True,
            "description": "Current goal, active subgoal, and progress status"
        },
        "working_notes": {
            "max_chars": 1200, "priority": 8, "editable": True,
            "description": "Key findings, decisions, and constraints discovered during work"
        },
        "user_context": {
            "max_chars": 500, "priority": 5, "editable": False,
            "description": "User preferences and relevant history"
        },
        "cartridge_context": {
            "max_chars": 400, "priority": 4, "editable": False,
            "description": "Persistent knowledge from previous sessions with this cartridge"
        },
        "global_profile": {
            "max_chars": 300, "priority": 2, "editable": False,
            "description": "App-wide user understanding"
        },
    }

    def __init__(self):
        self.blocks: Dict[str, MemoryBlock] = {}
        for label, cfg in self.DEFAULT_BLOCKS.items():
            self.blocks[label] = MemoryBlock(
                label=label,
                max_chars=cfg["max_chars"],
                priority=cfg["priority"],
                editable=cfg["editable"],
                description=cfg.get("description", ""),
            )

    def get_block(self, label: str) -> Optional[MemoryBlock]:
        return self.blocks.get(label)

    def update_block(self, label: str, value: str):
        """Update a block's content (only if editable)."""
        block = self.blocks.get(label)
        if block and block.editable:
            block.update(value)

    def append_to_block(self, label: str, text: str):
        """Append text to a block (only if editable)."""
        block = self.blocks.get(label)
        if block and block.editable:
            block.append(text)

    def load_readonly_blocks(self, user_memory_block: str = "",
                              cartridge_block: str = "",
                              global_block: str = ""):
        """Load read-only context from existing sources."""
        if user_memory_block:
            b = self.blocks.get("user_context")
            if b:
                b.value = user_memory_block[:b.max_chars]
        if cartridge_block:
            b = self.blocks.get("cartridge_context")
            if b:
                b.value = cartridge_block[:b.max_chars]
        if global_block:
            b = self.blocks.get("global_profile")
            if b:
                b.value = global_block[:b.max_chars]

    def assemble(self, total_budget_chars: int = 3000) -> str:
        """Assemble all non-empty blocks into a formatted context string.
        
        Blocks are included in priority order. If total exceeds budget,
        lowest-priority blocks are trimmed or dropped first.
        """
        active = [(b.priority, b) for b in self.blocks.values() if not b.is_empty()]
        if not active:
            return ""

        # Sort by priority descending (highest priority first)
        active.sort(key=lambda x: x[0], reverse=True)

        parts = []
        remaining = total_budget_chars
        for _, block in active:
            header = f"\n\n## {block.label.replace('_', ' ').title()}\n"
            text = header + block.value
            if len(text) <= remaining:
                parts.append(text)
                remaining -= len(text)
            elif remaining > 80:
                # Partial fit: truncate to remaining budget
                parts.append(text[:remaining - 3] + "...")
                remaining = 0
            # else: skip this block entirely

        return "".join(parts) if parts else ""

    def get_block_summary(self) -> str:
        """Return a compact summary of block states for debugging."""
        summaries = []
        for label, block in self.blocks.items():
            if not block.is_empty():
                summaries.append(f"{label}:{block.char_count()}/{block.max_chars}")
        return " | ".join(summaries) if summaries else "(empty)"


class ContextBudget:
    """Adaptive context budget allocation based on conversation state.
    
    Early rounds: heavy on history (the model needs full context).
    Late rounds: heavy on notes/knowledge (the model needs accumulated findings).
    """

    @staticmethod
    def allocate(tool_round: int, history_length: int,
                 total_chars: int = 12000) -> Dict[str, int]:
        """Return char budgets for each context category.
        
        Returns dict with keys: history, knowledge, notes, system
        """
        if tool_round <= 1:
            # Early: 65% history, 15% knowledge, 10% notes, 10% system
            return {
                "history": int(total_chars * 0.65),
                "knowledge": int(total_chars * 0.15),
                "notes": int(total_chars * 0.10),
                "system": int(total_chars * 0.10),
            }
        elif tool_round <= 4:
            # Mid: 50% history, 20% knowledge, 20% notes, 10% system
            return {
                "history": int(total_chars * 0.50),
                "knowledge": int(total_chars * 0.20),
                "notes": int(total_chars * 0.20),
                "system": int(total_chars * 0.10),
            }
        else:
            # Late: 30% history, 20% knowledge, 40% notes, 10% system
            return {
                "history": int(total_chars * 0.30),
                "knowledge": int(total_chars * 0.20),
                "notes": int(total_chars * 0.40),
                "system": int(total_chars * 0.10),
            }


# Singleton instances
user_settings = UserSettings()
