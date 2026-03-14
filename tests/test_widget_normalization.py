"""
Tests for frontend widget normalization logic — extracted and tested as pure
Python functions that mirror the TypeScript implementations.

This tests the LOGIC that the frontend widgets depend on, without needing
a browser. The actual TypeScript implementations are verified to match
these behaviors via the build + manual tests.

Covers:
- FormWidget field normalization (the root cause of shared-state + duplicate key bugs)
- ChoiceWidget option normalization
- OutlineWidget block normalization
- DiffWidget change normalization
"""
import re
import pytest


# ══════════════════════════════════════════════════════════════
# FormWidget field normalization (mirrors normalizeFormFields in InteractiveWidget.tsx)
# ══════════════════════════════════════════════════════════════

def normalize_form_fields(raw_fields: list) -> list:
    """
    Python mirror of the TypeScript normalizeFormFields function.
    Must produce identical behavior to the frontend implementation.
    """
    valid = [f for f in raw_fields if f and isinstance(f, dict) and len(f) > 0]
    seen = {}
    result = []
    for idx, f in enumerate(valid):
        # Derive name: prefer explicit name/id/key, else slugify label, else index
        name = f.get("name") or f.get("id") or f.get("key") or ""
        if not name and f.get("label"):
            name = re.sub(r'[^a-z0-9]+', '_', str(f["label"]).lower()).strip('_')
        if not name:
            name = f"field_{idx}"
        # Ensure uniqueness
        count = seen.get(name, 0)
        seen[name] = count + 1
        if count > 0:
            name = f"{name}_{count}"
        result.append({
            "name": name,
            "label": f.get("label") or f.get("name") or f"Field {idx + 1}",
            "type": f.get("type") or "text",
            "options": f.get("options"),
            "default": f.get("default") if f.get("default") is not None else f.get("defaultValue") if f.get("defaultValue") is not None else f.get("value"),
        })
    return result


class TestFormFieldNormalization:
    """Tests for the core bug: model sends fields without 'name' property."""

    def test_fields_with_names_preserved(self):
        """When model provides proper names, they pass through unchanged."""
        raw = [
            {"name": "product", "label": "Product Name", "type": "text"},
            {"name": "audience", "label": "Target Audience", "type": "text"},
        ]
        result = normalize_form_fields(raw)
        assert len(result) == 2
        assert result[0]["name"] == "product"
        assert result[1]["name"] == "audience"

    def test_fields_without_names_get_slugified_labels(self):
        """ROOT BUG: model sends {label, type} without name.
        Each field must get a UNIQUE name derived from label."""
        raw = [
            {"label": "Product Name", "type": "text"},
            {"label": "Target Audience", "type": "text"},
            {"label": "Key Benefit", "type": "text"},
            {"label": "Launch Date", "type": "text"},
        ]
        result = normalize_form_fields(raw)
        assert len(result) == 4
        names = [f["name"] for f in result]
        # All names must be unique
        assert len(set(names)) == 4, f"Duplicate names detected: {names}"
        # Names should be human-readable slugs
        assert result[0]["name"] == "product_name"
        assert result[1]["name"] == "target_audience"
        assert result[2]["name"] == "key_benefit"
        assert result[3]["name"] == "launch_date"

    def test_duplicate_labels_get_unique_names(self):
        """If two fields have the same label, names must still be unique."""
        raw = [
            {"label": "Option", "type": "text"},
            {"label": "Option", "type": "text"},
            {"label": "Option", "type": "text"},
        ]
        result = normalize_form_fields(raw)
        names = [f["name"] for f in result]
        assert len(set(names)) == 3, f"Duplicate names: {names}"
        assert names[0] == "option"
        assert names[1] == "option_1"
        assert names[2] == "option_2"

    def test_no_label_no_name_uses_index(self):
        """If field has neither name nor label, fall back to index."""
        raw = [
            {"type": "text"},
            {"type": "number"},
        ]
        result = normalize_form_fields(raw)
        assert result[0]["name"] == "field_0"
        assert result[1]["name"] == "field_1"
        assert result[0]["label"] == "Field 1"
        assert result[1]["label"] == "Field 2"

    def test_empty_fields_filtered(self):
        """Empty objects should be removed."""
        raw = [{}, {"label": "Valid", "type": "text"}, None, {}, 42]
        result = normalize_form_fields(raw)
        assert len(result) == 1
        assert result[0]["label"] == "Valid"

    def test_type_defaults_to_text(self):
        """If model omits type, default to 'text'."""
        raw = [{"label": "Name"}]
        result = normalize_form_fields(raw)
        assert result[0]["type"] == "text"

    def test_default_value_extraction(self):
        """Multiple default value property names should be checked."""
        raw = [
            {"label": "A", "default": "val1"},
            {"label": "B", "defaultValue": "val2"},
            {"label": "C", "value": "val3"},
            {"label": "D"},  # No default
        ]
        result = normalize_form_fields(raw)
        assert result[0]["default"] == "val1"
        assert result[1]["default"] == "val2"
        assert result[2]["default"] == "val3"
        assert result[3]["default"] is None

    def test_id_and_key_as_name_sources(self):
        """Fields with 'id' or 'key' instead of 'name' should work."""
        raw = [
            {"id": "field_id", "label": "By ID", "type": "text"},
            {"key": "field_key", "label": "By Key", "type": "text"},
        ]
        result = normalize_form_fields(raw)
        assert result[0]["name"] == "field_id"
        assert result[1]["name"] == "field_key"

    def test_special_characters_in_labels(self):
        """Labels with special characters should produce clean slugs."""
        raw = [
            {"label": "What's your goal? (optional)", "type": "text"},
            {"label": "Email / Phone #", "type": "text"},
        ]
        result = normalize_form_fields(raw)
        assert " " not in result[0]["name"]
        assert " " not in result[1]["name"]
        # Should only contain lowercase alphanumeric and underscores
        for f in result:
            assert re.match(r'^[a-z0-9_]+$', f["name"]), f"Invalid name: {f['name']}"

    def test_preserves_options_for_select(self):
        raw = [{"name": "color", "label": "Color", "type": "select", "options": ["Red", "Blue", "Green"]}]
        result = normalize_form_fields(raw)
        assert result[0]["options"] == ["Red", "Blue", "Green"]

    def test_realistic_writer_form(self):
        """Simulate what the Writer model actually sends — the exact scenario that was broken."""
        raw = [
            {"label": "Product Name", "type": "text"},
            {"label": "Target Audience", "type": "text"},
            {"label": "Key Benefit", "type": "text"},
            {"label": "Launch Date", "type": "text"},
        ]
        result = normalize_form_fields(raw)
        # Core assertion: each field maps to a unique state key
        names = [f["name"] for f in result]
        assert len(names) == len(set(names)), f"SHARED STATE BUG: duplicate names {names}"
        # None should be 'undefined' or empty
        assert all(n and n != "undefined" for n in names), f"Undefined names: {names}"


# ══════════════════════════════════════════════════════════════
# ChoiceWidget option normalization
# ══════════════════════════════════════════════════════════════

def normalize_choice_options(raw_options: list) -> list:
    """Mirror of how ChoiceWidget normalizes options."""
    result = []
    for opt in raw_options:
        if isinstance(opt, dict):
            result.append({
                "label": str(opt.get("label", opt.get("value", ""))),
                "value": str(opt.get("value", opt.get("label", ""))),
                "description": opt.get("description"),
            })
        elif isinstance(opt, str):
            result.append({"label": opt, "value": opt, "description": None})
        elif isinstance(opt, (int, float)):
            result.append({"label": str(opt), "value": str(opt), "description": None})
    return result


class TestChoiceOptionNormalization:
    def test_object_options(self):
        raw = [{"label": "Python", "value": "py"}, {"label": "JavaScript", "value": "js"}]
        result = normalize_choice_options(raw)
        assert result[0]["label"] == "Python"
        assert result[0]["value"] == "py"

    def test_string_options(self):
        raw = ["Option A", "Option B", "Option C"]
        result = normalize_choice_options(raw)
        assert all(r["label"] == r["value"] for r in result)

    def test_mixed_options(self):
        raw = [{"label": "Custom", "value": "custom"}, "Simple", 42]
        result = normalize_choice_options(raw)
        assert len(result) == 3
        assert result[2]["value"] == "42"

    def test_label_only(self):
        raw = [{"label": "Only Label"}]
        result = normalize_choice_options(raw)
        assert result[0]["value"] == "Only Label"

    def test_value_only(self):
        raw = [{"value": "only_val"}]
        result = normalize_choice_options(raw)
        assert result[0]["label"] == "only_val"


# ══════════════════════════════════════════════════════════════
# OutlineWidget block normalization
# ══════════════════════════════════════════════════════════════

def normalize_outline_items(raw_items: list) -> list:
    """Mirror of how OutlineWidget normalizes items from config."""
    result = []
    for i, item in enumerate(raw_items):
        if isinstance(item, str):
            result.append({"id": f"block_{i}", "text": item, "description": None})
        elif isinstance(item, dict):
            text = item.get("title") or item.get("label") or item.get("text") or ""
            desc = item.get("description") or item.get("desc")
            result.append({"id": f"block_{i}", "text": str(text), "description": desc})
    return result


class TestOutlineBlockNormalization:
    def test_string_items(self):
        raw = ["Introduction", "Main Body", "Conclusion"]
        result = normalize_outline_items(raw)
        assert len(result) == 3
        assert result[0]["text"] == "Introduction"
        assert result[0]["id"] == "block_0"

    def test_object_items_with_title(self):
        raw = [{"title": "Intro", "description": "Opening hook"}, {"title": "Body"}]
        result = normalize_outline_items(raw)
        assert result[0]["text"] == "Intro"
        assert result[0]["description"] == "Opening hook"
        assert result[1]["description"] is None

    def test_object_items_with_label(self):
        raw = [{"label": "Section 1"}, {"label": "Section 2"}]
        result = normalize_outline_items(raw)
        assert result[0]["text"] == "Section 1"

    def test_mixed_items(self):
        raw = ["Simple string", {"title": "Complex", "description": "With desc"}]
        result = normalize_outline_items(raw)
        assert len(result) == 2
        assert result[0]["text"] == "Simple string"
        assert result[1]["description"] == "With desc"

    def test_unique_ids(self):
        raw = ["A", "B", "C", "D"]
        result = normalize_outline_items(raw)
        ids = [b["id"] for b in result]
        assert len(set(ids)) == 4


# ══════════════════════════════════════════════════════════════
# DiffWidget change normalization
# ══════════════════════════════════════════════════════════════

def normalize_diff_changes(raw_changes: list) -> list:
    """Mirror of how DiffWidget normalizes changes from config."""
    result = []
    for i, c in enumerate(raw_changes):
        if not isinstance(c, dict):
            continue
        result.append({
            "id": c.get("id") or f"change_{i}",
            "label": c.get("label") or c.get("title") or c.get("description") or f"Change {i + 1}",
            "original": str(c.get("original", "")),
            "proposed": str(c.get("proposed", c.get("new", c.get("replacement", "")))),
        })
    return result


class TestDiffChangeNormalization:
    def test_standard_changes(self):
        raw = [
            {"id": "c1", "label": "Intro", "original": "Old text", "proposed": "New text"},
            {"id": "c2", "label": "Body", "original": "Old body", "proposed": "New body"},
        ]
        result = normalize_diff_changes(raw)
        assert len(result) == 2
        assert result[0]["original"] == "Old text"
        assert result[0]["proposed"] == "New text"

    def test_missing_id_gets_generated(self):
        raw = [{"label": "Fix", "original": "bug", "proposed": "fix"}]
        result = normalize_diff_changes(raw)
        assert result[0]["id"] == "change_0"

    def test_alternative_proposed_keys(self):
        """Model might use 'new' or 'replacement' instead of 'proposed'."""
        raw = [
            {"id": "c1", "label": "A", "original": "old", "new": "new_text"},
            {"id": "c2", "label": "B", "original": "old", "replacement": "repl_text"},
        ]
        result = normalize_diff_changes(raw)
        assert result[0]["proposed"] == "new_text"
        assert result[1]["proposed"] == "repl_text"

    def test_non_dict_filtered(self):
        raw = [{"id": "c1", "original": "a", "proposed": "b"}, "not a dict", 42, None]
        result = normalize_diff_changes(raw)
        assert len(result) == 1


# ══════════════════════════════════════════════════════════════
# Select option normalization (mirrors normalizeSelectOption)
# ══════════════════════════════════════════════════════════════

def normalize_select_option(opt, index: int) -> dict:
    """Mirror of normalizeSelectOption in InteractiveWidget.tsx."""
    if isinstance(opt, dict) and opt is not None:
        value_raw = opt.get("value") if opt.get("value") is not None else opt.get("label", "")
        label_raw = opt.get("label") if opt.get("label") is not None else opt.get("value", "")
        return {
            "key": f"{value_raw}-{index}",
            "value": str(value_raw),
            "label": str(label_raw),
        }
    return {
        "key": f"{opt}-{index}",
        "value": str(opt),
        "label": str(opt),
    }


class TestSelectOptionNormalization:
    def test_object_with_both(self):
        result = normalize_select_option({"label": "Red", "value": "red"}, 0)
        assert result["label"] == "Red"
        assert result["value"] == "red"

    def test_string_option(self):
        result = normalize_select_option("blue", 1)
        assert result["label"] == "blue"
        assert result["value"] == "blue"
        assert result["key"] == "blue-1"

    def test_number_option(self):
        result = normalize_select_option(42, 2)
        assert result["value"] == "42"

    def test_unique_keys(self):
        options = ["A", "B", "A"]  # Duplicate values
        keys = [normalize_select_option(o, i)["key"] for i, o in enumerate(options)]
        # Keys should be unique because of the index
        assert keys[0] == "A-0"
        assert keys[2] == "A-2"  # Different index makes it unique
