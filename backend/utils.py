"""
utils.py — Thin wrappers around shared.py utilities.

All security logic lives in backend.core.shared to avoid duplication.
"""

from backend.core.shared import validate_image_path as _validate


def validate_image_file(image_path: str):
    """Validate image file for security and compatibility.
    Returns (is_valid: bool, message: str).
    Delegates to backend.core.shared.validate_image_path."""
    return _validate(image_path)
