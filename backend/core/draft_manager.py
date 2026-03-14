"""
draft_manager.py — File-backed draft collaboration system.

Each draft lives at ~/.kasset/drafts/<draft_id>/ with:
  - versions/v1.txt, v2.txt, ...  (immutable snapshots)
  - meta.json                      (comments, metadata, finalization state)
  - final -> ~/Desktop/...         (symlink created on finalize)

The agent writes new versions via API; the user edits inline and saves versions.
Both can add comments anchored to text offsets. Diffs are computed on demand.
"""

import difflib
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .shared import KASSET_DIR, atomic_write_json

logger = logging.getLogger(__name__)

DRAFTS_DIR = KASSET_DIR / "drafts"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

FINALIZED_DIR = KASSET_DIR / "finalized"
FINALIZED_DIR.mkdir(parents=True, exist_ok=True)


def _safe_id(draft_id: str) -> str:
    """Sanitize draft_id to prevent path traversal. Raises ValueError if invalid."""
    if not draft_id or not isinstance(draft_id, str):
        raise ValueError("Invalid draft ID")
    # Only allow hex characters (token_hex output)
    cleaned = draft_id.strip()
    if not cleaned or '/' in cleaned or '\\' in cleaned or '..' in cleaned:
        raise ValueError("Invalid draft ID")
    if not all(c in '0123456789abcdef' for c in cleaned):
        raise ValueError("Invalid draft ID")
    return cleaned


class DraftManager:
    """Manages file-backed drafts with versioning, comments, and finalization."""

    # ── Creation ──────────────────────────────────────────────

    def create(self, content: str, title: str = "Untitled Draft",
               author: str = "ai", language: str = "text") -> Dict[str, Any]:
        """Create a new draft. Returns the full draft state."""
        draft_id = secrets.token_hex(8)
        draft_dir = DRAFTS_DIR / draft_id
        versions_dir = draft_dir / "versions"
        versions_dir.mkdir(parents=True, exist_ok=True)

        # Write first version
        v1_path = versions_dir / "v1.txt"
        v1_path.write_text(content, encoding="utf-8")

        meta = {
            "id": draft_id,
            "title": title,
            "language": language,
            "created_at": time.time(),
            "updated_at": time.time(),
            "version_count": 1,
            "current_version": 1,
            "finalized": False,
            "finalized_path": None,
            "versions": [
                {
                    "number": 1,
                    "author": author,
                    "timestamp": time.time(),
                    "char_count": len(content),
                    "word_count": len(content.split()),
                }
            ],
            "comments": [],
        }
        atomic_write_json(draft_dir / "meta.json", meta)
        logger.info(f"Created draft {draft_id}: {title}")
        return self._build_response(draft_id, meta, content)

    # ── Read ──────────────────────────────────────────────────

    def get(self, draft_id: str, version: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get draft state. Returns None if not found."""
        draft_id = _safe_id(draft_id)
        draft_dir = DRAFTS_DIR / draft_id
        meta_path = draft_dir / "meta.json"
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        v = version or meta["current_version"]
        content = self._read_version(draft_id, v)
        if content is None:
            return None
        return self._build_response(draft_id, meta, content, v)

    def list_all(self) -> List[Dict[str, Any]]:
        """List all drafts (metadata only, no content)."""
        drafts = []
        if not DRAFTS_DIR.exists():
            return drafts
        for d in sorted(DRAFTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            meta_path = d / "meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    drafts.append({
                        "id": meta["id"],
                        "title": meta["title"],
                        "language": meta.get("language", "text"),
                        "version_count": meta["version_count"],
                        "finalized": meta["finalized"],
                        "updated_at": meta["updated_at"],
                        "comment_count": len(meta.get("comments", [])),
                    })
                except Exception as e:
                    logger.debug(f"Skipping draft {d.name}: {e}")
        return drafts

    # ── Update (new version) ──────────────────────────────────

    def add_version(self, draft_id: str, content: str,
                    author: str = "user") -> Optional[Dict[str, Any]]:
        """Add a new version to an existing draft."""
        draft_id = _safe_id(draft_id)
        draft_dir = DRAFTS_DIR / draft_id
        meta_path = draft_dir / "meta.json"
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("finalized"):
            return None  # Can't modify finalized drafts

        new_num = meta["version_count"] + 1
        v_path = draft_dir / "versions" / f"v{new_num}.txt"
        v_path.write_text(content, encoding="utf-8")

        meta["version_count"] = new_num
        meta["current_version"] = new_num
        meta["updated_at"] = time.time()
        meta["versions"].append({
            "number": new_num,
            "author": author,
            "timestamp": time.time(),
            "char_count": len(content),
            "word_count": len(content.split()),
        })
        atomic_write_json(meta_path, meta)
        return self._build_response(draft_id, meta, content)

    # ── Comments ──────────────────────────────────────────────

    def add_comment(self, draft_id: str, selection: str,
                    start_offset: int, end_offset: int,
                    text: str, author: str = "user",
                    version: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Add a comment anchored to a text region."""
        draft_id = _safe_id(draft_id)
        draft_dir = DRAFTS_DIR / draft_id
        meta_path = draft_dir / "meta.json"
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("finalized"):
            return None  # Can't comment on finalized drafts

        comment = {
            "id": secrets.token_hex(4),
            "selection": selection,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "text": text,
            "author": author,
            "version": version or meta["current_version"],
            "timestamp": time.time(),
            "resolved": False,
        }
        meta["comments"].append(comment)
        meta["updated_at"] = time.time()
        atomic_write_json(meta_path, meta)

        content = self._read_version(draft_id, meta["current_version"]) or ""
        return self._build_response(draft_id, meta, content)

    def resolve_comment(self, draft_id: str, comment_id: str) -> Optional[Dict[str, Any]]:
        """Mark a comment as resolved."""
        draft_id = _safe_id(draft_id)
        draft_dir = DRAFTS_DIR / draft_id
        meta_path = draft_dir / "meta.json"
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        for c in meta["comments"]:
            if c["id"] == comment_id:
                c["resolved"] = True
                break
        meta["updated_at"] = time.time()
        atomic_write_json(meta_path, meta)
        content = self._read_version(draft_id, meta["current_version"]) or ""
        return self._build_response(draft_id, meta, content)

    def delete_comment(self, draft_id: str, comment_id: str) -> Optional[Dict[str, Any]]:
        """Delete a comment."""
        draft_id = _safe_id(draft_id)
        draft_dir = DRAFTS_DIR / draft_id
        meta_path = draft_dir / "meta.json"
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["comments"] = [c for c in meta["comments"] if c["id"] != comment_id]
        meta["updated_at"] = time.time()
        atomic_write_json(meta_path, meta)
        content = self._read_version(draft_id, meta["current_version"]) or ""
        return self._build_response(draft_id, meta, content)

    # ── Diff ──────────────────────────────────────────────────

    def diff(self, draft_id: str, v1: int, v2: int) -> Optional[Dict[str, Any]]:
        """Compute a structured diff between two versions."""
        draft_id = _safe_id(draft_id)
        content_a = self._read_version(draft_id, v1)
        content_b = self._read_version(draft_id, v2)
        if content_a is None or content_b is None:
            return None

        lines_a = content_a.splitlines(keepends=True)
        lines_b = content_b.splitlines(keepends=True)

        # Unified diff for display
        unified = list(difflib.unified_diff(
            lines_a, lines_b,
            fromfile=f"v{v1}", tofile=f"v{v2}",
            lineterm=""
        ))

        # Structured inline diff (word-level changes for richer UI)
        sm = difflib.SequenceMatcher(None, content_a, content_b)
        ops = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                ops.append({"op": "equal", "text": content_a[i1:i2]})
            elif tag == "replace":
                ops.append({"op": "delete", "text": content_a[i1:i2]})
                ops.append({"op": "insert", "text": content_b[j1:j2]})
            elif tag == "delete":
                ops.append({"op": "delete", "text": content_a[i1:i2]})
            elif tag == "insert":
                ops.append({"op": "insert", "text": content_b[j1:j2]})

        return {
            "draft_id": draft_id,
            "from_version": v1,
            "to_version": v2,
            "unified": "\n".join(unified),
            "ops": ops,
            "stats": {
                "additions": sum(1 for o in ops if o["op"] == "insert"),
                "deletions": sum(1 for o in ops if o["op"] == "delete"),
                "chars_added": sum(len(o["text"]) for o in ops if o["op"] == "insert"),
                "chars_removed": sum(len(o["text"]) for o in ops if o["op"] == "delete"),
            }
        }

    # ── Navigate versions ─────────────────────────────────────

    def set_current_version(self, draft_id: str, version: int) -> Optional[Dict[str, Any]]:
        """Switch the draft's current (active) version."""
        draft_id = _safe_id(draft_id)
        draft_dir = DRAFTS_DIR / draft_id
        meta_path = draft_dir / "meta.json"
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if version < 1 or version > meta["version_count"]:
            return None
        meta["current_version"] = version
        atomic_write_json(meta_path, meta)
        content = self._read_version(draft_id, version) or ""
        return self._build_response(draft_id, meta, content)

    # ── Finalize ──────────────────────────────────────────────

    def finalize(self, draft_id: str, filename: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Finalize a draft: copy current version to ~/Desktop and create a symlink."""
        draft_id = _safe_id(draft_id)
        draft_dir = DRAFTS_DIR / draft_id
        meta_path = draft_dir / "meta.json"
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

        content = self._read_version(draft_id, meta["current_version"])
        if content is None:
            return None

        # Determine output filename
        safe_title = "".join(c for c in meta["title"] if c.isalnum() or c in " -_").strip()
        if not safe_title:
            safe_title = f"draft-{draft_id}"
        ext = ".md" if meta.get("language") in ("markdown", "md") else ".txt"
        fname = filename or f"{safe_title}{ext}"

        # Write to finalized directory
        final_path = FINALIZED_DIR / fname
        counter = 1
        while final_path.exists():
            stem = final_path.stem
            final_path = FINALIZED_DIR / f"{stem}-{counter}{ext}"
            counter += 1
        final_path.write_text(content, encoding="utf-8")

        # Also copy to ~/Desktop if it exists
        desktop = Path.home() / "Desktop"
        desktop_path = None
        if desktop.exists():
            desktop_file = desktop / fname
            counter = 1
            while desktop_file.exists():
                stem = Path(fname).stem
                desktop_file = desktop / f"{stem}-{counter}{ext}"
                counter += 1
            desktop_file.write_text(content, encoding="utf-8")
            desktop_path = str(desktop_file)

        meta["finalized"] = True
        meta["finalized_path"] = desktop_path or str(final_path)
        meta["updated_at"] = time.time()
        atomic_write_json(meta_path, meta)

        logger.info(f"Finalized draft {draft_id} -> {meta['finalized_path']}")
        return self._build_response(draft_id, meta, content)

    # ── Delete ────────────────────────────────────────────────

    def delete(self, draft_id: str) -> bool:
        """Delete a draft and all its versions."""
        import shutil
        draft_id = _safe_id(draft_id)
        draft_dir = DRAFTS_DIR / draft_id
        if not draft_dir.exists():
            return False
        shutil.rmtree(draft_dir)
        return True

    # ── Internals ─────────────────────────────────────────────

    def _read_version(self, draft_id: str, version: int) -> Optional[str]:
        v_path = DRAFTS_DIR / draft_id / "versions" / f"v{version}.txt"
        if not v_path.exists():
            return None
        return v_path.read_text(encoding="utf-8")

    def _build_response(self, draft_id: str, meta: dict, content: str,
                        viewing_version: Optional[int] = None) -> Dict[str, Any]:
        v = viewing_version or meta["current_version"]
        return {
            "id": draft_id,
            "title": meta["title"],
            "language": meta.get("language", "text"),
            "content": content,
            "current_version": meta["current_version"],
            "viewing_version": v,
            "version_count": meta["version_count"],
            "versions": meta["versions"],
            "comments": [c for c in meta.get("comments", []) if not c.get("resolved")],
            "all_comments": meta.get("comments", []),
            "finalized": meta.get("finalized", False),
            "finalized_path": meta.get("finalized_path"),
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
            "char_count": len(content),
            "word_count": len(content.split()),
        }


# Singleton
draft_manager = DraftManager()
