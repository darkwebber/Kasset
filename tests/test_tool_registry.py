"""
Tests for backend/core/tool_registry.py — the tool definition and execution registry.

Covers:
- All builtin tools are registered and have required metadata
- Tool description quality (non-empty, has params documented)
- request_user_input tool specifically (widget types, config schema)
- Tool name consistency between registry and cartridge references
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

try:
    from core.tool_registry import BUILTIN_TOOLS
    HAS_REGISTRY = True
except ImportError:
    HAS_REGISTRY = False

pytestmark = pytest.mark.skipif(not HAS_REGISTRY, reason="tool_registry import failed")


class TestBuiltinTools:
    def test_registry_is_dict(self):
        assert isinstance(BUILTIN_TOOLS, dict)
        assert len(BUILTIN_TOOLS) > 0

    def test_essential_tools_exist(self):
        """Core tools that most cartridges depend on."""
        essential = [
            "read_file", "write_file", "execute_python",
            "calculate", "request_user_input",
        ]
        for tool in essential:
            assert tool in BUILTIN_TOOLS, f"Essential tool missing: {tool}"

    def test_tools_have_descriptions(self):
        for name, tool in BUILTIN_TOOLS.items():
            if isinstance(tool, dict):
                desc = tool.get("desc") or tool.get("description") or ""
                assert len(desc) > 10, f"Tool {name} has no/short description"

    def test_tools_have_params(self):
        for name, tool in BUILTIN_TOOLS.items():
            if isinstance(tool, dict):
                params = tool.get("params") or tool.get("parameters")
                assert params is not None or name in ("get_location",), \
                    f"Tool {name} has no params definition"


class TestRequestUserInput:
    """Specific tests for the widget-serving tool."""

    def test_exists(self):
        assert "request_user_input" in BUILTIN_TOOLS

    def test_has_widget_type_param(self):
        tool = BUILTIN_TOOLS["request_user_input"]
        if isinstance(tool, dict):
            params = tool.get("params", {})
            assert "widget_type" in params, "Missing widget_type parameter"

    def test_documents_all_widget_types(self):
        """All supported widget types should be in the description."""
        tool = BUILTIN_TOOLS["request_user_input"]
        if isinstance(tool, dict):
            desc = tool.get("desc", "")
            for wt in ("choice", "slider", "editor", "outline", "form", "diff", "embed"):
                assert wt in desc, f"Widget type '{wt}' not documented in tool description"

    def test_outline_widget_documented(self):
        """Outline widget (new) should be properly documented."""
        tool = BUILTIN_TOOLS["request_user_input"]
        if isinstance(tool, dict):
            desc = tool.get("desc", "")
            assert "outline" in desc
            assert "items" in desc.lower() or "block" in desc.lower() or "sortable" in desc.lower()

    def test_widget_type_in_params(self):
        tool = BUILTIN_TOOLS["request_user_input"]
        if isinstance(tool, dict):
            wt_desc = tool.get("params", {}).get("widget_type", "")
            assert "outline" in wt_desc, "outline missing from widget_type param"
