"""
utils.py — Shared utilities for Qwen 3.5 9B Local Studio
"""

import os
import logging
import tempfile
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
MAX_IMAGE_SIZE_MB = 10


def validate_image_file(image_path: str) -> Tuple[bool, str]:
    """Validate image file for security and compatibility."""
    try:
        if not image_path or not image_path.strip():
            return False, "Empty image path"

        path_obj = Path(image_path)

        # Check file extension
        if path_obj.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
            return False, f"Unsupported image format: {path_obj.suffix}"

        # Check file exists
        if not path_obj.exists():
            return False, "Image file does not exist"

        # Check file size
        file_size_mb = path_obj.stat().st_size / (1024 * 1024)
        if file_size_mb > MAX_IMAGE_SIZE_MB:
            return False, f"Image too large: {file_size_mb:.1f}MB (max: {MAX_IMAGE_SIZE_MB}MB)"

        # Security check: prevent path traversal but allow reasonable paths
        resolved = path_obj.resolve()
        allowed_roots = [
            Path(os.getcwd()),
            Path.home() / "Desktop",
            Path.home() / "Documents",
            Path.home() / "Downloads",
            Path.home() / "Pictures",
            Path(tempfile.gettempdir()).resolve(),  # Gradio uploads (macOS: /private/var/folders/...)
            Path("/tmp"),
            Path("/var/tmp"),
        ]

        if not any(resolved == root or resolved.is_relative_to(root) for root in allowed_roots):
            return False, f"Access denied - image path not allowed: {resolved}"

        return True, "Valid image file"
    except Exception as e:
        logger.error(f"Image validation error: {e}")
        return False, f"Validation error: {str(e)}"
