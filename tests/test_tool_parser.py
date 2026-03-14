"""
Tests for backend/core/tool_parser.py — the critical parsing layer between
raw model output and structured tool calls.

Covers:
- parse_thinking: extracting think blocks from model output
- extract_tool_call: all supported formats (XML, JSON, hybrid, malformed)
- has_tool_call_attempt: detecting partial/failed tool calls
- diagnose_tool_call_error: generating actionable error feedback
- enrich_tool_error: context-aware error hints
"""
import pytest
from core.tool_parser import (
    parse_thinking,
    extract_tool_call,
    has_tool_call_attempt,
    diagnose_tool_call_error,
    enrich_tool_error,
)


# ══════════════════════════════════════════════════════════════
# parse_thinking
# ══════════════════════════════════════════════════════════════

class TestParseThinking:
    def test_standard_think_tags(self):
        raw = "<think>Planning the approach...</think>Here is the answer."
        thought, answer = parse_thinking(raw)
        assert thought == "Planning the approach..."
        assert answer == "Here is the answer."

    def test_no_think_tags(self):
        raw = "Just a plain response with no thinking."
        thought, answer = parse_thinking(raw)
        assert thought == ""
        assert answer == "Just a plain response with no thinking."

    def test_open_think_no_close(self):
        """Model starts thinking but gets truncated before closing."""
        raw = "<think>I need to figure this out but got cut off"
        thought, answer = parse_thinking(raw)
        assert thought == "I need to figure this out but got cut off"
        assert answer == ""

    def test_close_think_no_open(self):
        """Model output has closing tag but no opening (e.g. resumed mid-stream)."""
        raw = "partial thinking content</think>The actual answer."
        thought, answer = parse_thinking(raw)
        assert thought == "partial thinking content"
        assert answer == "The actual answer."

    def test_alternative_thinking_tags(self):
        raw = "<|thinking|>Alt format thinking<|/thinking|>Alt answer."
        thought, answer = parse_thinking(raw)
        assert thought == "Alt format thinking"
        assert answer == "Alt answer."

    def test_multiline_thinking(self):
        raw = "<think>\nLine 1\nLine 2\nLine 3\n</think>\nAnswer here."
        thought, answer = parse_thinking(raw)
        assert "Line 1" in thought
        assert "Line 3" in thought
        assert answer == "Answer here."

    def test_empty_think_block(self):
        raw = "<think></think>Answer only."
        thought, answer = parse_thinking(raw)
        assert thought == ""
        assert answer == "Answer only."

    def test_text_before_think(self):
        raw = "Preamble text <think>Thinking here</think>And the answer."
        thought, answer = parse_thinking(raw)
        assert thought == "Thinking here"
        assert "Preamble text" in answer
        assert "And the answer." in answer


# ══════════════════════════════════════════════════════════════
# extract_tool_call — Qwen3-Coder XML format
# ══════════════════════════════════════════════════════════════

class TestExtractToolCallXML:
    def test_standard_xml_format(self):
        text = '<tool_call><function=read_file><parameter=path>/tmp/test.py</parameter></function></tool_call>'
        result = extract_tool_call(text)
        assert result is not None
        assert result["name"] == "read_file"
        assert result["arguments"]["path"] == "/tmp/test.py"

    def test_xml_multiple_params(self):
        text = (
            '<tool_call><function=execute_python>'
            '<parameter=code>print("hello")</parameter>'
            '</function></tool_call>'
        )
        result = extract_tool_call(text)
        assert result is not None
        assert result["name"] == "execute_python"
        assert result["arguments"]["code"] == 'print("hello")'

    def test_xml_with_surrounding_text(self):
        text = 'Let me read the file.\n\n<tool_call><function=read_file><parameter=path>/test.txt</parameter></function></tool_call>'
        result = extract_tool_call(text)
        assert result is not None
        assert result["name"] == "read_file"

    def test_xml_with_whitespace(self):
        text = '<tool_call>\n  <function=list_directory>\n    <parameter=directory>/home</parameter>\n  </function>\n</tool_call>'
        result = extract_tool_call(text)
        assert result is not None
        assert result["name"] == "list_directory"


# ══════════════════════════════════════════════════════════════
# extract_tool_call — JSON format
# ══════════════════════════════════════════════════════════════

class TestExtractToolCallJSON:
    def test_standard_json_in_tags(self):
        text = '<tool_call>{"name": "calculate", "arguments": {"expression": "2+2"}}</tool_call>'
        result = extract_tool_call(text)
        assert result is not None
        assert result["name"] == "calculate"
        assert result["arguments"]["expression"] == "2+2"

    def test_json_unclosed_tag(self):
        """Model forgets closing tag — very common."""
        text = '<tool_call>{"name": "read_file", "arguments": {"path": "/tmp/test.py"}}'
        result = extract_tool_call(text)
        assert result is not None
        assert result["name"] == "read_file"

    def test_json_with_newlines_in_code(self):
        """Model puts raw newlines in code strings."""
        text = '<tool_call>{"name": "execute_python", "arguments": {"code": "x = 1\\ny = 2\\nprint(x+y)"}}</tool_call>'
        result = extract_tool_call(text)
        assert result is not None
        assert result["name"] == "execute_python"

    def test_alternative_tag_format(self):
        text = '<|tool_call|>{"name": "calculate", "arguments": {"expression": "5*5"}}<|/tool_call|>'
        result = extract_tool_call(text)
        assert result is not None
        assert result["name"] == "calculate"

    def test_raw_json_no_tags(self):
        text = 'Here is the tool call:\n{"name": "search_files", "arguments": {"pattern": "*.py", "directory": "/src"}}'
        result = extract_tool_call(text)
        assert result is not None
        assert result["name"] == "search_files"

    def test_json_with_nested_objects(self):
        """request_user_input has deeply nested config."""
        text = '<tool_call>{"name": "request_user_input", "arguments": {"widget_type": "form", "config": {"prompt": "Details:", "fields": [{"label": "Name", "type": "text"}]}}}</tool_call>'
        result = extract_tool_call(text)
        assert result is not None
        assert result["name"] == "request_user_input"
        assert result["arguments"]["widget_type"] == "form"

    def test_execute_python_direct_scan(self):
        """Fallback extraction for execute_python with malformed JSON."""
        text = '<tool_call>{"name": "execute_python", "arguments": {"code": "for i in range(10):\n    print(i)"}}'
        result = extract_tool_call(text)
        assert result is not None
        assert result["name"] == "execute_python"
        assert "range(10)" in result["arguments"]["code"]


# ══════════════════════════════════════════════════════════════
# extract_tool_call — failure cases
# ══════════════════════════════════════════════════════════════

class TestExtractToolCallFailures:
    def test_no_tool_call(self):
        text = "This is just a regular message with no tool calls."
        assert extract_tool_call(text) is None

    def test_truncated_tool_call(self):
        """Tool call started but output was truncated."""
        text = '<tool_call>{"name": "execute_python", "arguments": {"code": "very long code that gets'
        # This has unclosed JSON, parser may or may not extract it
        # The important thing is it doesn't crash
        result = extract_tool_call(text)
        # Result may be None or partial — just ensure no exception

    def test_empty_tool_call_tags(self):
        text = "<tool_call></tool_call>"
        assert extract_tool_call(text) is None

    def test_malformed_json(self):
        text = '<tool_call>{"name": "read_file", "arguments": {bad json here}}</tool_call>'
        # Should not crash
        result = extract_tool_call(text)
        # May or may not parse, but must not raise


# ══════════════════════════════════════════════════════════════
# has_tool_call_attempt
# ══════════════════════════════════════════════════════════════

class TestHasToolCallAttempt:
    def test_standard_tag(self):
        assert has_tool_call_attempt("<tool_call>{") is True

    def test_alternative_tag(self):
        assert has_tool_call_attempt("<|tool_call|>{") is True

    def test_xml_function_tag(self):
        assert has_tool_call_attempt("<function=read_file>") is True

    def test_no_tool_call(self):
        assert has_tool_call_attempt("Just a regular message.") is False

    def test_case_insensitive(self):
        assert has_tool_call_attempt("<TOOL_CALL>{") is True


# ══════════════════════════════════════════════════════════════
# diagnose_tool_call_error
# ══════════════════════════════════════════════════════════════

class TestDiagnoseToolCallError:
    def test_unclosed_braces(self):
        text = '<tool_call>{"name": "test", "arguments": {"key": "val"}</tool_call>'
        diagnosis = diagnose_tool_call_error(text)
        assert "SYSTEM" in diagnosis
        assert "brace" in diagnosis.lower() or "parse error" in diagnosis.lower()

    def test_missing_name(self):
        text = '<tool_call>{"arguments": {"key": "val"}}</tool_call>'
        diagnosis = diagnose_tool_call_error(text)
        assert "name" in diagnosis.lower()

    def test_missing_arguments(self):
        text = '<tool_call>{"name": "test"}</tool_call>'
        diagnosis = diagnose_tool_call_error(text)
        assert "arguments" in diagnosis.lower()

    def test_empty_tool_call(self):
        text = '<tool_call></tool_call>'
        diagnosis = diagnose_tool_call_error(text)
        assert "SYSTEM" in diagnosis

    def test_raw_newlines_in_code(self):
        text = '<tool_call>{"name": "execute_python", "arguments": {"code": "line1\nline2"}}</tool_call>'
        diagnosis = diagnose_tool_call_error(text)
        assert "SYSTEM" in diagnosis


# ══════════════════════════════════════════════════════════════
# enrich_tool_error
# ══════════════════════════════════════════════════════════════

class TestEnrichToolError:
    def test_file_not_found(self):
        result = enrich_tool_error("read_file", {"path": "/nonexistent"}, "FileNotFoundError: No such file or directory")
        assert "list_directory" in result.lower() or "verify" in result.lower()

    def test_syntax_error(self):
        result = enrich_tool_error("execute_python", {"code": "x ="}, "SyntaxError: invalid syntax at line 1")
        assert "syntax" in result.lower()
        assert "line 1" in result

    def test_name_error(self):
        result = enrich_tool_error("execute_python", {"code": "print(x)"}, "NameError: name 'x' is not defined")
        assert "x" in result
        assert "defined" in result.lower()

    def test_module_not_found(self):
        result = enrich_tool_error("execute_python", {"code": "import foo"}, "ModuleNotFoundError: No module named 'foo'")
        assert "foo" in result
        assert "installed" in result.lower() or "module" in result.lower()

    def test_permission_denied(self):
        result = enrich_tool_error("write_file", {"path": "/etc/shadow"}, "Permission denied: /etc/shadow")
        assert "permission" in result.lower()

    def test_timeout(self):
        result = enrich_tool_error("run_command", {"command": "sleep 100"}, "Command timed out after 30s")
        assert "timed out" in result.lower()

    def test_zero_division(self):
        result = enrich_tool_error("execute_python", {"code": "1/0"}, "ZeroDivisionError: division by zero")
        assert "zero" in result.lower()

    def test_key_error(self):
        result = enrich_tool_error("execute_python", {"code": "d['x']"}, "KeyError: 'x'")
        assert "key" in result.lower()

    def test_generic_traceback(self):
        result = enrich_tool_error("execute_python", {"code": "bad()"}, "Traceback (most recent call last):\n  ...\nRuntimeError: something")
        assert "traceback" in result.lower() or "exception" in result.lower()
