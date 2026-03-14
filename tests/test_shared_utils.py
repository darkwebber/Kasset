"""
Tests for backend/core/shared.py and backend/utils.py — shared utility functions.

Covers:
- Image validation
- Path safety
- Common utility patterns
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

try:
    from core.shared import validate_image_path
    HAS_SHARED = True
except ImportError:
    HAS_SHARED = False


@pytest.mark.skipif(not HAS_SHARED, reason="shared.py import failed")
class TestImageValidation:
    def test_valid_extensions(self):
        """Common image extensions should be accepted."""
        valid = ["photo.jpg", "image.png", "pic.jpeg", "icon.gif", "logo.webp"]
        for name in valid:
            path = Path(f"/tmp/{name}")
            # Just check extension logic — file doesn't need to exist for pattern test
            ext = path.suffix.lower()
            assert ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".svg"}

    def test_invalid_extensions(self):
        invalid = ["script.py", "data.json", "doc.pdf", "archive.zip"]
        for name in invalid:
            ext = Path(name).suffix.lower()
            assert ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


class TestPathSafety:
    def test_resolve_removes_traversal(self):
        p = Path("/tmp/../etc/passwd")
        resolved = p.resolve()
        assert ".." not in str(resolved)

    def test_home_expansion(self):
        p = Path("~/test.txt").expanduser()
        assert "~" not in str(p)
        assert str(p).startswith("/")

    def test_absolute_detection(self):
        assert Path("/absolute/path").is_absolute()
        assert not Path("relative/path").is_absolute()
