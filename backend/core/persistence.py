"""Chat persistence and user memory system.
Stores conversations and learned user preferences to disk as JSON.
"""
import json
import logging
import time
import hashlib
import secrets
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from backend.core.shared import atomic_write_json as _atomic_write_json, CHATS_DIR, CACHE_DIR, USER_MEMORY_FILE as USER_FILE

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# CHAT PERSISTENCE
# ═══════════════════════════════════════════

class ChatStore:
    """Save/load/list conversations on disk."""

    @staticmethod
    def _chat_path(chat_id: str) -> Path:
        return CHATS_DIR / f"{chat_id}.json"

    @staticmethod
    def _graph_path(chat_id: str) -> Path:
        return CHATS_DIR / f"{chat_id}.graph.json"

    @staticmethod
    def save_graph(chat_id: str, graph_data: dict) -> None:
        """Persist a conversation's knowledge graph."""
        try:
            _atomic_write_json(ChatStore._graph_path(chat_id), graph_data, indent=0)
        except Exception as e:
            logger.warning(f"Failed to save graph for {chat_id}: {e}")

    @staticmethod
    def load_graph(chat_id: str) -> Optional[dict]:
        """Load a conversation's knowledge graph."""
        path = ChatStore._graph_path(chat_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception:
            return None

    @staticmethod
    def generate_id() -> str:
        return secrets.token_hex(6)

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
        _atomic_write_json(path, data)
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
        """List all saved conversations (metadata only, no messages).
        Reads only enough bytes to extract metadata fields without parsing full message content."""
        chats = []
        for f in sorted(CHATS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                # For very large files (>1MB), read only the first portion to extract metadata
                file_size = f.stat().st_size
                if file_size > 1_000_000:
                    # Metadata fields are always at the top of the JSON; read first 2KB
                    raw = f.read_text(encoding="utf-8")[:2048]
                    # Parse partial JSON to extract metadata
                    meta = {}
                    for key in ["id", "title", "summary", "message_count", "created_at", "updated_at"]:
                        import re as _re
                        m = _re.search(rf'"{key}"\s*:\s*"([^"]*?)"', raw)
                        if m:
                            meta[key] = m.group(1)
                        else:
                            m = _re.search(rf'"{key}"\s*:\s*(\d+)', raw)
                            if m:
                                meta[key] = int(m.group(1))
                    # Extract cartridge_ids array
                    cid_match = _re.search(r'"cartridge_ids"\s*:\s*\[([^\]]*)\]', raw)
                    if cid_match:
                        meta["cartridge_ids"] = [s.strip().strip('"') for s in cid_match.group(1).split(',') if s.strip()]
                    else:
                        meta["cartridge_ids"] = []
                    chats.append({
                        "id": meta.get("id", f.stem),
                        "title": meta.get("title", "Untitled"),
                        "summary": meta.get("summary", ""),
                        "cartridge_ids": meta.get("cartridge_ids", []),
                        "message_count": meta.get("message_count", 0),
                        "created_at": meta.get("created_at", ""),
                        "updated_at": meta.get("updated_at", ""),
                    })
                else:
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
    def search(query: str, max_results: int = 20) -> List[Dict]:
        """Search across all saved conversations by message content and title."""
        if not query or not query.strip():
            return []
        q = query.lower().strip()
        results = []
        for f in sorted(CHATS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(f.read_text())
                title = data.get("title", "")
                messages = data.get("messages", [])

                # Search title and message content
                matched_excerpt = ""
                if q in title.lower():
                    matched_excerpt = title
                else:
                    for msg in messages:
                        content = msg.get("content", "")
                        if q in content.lower():
                            # Extract snippet around match
                            idx = content.lower().index(q)
                            start = max(0, idx - 40)
                            end = min(len(content), idx + len(q) + 60)
                            snippet = content[start:end].replace("\n", " ").strip()
                            if start > 0:
                                snippet = "…" + snippet
                            if end < len(content):
                                snippet = snippet + "…"
                            matched_excerpt = snippet
                            break

                if matched_excerpt:
                    results.append({
                        "id": data["id"],
                        "title": data.get("title", "Untitled"),
                        "excerpt": matched_excerpt,
                        "cartridge_ids": data.get("cartridge_ids", []),
                        "message_count": data.get("message_count", 0),
                        "updated_at": data.get("updated_at", ""),
                    })
                    if len(results) >= max_results:
                        break
            except Exception:
                continue
        return results

    @staticmethod
    def delete(chat_id: str) -> bool:
        path = ChatStore._chat_path(chat_id)
        if path.exists():
            path.unlink()
            # Also clean up the knowledge graph file
            graph_path = ChatStore._graph_path(chat_id)
            if graph_path.exists():
                try:
                    graph_path.unlink()
                except Exception:
                    pass
            return True
        return False

    @staticmethod
    def save_feedback(chat_id: str, message_index: int, rating: str, comment: str = "") -> bool:
        """Save thumbs up/down feedback for a specific message. rating: 'up' | 'down'."""
        path = ChatStore._chat_path(chat_id)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text())
            if "feedback" not in data:
                data["feedback"] = {}
            data["feedback"][str(message_index)] = {
                "rating": rating,
                "comment": comment,
                "timestamp": datetime.now().isoformat(),
            }
            _atomic_write_json(path, data)
            return True
        except Exception as e:
            logger.error(f"Failed to save feedback for {chat_id}[{message_index}]: {e}")
            return False

    @staticmethod
    def get_feedback_stats() -> dict:
        """Aggregate feedback statistics across all chats for self-learning insights."""
        total_up = 0
        total_down = 0
        down_contexts: list = []
        for f in CHATS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                feedback = data.get("feedback", {})
                messages = data.get("messages", [])
                for idx_str, fb in feedback.items():
                    if fb.get("rating") == "up":
                        total_up += 1
                    elif fb.get("rating") == "down":
                        total_down += 1
                        idx = int(idx_str)
                        if idx > 0 and idx < len(messages):
                            down_contexts.append({
                                "chat_id": data.get("id"),
                                "message": messages[idx].get("content", "")[:200],
                                "timestamp": fb.get("timestamp"),
                            })
            except Exception:
                continue
        return {
            "total_up": total_up,
            "total_down": total_down,
            "total": total_up + total_down,
            "satisfaction_rate": round(total_up / (total_up + total_down) * 100, 1) if (total_up + total_down) > 0 else None,
            "recent_down_contexts": down_contexts[-10:],
        }

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
        _atomic_write_json(USER_FILE, self._memories)

    # Relevance decay constants
    ARCHIVE_AFTER_DAYS = 90
    MAX_CONTEXT_TOKENS = 2000  # Token budget for injected memories
    CHARS_PER_TOKEN = 3.5

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
                existing["last_accessed"] = datetime.now().isoformat()
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
            "last_accessed": datetime.now().isoformat(),
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

    def _relevance_score(self, memory: Dict) -> float:
        """Compute a relevance score for a memory based on recency and usage.
        Higher = more relevant. Score decays over time."""
        now = time.time()
        last_accessed_str = memory.get("last_accessed", memory.get("updated_at", memory.get("created_at", "")))
        try:
            last_dt = datetime.fromisoformat(last_accessed_str)
            days_since = (now - last_dt.timestamp()) / 86400
        except (ValueError, TypeError):
            days_since = 30  # fallback

        hits = memory.get("hits", 1)

        # Decay: halve relevance every 30 days; boost by log(hits)
        import math
        recency_factor = 0.5 ** (days_since / 30)
        usage_factor = 1.0 + math.log(max(1, hits))

        # Instructions get a priority boost
        type_bonus = 2.0 if memory.get("type") == "instruction" else 1.0

        return recency_factor * usage_factor * type_bonus

    def auto_archive_stale(self) -> int:
        """Archive memories not accessed in ARCHIVE_AFTER_DAYS. Returns count archived."""
        now = time.time()
        count = 0
        for m in self._memories:
            if not m.get("active", True):
                continue
            last_str = m.get("last_accessed", m.get("updated_at", m.get("created_at", "")))
            try:
                last_dt = datetime.fromisoformat(last_str)
                days = (now - last_dt.timestamp()) / 86400
            except (ValueError, TypeError):
                days = self.ARCHIVE_AFTER_DAYS + 1
            if days > self.ARCHIVE_AFTER_DAYS:
                m["active"] = False
                count += 1
        if count:
            self._save()
            logger.info(f"Auto-archived {count} stale memories")
        return count

    def touch(self, memory_id: str):
        """Update last_accessed timestamp for a memory (called when it's injected into context)."""
        for m in self._memories:
            if m["id"] == memory_id:
                m["last_accessed"] = datetime.now().isoformat()
                # Don't save on every touch — batch save later
                break

    def get_context_block(self) -> str:
        """Build a context block string to inject into system prompts.
        Uses relevance scoring to select top-N memories within token budget."""
        # Auto-archive stale memories first
        self.auto_archive_stale()

        active = self.get_all(active_only=True)
        if not active:
            return ""

        # Score and rank
        scored = [(m, self._relevance_score(m)) for m in active]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Select within token budget
        selected = []
        token_count = 0
        header_tokens = 20  # reserve for section headers
        for m, score in scored:
            est_tokens = max(1, int(len(m["content"]) / self.CHARS_PER_TOKEN))
            if token_count + est_tokens + header_tokens > self.MAX_CONTEXT_TOKENS:
                break
            selected.append(m)
            token_count += est_tokens
            # Touch to update last_accessed
            self.touch(m["id"])

        if not selected:
            return ""

        # Batch save after touching
        self._save()

        sections = {
            "instruction": [],
            "preference": [],
            "fact": [],
            "context": [],
        }
        for m in selected:
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
        _atomic_write_json(self._cache_file, self._summary_cache, indent=0)

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
