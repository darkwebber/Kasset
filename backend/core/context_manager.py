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

logger = logging.getLogger(__name__)

# Storage directories
DATA_DIR = Path.home() / ".kasset"
CONTEXT_DIR = DATA_DIR / "context"
CARTRIDGE_CONTEXT_DIR = CONTEXT_DIR / "cartridges"
GLOBAL_PROFILE_FILE = CONTEXT_DIR / "global_profile.json"
SETTINGS_FILE = DATA_DIR / "settings.json"


def _ensure_dirs():
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    CARTRIDGE_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)


_ensure_dirs()


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
        "rss_feeds": [],
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
        SETTINGS_FILE.write_text(json.dumps(self._settings, indent=2))

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
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    @staticmethod
    def update_from_chat(
        cartridge_id: str, messages: List[Dict], chat_title: str = ""
    ):
        """
        Update cartridge context after a chat session.
        Extracts topics and user intents from the conversation.
        """
        ctx = CartridgeContext.load(cartridge_id)
        now = datetime.now().isoformat()

        ctx["chat_count"] = ctx.get("chat_count", 0) + 1
        if not ctx.get("first_used"):
            ctx["first_used"] = now
        ctx["last_used"] = now

        existing_topics = {t["text"] for t in ctx.get("topics", [])}

        # Add chat title as a topic
        if chat_title and chat_title != "New conversation":
            if chat_title not in existing_topics:
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
                if topic not in existing_topics:
                    ctx.setdefault("topics", []).append(
                        {"text": topic, "date": now}
                    )
                    existing_topics.add(topic)

        # Trim to max entries
        if len(ctx.get("topics", [])) > CartridgeContext.MAX_TOPICS:
            ctx["topics"] = ctx["topics"][-CartridgeContext.MAX_TOPICS:]

        CartridgeContext.save(cartridge_id, ctx)
        logger.info(
            f"Cartridge context '{cartridge_id}': "
            f"{ctx['chat_count']} chats, {len(ctx.get('topics', []))} topics"
        )

    @staticmethod
    def add_learning(cartridge_id: str, learning: str):
        """Add a specific learning about the user for this cartridge."""
        ctx = CartridgeContext.load(cartridge_id)
        existing = {l for l in ctx.get("learnings", [])}
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

        return "\n".join(parts)

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
        GLOBAL_PROFILE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )

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
                    if any(lo <= ord(c) <= hi for c in content):
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


# Singleton instances
user_settings = UserSettings()
