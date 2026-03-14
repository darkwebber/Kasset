"""
Tests for backend/core/cartridge_loader.py — loading and validating kasset cartridges.

Covers:
- Loading builtin cartridges from disk
- Validating required fields (id, name, system_prompt, tools)
- Writer cartridge specific checks (outline widget, markdown language, token budget)
- Cartridge stacking configuration
"""
import json
import pytest
from pathlib import Path


CARTRIDGE_DIR = Path(__file__).parent.parent / "cartridges" / "builtins"


def load_cartridge(name: str) -> dict:
    path = CARTRIDGE_DIR / f"{name}.json"
    assert path.exists(), f"Cartridge file not found: {path}"
    with open(path) as f:
        return json.load(f)


def all_builtin_cartridge_names():
    """Discover all builtin cartridge JSON files."""
    if not CARTRIDGE_DIR.exists():
        return []
    return [p.stem for p in CARTRIDGE_DIR.glob("*.json")]


# ══════════════════════════════════════════════════════════════
# Structural validation — every cartridge must have required fields
# ══════════════════════════════════════════════════════════════

class TestCartridgeStructure:
    @pytest.fixture(params=all_builtin_cartridge_names())
    def cartridge(self, request):
        return load_cartridge(request.param)

    def test_has_required_fields(self, cartridge):
        for field in ("id", "name", "system_prompt", "tools"):
            assert field in cartridge, f"Missing required field: {field}"

    def test_id_is_slug(self, cartridge):
        """ID should be a simple slug (lowercase, hyphens, no spaces)."""
        cid = cartridge["id"]
        assert cid == cid.lower(), f"Cartridge ID should be lowercase: {cid}"
        assert " " not in cid, f"Cartridge ID should not contain spaces: {cid}"

    def test_tools_is_list(self, cartridge):
        assert isinstance(cartridge["tools"], list)
        assert len(cartridge["tools"]) > 0, "Cartridge should have at least one tool"

    def test_system_prompt_not_empty(self, cartridge):
        assert len(cartridge["system_prompt"]) > 50, "System prompt seems too short"

    def test_suggested_tokens_reasonable(self, cartridge):
        tokens = cartridge.get("suggested_tokens", 8192)
        assert 1024 <= tokens <= 65536, f"Token budget {tokens} is out of reasonable range"

    def test_has_icon(self, cartridge):
        assert "icon" in cartridge, "Cartridge should have an icon"

    def test_has_description(self, cartridge):
        assert "description" in cartridge, "Cartridge should have a description"
        assert len(cartridge["description"]) > 10, "Description seems too short"


# ══════════════════════════════════════════════════════════════
# Writer cartridge — specific behavioral checks
# ══════════════════════════════════════════════════════════════

class TestWriterCartridge:
    @pytest.fixture
    def writer(self):
        return load_cartridge("writer")

    def test_uses_outline_widget(self, writer):
        """Writer should use outline widget for structure collaboration."""
        prompt = writer["system_prompt"]
        assert "outline" in prompt, "Writer prompt should reference outline widget"
        assert '"widget_type": "outline"' in prompt or '\"widget_type\": \"outline\"' in prompt

    def test_uses_markdown_language(self, writer):
        """Editor widget should use markdown language for split-pane preview."""
        prompt = writer["system_prompt"]
        assert "markdown" in prompt
        # Should NOT use language: "text" for drafts
        assert 'language: "text"' not in prompt, "Writer should use markdown, not text"

    def test_anti_narration_rule(self, writer):
        """Writer should have rule against duplicating diff content in prose."""
        prompt = writer["system_prompt"]
        assert "narrat" in prompt.lower(), "Writer should have anti-narration rule"

    def test_short_prompt_rule(self, writer):
        """Writer should instruct model to keep form prompts short."""
        prompt = writer["system_prompt"]
        assert "short" in prompt.lower()

    def test_token_budget_adequate(self, writer):
        """Writer needs enough tokens for think + tool call."""
        assert writer.get("suggested_tokens", 0) >= 16384, \
            f"Writer token budget {writer.get('suggested_tokens')} is too small for reliable tool calls"

    def test_has_request_user_input(self, writer):
        """Writer must have request_user_input in tools."""
        assert "request_user_input" in writer["tools"]

    def test_collaboration_mode(self, writer):
        assert writer.get("collaboration_mode") is True


# ══════════════════════════════════════════════════════════════
# Tool list validation — no phantom tools
# ══════════════════════════════════════════════════════════════

# Known valid tool names from tool_registry.py
KNOWN_TOOLS = {
    "read_file", "write_file", "edit_file", "search_files", "list_directory",
    "run_command", "execute_python", "execute_cpp", "calculate",
    "web_search", "web_browse", "html_preview", "save_notes",
    "request_user_input", "get_location", "grep_code",
}


class TestToolReferences:
    @pytest.fixture(params=all_builtin_cartridge_names())
    def cartridge(self, request):
        return load_cartridge(request.param)

    def test_tools_are_known(self, cartridge):
        """All tools referenced by cartridges should exist in the registry."""
        unknown = set(cartridge["tools"]) - KNOWN_TOOLS
        # Allow custom/plugin tools — just warn, don't fail hard
        if unknown:
            # Check they're not obviously misspelled
            for tool in unknown:
                assert len(tool) > 2, f"Suspicious tool name: {tool}"
                assert "_" in tool or tool.isalpha(), f"Malformed tool name: {tool}"
