"""
shared.py — Shared utilities for Kasset backend.

Centralizes common functions used across persistence, context_manager, and other modules.
"""

import fcntl
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Data directories ──────────────────────────────────────
KASSET_DIR = Path.home() / ".kasset"
CHATS_DIR = KASSET_DIR / "chats"
CONTEXT_DIR = KASSET_DIR / "context"
CACHE_DIR = KASSET_DIR / "cache"
UPLOADS_DIR = KASSET_DIR / "uploads"
WORKSPACE_DIR = KASSET_DIR / "workspace"
USER_TOOLS_DIR = KASSET_DIR / "tools"
USER_CARTRIDGES_DIR = KASSET_DIR / "cartridges"
INPUT_TYPES_DIR = KASSET_DIR / "input_types"
SETTINGS_FILE = KASSET_DIR / "settings.json"
USER_MEMORY_FILE = KASSET_DIR / "user_memory.json"
GLOBAL_PROFILE_FILE = CONTEXT_DIR / "global_profile.json"

# Ensure core dirs exist
for _d in [KASSET_DIR, CHATS_DIR, CONTEXT_DIR, CACHE_DIR, UPLOADS_DIR,
           WORKSPACE_DIR, USER_TOOLS_DIR, USER_CARTRIDGES_DIR, INPUT_TYPES_DIR,
           CONTEXT_DIR / "cartridges"]:
    _d.mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: Path, data: Any, indent: int = 2):
    """Write JSON to a file atomically using write-to-temp + rename.
    Uses fcntl advisory locking to prevent concurrent write corruption.
    Falls back to direct write if locking is unavailable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    try:
        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                fd, tmp_path = tempfile.mkstemp(
                    dir=str(path.parent), suffix=".tmp", prefix=".write_"
                )
                try:
                    with os.fdopen(fd, "w") as f:
                        json.dump(data, f, ensure_ascii=False, indent=indent)
                    os.replace(tmp_path, str(path))
                except Exception:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
    except Exception:
        # Fallback: direct write if locking fails
        path.write_text(json.dumps(data, ensure_ascii=False, indent=indent))


# ─── Path security ──────────────────────────────────────

ALLOWED_FS_ROOTS = [
    Path.home(),
    Path("/tmp"),
    Path("/var/tmp"),
    Path(tempfile.gettempdir()).resolve(),
]

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
MAX_IMAGE_SIZE_MB = 10


def check_path_allowed(path: str, extra_roots: list = None) -> bool:
    """Check if a resolved path is within allowed filesystem roots."""
    try:
        resolved = Path(path).resolve()
        roots = ALLOWED_FS_ROOTS + (extra_roots or [])
        return any(resolved == r or resolved.is_relative_to(r) for r in roots)
    except Exception:
        return False


def validate_image_path(image_path: str) -> tuple:
    """Validate image file for security and compatibility.
    Returns (is_valid: bool, message: str)."""
    try:
        if not image_path or not image_path.strip():
            return False, "Empty image path"

        path_obj = Path(image_path)

        if path_obj.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
            return False, f"Unsupported image format: {path_obj.suffix}"

        if not path_obj.exists():
            return False, "Image file does not exist"

        file_size_mb = path_obj.stat().st_size / (1024 * 1024)
        if file_size_mb > MAX_IMAGE_SIZE_MB:
            return False, f"Image too large: {file_size_mb:.1f}MB (max: {MAX_IMAGE_SIZE_MB}MB)"

        if not check_path_allowed(str(path_obj)):
            return False, f"Access denied — image path not in allowed directories"

        return True, "Valid image file"
    except Exception as e:
        logger.error(f"Image validation error: {e}")
        return False, f"Validation error: {str(e)}"
