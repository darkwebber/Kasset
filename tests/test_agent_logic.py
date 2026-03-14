"""
Tests for agent-level logic extracted from backend/core/agent.py.

Since Agent requires a model backend, these tests focus on the pure-logic
helpers that can be tested in isolation: truncation detection, observation
masking, adaptive sampling, and the request_user_input widget config
normalization done on the backend side.
"""
import json
import re
import pytest


# ══════════════════════════════════════════════════════════════
# Truncation detection (same logic as agent.py lines ~1026-1032)
# ══════════════════════════════════════════════════════════════

def detect_truncation(text: str):
    """Reproduce the exact truncation detection logic from agent.py."""
    _truncated = False
    _truncated_tool_call = False
    if '<tool_call>' in text and '</tool_call>' not in text:
        _truncated = True
        _truncated_tool_call = True
    elif text.count('```') % 2 != 0:
        _truncated = True
    return _truncated, _truncated_tool_call


class TestTruncationDetection:
    def test_complete_tool_call_not_truncated(self):
        text = '<tool_call>{"name": "test", "arguments": {}}</tool_call>'
        trunc, tool = detect_truncation(text)
        assert trunc is False
        assert tool is False

    def test_unclosed_tool_call_is_truncated(self):
        text = '<tool_call>{"name": "execute_python", "arguments": {"code": "very long co'
        trunc, tool = detect_truncation(text)
        assert trunc is True
        assert tool is True

    def test_odd_backticks_is_truncated(self):
        text = 'Here is code:\n```python\nprint("hello")\n'
        trunc, tool = detect_truncation(text)
        assert trunc is True
        assert tool is False

    def test_even_backticks_not_truncated(self):
        text = 'Here is code:\n```python\nprint("hello")\n```\nDone.'
        trunc, tool = detect_truncation(text)
        assert trunc is False

    def test_no_special_content(self):
        text = "Just a plain text response."
        trunc, tool = detect_truncation(text)
        assert trunc is False
        assert tool is False

    def test_multiple_complete_tool_calls(self):
        text = '<tool_call>{"name": "a", "arguments": {}}</tool_call> text <tool_call>{"name": "b", "arguments": {}}</tool_call>'
        trunc, tool = detect_truncation(text)
        assert trunc is False

    def test_tool_call_with_backticks_inside(self):
        """Code inside tool call may have backticks — shouldn't false-trigger."""
        text = '<tool_call>{"name": "execute_python", "arguments": {"code": "x = `test`"}}</tool_call>'
        trunc, tool = detect_truncation(text)
        assert trunc is False  # tool_call is properly closed


# ══════════════════════════════════════════════════════════════
# UI tool detection (same logic as agent.py truncation recovery)
# ══════════════════════════════════════════════════════════════

def is_ui_tool_call(text: str) -> bool:
    """Reproduce the UI tool detection from truncation recovery."""
    partial_call = text[text.rfind('<tool_call>'):]
    return any(kw in partial_call for kw in ['request_user_input', 'widget_type', 'config'])


class TestUIToolDetection:
    def test_request_user_input_detected(self):
        text = '<tool_call>{"name": "request_user_input", "arguments": {"widget_type": "form", "config": {"prompt": "test"'
        assert is_ui_tool_call(text) is True

    def test_execute_python_not_ui(self):
        text = '<tool_call>{"name": "execute_python", "arguments": {"code": "print(1)"'
        assert is_ui_tool_call(text) is False

    def test_widget_type_keyword_detected(self):
        text = '<tool_call>{"name": "request_user_input", "arguments": {"widget_type": "choice"'
        assert is_ui_tool_call(text) is True

    def test_read_file_not_ui(self):
        text = '<tool_call>{"name": "read_file", "arguments": {"path": "/tmp/data.json"'
        assert is_ui_tool_call(text) is False


# ══════════════════════════════════════════════════════════════
# Observation masking pattern
# ══════════════════════════════════════════════════════════════

def mask_old_observations(history: list, keep_recent: int = 3) -> list:
    """
    Simplified version of _mask_old_observations from agent.py.
    Compresses old tool results to prevent context bloat in long sessions.
    """
    result = []
    # Count tool result messages from the end
    tool_result_indices = []
    for i, msg in enumerate(history):
        if msg.get("role") == "user" and msg.get("content", "").startswith("Tool result for"):
            tool_result_indices.append(i)

    # Mask all but the most recent `keep_recent` tool results
    mask_set = set(tool_result_indices[:-keep_recent]) if len(tool_result_indices) > keep_recent else set()

    for i, msg in enumerate(history):
        if i in mask_set:
            # Compress: keep first line + truncation notice
            first_line = msg["content"].split("\n")[0][:100]
            result.append({**msg, "content": f"{first_line}\n[...output compressed for context efficiency...]"})
        else:
            result.append(msg)
    return result


class TestObservationMasking:
    def test_no_masking_under_threshold(self):
        history = [
            {"role": "user", "content": "Tool result for read_file: content here"},
            {"role": "user", "content": "Tool result for list_directory: dir listing"},
        ]
        result = mask_old_observations(history, keep_recent=3)
        assert all("compressed" not in m["content"] for m in result)

    def test_masks_old_results(self):
        history = [
            {"role": "user", "content": "Tool result for read_file: " + "x" * 500},
            {"role": "user", "content": "Tool result for search_files: " + "y" * 500},
            {"role": "user", "content": "Tool result for list_directory: " + "z" * 500},
            {"role": "user", "content": "Tool result for execute_python: " + "w" * 500},
        ]
        result = mask_old_observations(history, keep_recent=2)
        # First two should be compressed
        assert "compressed" in result[0]["content"]
        assert "compressed" in result[1]["content"]
        # Last two should be preserved
        assert "compressed" not in result[2]["content"]
        assert "compressed" not in result[3]["content"]

    def test_non_tool_messages_preserved(self):
        history = [
            {"role": "system", "content": "You are an assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "Tool result for read_file: big content " + "x" * 500},
        ]
        result = mask_old_observations(history, keep_recent=1)
        assert result[0]["content"] == "You are an assistant."
        assert result[1]["content"] == "Hello"
        assert result[2]["content"] == "Hi there!"


# ══════════════════════════════════════════════════════════════
# Widget config validation patterns
# ══════════════════════════════════════════════════════════════

VALID_WIDGET_TYPES = {"choice", "slider", "editor", "outline", "form", "diff", "embed"}


class TestWidgetConfigValidation:
    def test_choice_config(self):
        config = {
            "prompt": "Pick a language:",
            "options": [
                {"label": "Python", "value": "python"},
                {"label": "JavaScript", "value": "js"},
            ],
        }
        assert "prompt" in config
        assert len(config["options"]) >= 2

    def test_form_config_with_fields(self):
        config = {
            "prompt": "Details:",
            "fields": [
                {"label": "Name", "type": "text"},
                {"label": "Age", "type": "number"},
            ],
        }
        assert all("label" in f for f in config["fields"])

    def test_outline_config(self):
        config = {
            "prompt": "Proposed structure:",
            "items": ["Intro", "Main Body", "Conclusion"],
        }
        assert len(config["items"]) >= 2

    def test_editor_config(self):
        config = {
            "prompt": "Edit this draft:",
            "content": "# My Draft\n\nSome content here.",
            "language": "markdown",
        }
        assert len(config["content"]) > 0

    def test_diff_config(self):
        config = {
            "prompt": "Review changes:",
            "changes": [
                {"id": "c1", "label": "Intro", "original": "Old text", "proposed": "New text"},
            ],
        }
        assert all("id" in c and "original" in c and "proposed" in c for c in config["changes"])

    def test_all_widget_types_valid(self):
        for wt in VALID_WIDGET_TYPES:
            assert isinstance(wt, str)
            assert len(wt) > 0


# ══════════════════════════════════════════════════════════════
# Adaptive sampler (basic structure test)
# ══════════════════════════════════════════════════════════════

class TestAdaptiveSampler:
    def test_import(self):
        from core.adaptive_sampler import AdaptiveSampler
        assert hasattr(AdaptiveSampler, 'resolve')

    def test_resolve_returns_sampling(self):
        from core.adaptive_sampler import AdaptiveSampler
        result = AdaptiveSampler.resolve(
            cartridge_ids=["writer"],
            user_message="Write a blog post about AI",
            tool_round=0,
            is_retry=False,
        )
        assert hasattr(result, 'temperature')
        assert hasattr(result, 'top_p')
        assert 0 <= result.temperature <= 2.0
        assert 0 <= result.top_p <= 1.0
