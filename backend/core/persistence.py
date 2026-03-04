"""
Chat persistence and user memory system.
Stores conversations and learned user preferences to disk as JSON.
"""
import json
import logging
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Storage directories
DATA_DIR = Path.home() / ".qwen-studio"
CHATS_DIR = DATA_DIR / "chats"
USER_FILE = DATA_DIR / "user_memory.json"
CACHE_DIR = DATA_DIR / "cache"


def _ensure_dirs():
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


_ensure_dirs()


# ═══════════════════════════════════════════
# CHAT PERSISTENCE
# ═══════════════════════════════════════════

class ChatStore:
    """Save/load/list conversations on disk."""

    @staticmethod
    def _chat_path(chat_id: str) -> Path:
        return CHATS_DIR / f"{chat_id}.json"

    @staticmethod
    def generate_id() -> str:
        return hashlib.sha256(f"{time.time()}".encode()).hexdigest()[:12]

    @staticmethod
    def save(chat_id: str, messages: List[Dict], cartridge_ids: List[str],
             title: str = "", summary: str = "") -> Dict:
        """Save a conversation to disk. Returns metadata."""
        path = ChatStore._chat_path(chat_id)
        now = datetime.now().isoformat()

        # Load existing to preserve created_at
        existing = None
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except Exception:
                pass

        data = {
            "id": chat_id,
            "title": title or ChatStore._auto_title(messages),
            "summary": summary,
            "cartridge_ids": cartridge_ids,
            "messages": messages,
            "message_count": len(messages),
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        logger.info(f"Chat saved: {chat_id} ({len(messages)} messages)")
        return {k: v for k, v in data.items() if k != "messages"}

    @staticmethod
    def load(chat_id: str) -> Optional[Dict]:
        """Load a conversation from disk."""
        path = ChatStore._chat_path(chat_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception as e:
            logger.error(f"Failed to load chat {chat_id}: {e}")
            return None

    @staticmethod
    def list_all() -> List[Dict]:
        """List all saved conversations (metadata only, no messages)."""
        chats = []
        for f in sorted(CHATS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(f.read_text())
                chats.append({
                    "id": data["id"],
                    "title": data.get("title", "Untitled"),
                    "summary": data.get("summary", ""),
                    "cartridge_ids": data.get("cartridge_ids", []),
                    "message_count": data.get("message_count", 0),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                })
            except Exception:
                continue
        return chats

    @staticmethod
    def delete(chat_id: str) -> bool:
        path = ChatStore._chat_path(chat_id)
        if path.exists():
            path.unlink()
            return True
        return False

    @staticmethod
    def _auto_title(messages: List[Dict]) -> str:
        """Generate a title from the first user message."""
        for msg in messages:
            if msg.get("role") == "user":
                text = msg["content"].strip()
                # Remove file attachments from title
                if text.startswith("[Attached file:"):
                    continue
                return text[:60] + ("..." if len(text) > 60 else "")
        return "New conversation"


# ═══════════════════════════════════════════
# USER MEMORY SYSTEM
# ═══════════════════════════════════════════

class UserMemory:
    """
    Persistent user profile that learns from conversations.
    Stores preferences, facts, and patterns so the model can personalize responses.

    Memory types:
    - preference: User likes/dislikes (e.g. "prefers Python over JS")
    - fact: Concrete facts (e.g. "uses macOS", "works with pandas often")
    - instruction: Standing instructions (e.g. "always explain step by step")
    - context: Ongoing context (e.g. "working on a data pipeline project")
    """

    MEMORY_TYPES = {"preference", "fact", "instruction", "context"}

    def __init__(self):
        self._memories: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if USER_FILE.exists():
            try:
                self._memories = json.loads(USER_FILE.read_text())
                logger.info(f"Loaded {len(self._memories)} user memories")
            except Exception as e:
                logger.error(f"Failed to load user memory: {e}")
                self._memories = []

    def _save(self):
        USER_FILE.write_text(json.dumps(self._memories, ensure_ascii=False, indent=2))

    def add(self, content: str, memory_type: str = "fact", source: str = "auto") -> Dict:
        """Add a memory. Deduplicates by checking for similar existing entries."""
        if memory_type not in self.MEMORY_TYPES:
            memory_type = "fact"

        # Check for duplicates (exact or very similar)
        content_lower = content.lower().strip()
        for existing in self._memories:
            if existing["content"].lower().strip() == content_lower:
                # Update timestamp instead of duplicating
                existing["updated_at"] = datetime.now().isoformat()
                existing["hits"] = existing.get("hits", 1) + 1
                self._save()
                return existing

        memory = {
            "id": hashlib.sha256(f"{content}{time.time()}".encode()).hexdigest()[:10],
            "content": content.strip(),
            "type": memory_type,
            "source": source,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "hits": 1,
            "active": True,
        }
        self._memories.append(memory)
        self._save()
        logger.info(f"New user memory [{memory_type}]: {content[:50]}...")
        return memory

    def remove(self, memory_id: str) -> bool:
        before = len(self._memories)
        self._memories = [m for m in self._memories if m["id"] != memory_id]
        if len(self._memories) < before:
            self._save()
            return True
        return False

    def update(self, memory_id: str, content: str) -> Optional[Dict]:
        for m in self._memories:
            if m["id"] == memory_id:
                m["content"] = content.strip()
                m["updated_at"] = datetime.now().isoformat()
                self._save()
                return m
        return None

    def get_all(self, active_only: bool = True) -> List[Dict]:
        if active_only:
            return [m for m in self._memories if m.get("active", True)]
        return list(self._memories)

    def get_context_block(self) -> str:
        """Build a context block string to inject into system prompts."""
        active = self.get_all(active_only=True)
        if not active:
            return ""

        sections = {
            "instruction": [],
            "preference": [],
            "fact": [],
            "context": [],
        }
        for m in active:
            sections.get(m["type"], sections["fact"]).append(m["content"])

        lines = ["\n\n## User Profile (learned from previous interactions)"]
        if sections["instruction"]:
            lines.append("**Standing instructions:**")
            lines.extend(f"- {s}" for s in sections["instruction"])
        if sections["preference"]:
            lines.append("**Preferences:**")
            lines.extend(f"- {s}" for s in sections["preference"])
        if sections["fact"]:
            lines.append("**Known facts:**")
            lines.extend(f"- {s}" for s in sections["fact"])
        if sections["context"]:
            lines.append("**Current context:**")
            lines.extend(f"- {s}" for s in sections["context"])

        return "\n".join(lines)

    def extract_memories_from_conversation(self, messages: List[Dict]) -> List[str]:
        """
        Analyze a conversation to extract potential memories.
        Returns a list of memory extraction prompts that the model should evaluate.
        This is called after each conversation to learn from it.
        """
        # Collect user messages for analysis
        user_texts = []
        for msg in messages:
            if msg.get("role") == "user":
                text = msg["content"].strip()
                if not text.startswith("[Attached file:") and len(text) > 10:
                    user_texts.append(text)

        if not user_texts:
            return []

        # Heuristic extraction rules (no model call needed)
        extracted = []
        for text in user_texts:
            tl = text.lower()

            # Detect explicit preferences
            pref_signals = [
                "i prefer", "i like", "i always", "i never", "i usually",
                "i want you to", "please always", "don't ever", "i hate",
                "my favorite", "i work with", "i use ",
            ]
            for signal in pref_signals:
                if signal in tl:
                    # Extract the relevant sentence
                    for sentence in text.replace(". ", ".\n").split("\n"):
                        if signal in sentence.lower():
                            clean = sentence.strip().rstrip(".")
                            if 10 < len(clean) < 200:
                                extracted.append(("preference", clean))
                    break

            # Detect facts about the user
            fact_signals = [
                "i'm a ", "i am a ", "my name is", "i work at", "i work on",
                "my project", "i'm using", "i am using", "i'm building",
                "my os is", "i run ", "my machine",
            ]
            for signal in fact_signals:
                if signal in tl:
                    for sentence in text.replace(". ", ".\n").split("\n"):
                        if signal in sentence.lower():
                            clean = sentence.strip().rstrip(".")
                            if 10 < len(clean) < 200:
                                extracted.append(("fact", clean))
                    break

            # Detect standing instructions
            instruction_signals = [
                "from now on", "going forward", "remember to",
                "always remember", "keep in mind", "note that i",
            ]
            for signal in instruction_signals:
                if signal in tl:
                    for sentence in text.replace(". ", ".\n").split("\n"):
                        if signal in sentence.lower():
                            clean = sentence.strip().rstrip(".")
                            if 10 < len(clean) < 200:
                                extracted.append(("instruction", clean))
                    break

        return extracted


# ═══════════════════════════════════════════
# PROMPT CACHE
# ═══════════════════════════════════════════

class PromptCache:
    """
    Cache for system prompt hashes to avoid rebuilding identical prompts.
    Also caches conversation summaries for context compression.
    """

    def __init__(self, max_summaries: int = 50):
        self._summary_cache: Dict[str, str] = {}
        self._max_summaries = max_summaries
        self._cache_file = CACHE_DIR / "summaries.json"
        self._load()

    def _load(self):
        if self._cache_file.exists():
            try:
                self._summary_cache = json.loads(self._cache_file.read_text())
            except Exception:
                self._summary_cache = {}

    def _save(self):
        # Evict oldest if over limit
        if len(self._summary_cache) > self._max_summaries:
            keys = list(self._summary_cache.keys())
            for k in keys[:len(keys) - self._max_summaries]:
                del self._summary_cache[k]
        self._cache_file.write_text(json.dumps(self._summary_cache))

    @staticmethod
    def _hash_messages(messages: List[Dict]) -> str:
        raw = json.dumps(messages, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get_summary(self, messages: List[Dict]) -> Optional[str]:
        key = self._hash_messages(messages)
        return self._summary_cache.get(key)

    def store_summary(self, messages: List[Dict], summary: str):
        key = self._hash_messages(messages)
        self._summary_cache[key] = summary
        self._save()


# Singleton instances
chat_store = ChatStore()
user_memory = UserMemory()
prompt_cache = PromptCache()
