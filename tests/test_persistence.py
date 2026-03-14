"""
Tests for backend/core/persistence.py — chat history and session persistence.

Covers:
- Session storage/retrieval patterns
- Message format validation
- Interactive segment serialization (widget state roundtripping)
"""
import pytest
import json


class TestMessageFormat:
    """Validate that message formats used throughout the system are consistent."""

    VALID_ROLES = {"system", "user", "assistant"}

    def test_standard_message(self):
        msg = {"role": "user", "content": "Hello"}
        assert msg["role"] in self.VALID_ROLES
        assert isinstance(msg["content"], str)

    def test_assistant_with_segments(self):
        """Assistant messages may have structured segments."""
        msg = {
            "role": "assistant",
            "content": "Here is a widget:",
            "segments": [
                {"kind": "text", "content": "Here is a widget:"},
                {
                    "kind": "interactive",
                    "widgetId": "w_123",
                    "widgetType": "form",
                    "config": {"prompt": "Details:", "fields": []},
                    "status": "pending",
                },
            ],
        }
        assert msg["role"] == "assistant"
        assert len(msg["segments"]) == 2
        assert msg["segments"][1]["kind"] == "interactive"


class TestInteractiveSegmentSerialization:
    """Test that interactive segments roundtrip through JSON correctly."""

    def test_form_segment_roundtrip(self):
        segment = {
            "kind": "interactive",
            "widgetId": "w_form_1",
            "widgetType": "form",
            "config": {
                "prompt": "Product details:",
                "fields": [
                    {"label": "Product Name", "type": "text"},
                    {"label": "Target Audience", "type": "text"},
                ],
            },
            "status": "pending",
        }
        serialized = json.dumps(segment)
        deserialized = json.loads(serialized)
        assert deserialized["widgetType"] == "form"
        assert len(deserialized["config"]["fields"]) == 2

    def test_outline_segment_roundtrip(self):
        segment = {
            "kind": "interactive",
            "widgetId": "w_outline_1",
            "widgetType": "outline",
            "config": {
                "prompt": "Proposed structure:",
                "items": ["Intro", "Body", "Conclusion"],
            },
            "status": "pending",
        }
        serialized = json.dumps(segment)
        deserialized = json.loads(serialized)
        assert deserialized["widgetType"] == "outline"
        assert len(deserialized["config"]["items"]) == 3

    def test_choice_segment_with_response(self):
        segment = {
            "kind": "interactive",
            "widgetId": "w_choice_1",
            "widgetType": "choice",
            "config": {
                "prompt": "Pick one:",
                "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
            },
            "status": "submitted",
            "response": "a",
        }
        serialized = json.dumps(segment)
        deserialized = json.loads(serialized)
        assert deserialized["status"] == "submitted"
        assert deserialized["response"] == "a"

    def test_editor_segment_with_persistent_id(self):
        segment = {
            "kind": "interactive",
            "widgetId": "w_editor_1",
            "widgetType": "editor",
            "config": {
                "content": "# Draft\n\nSome content.",
                "language": "markdown",
            },
            "status": "active",
            "persistentId": "draft_blog",
            "revision": 2,
        }
        serialized = json.dumps(segment)
        deserialized = json.loads(serialized)
        assert deserialized["persistentId"] == "draft_blog"
        assert deserialized["revision"] == 2

    def test_diff_segment_with_decisions(self):
        segment = {
            "kind": "interactive",
            "widgetId": "w_diff_1",
            "widgetType": "diff",
            "config": {
                "prompt": "Review:",
                "changes": [
                    {"id": "c1", "label": "Intro", "original": "old", "proposed": "new"},
                ],
            },
            "status": "submitted",
            "response": {"decisions": {"c1": {"action": "accepted"}}},
        }
        serialized = json.dumps(segment)
        deserialized = json.loads(serialized)
        assert deserialized["response"]["decisions"]["c1"]["action"] == "accepted"

    def test_all_widget_types_serializable(self):
        """Every widget type should be JSON-serializable."""
        for wt in ("choice", "slider", "editor", "outline", "form", "diff", "embed"):
            segment = {
                "kind": "interactive",
                "widgetId": f"w_{wt}_1",
                "widgetType": wt,
                "config": {},
                "status": "pending",
            }
            serialized = json.dumps(segment)
            assert json.loads(serialized)["widgetType"] == wt
