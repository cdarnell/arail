"""Unit tests for arail.agents.recap.schema."""

from __future__ import annotations

import pytest

from arail.agents.recap.schema import (
    SchemaError,
    ThinkSubtasks,
    parse_think_subtasks,
)


# ---------------------------------------------------------------------------
# Valid inputs
# ---------------------------------------------------------------------------

VALID_JSON = """\
```json
{
  "think": "I need to cook a burger",
  "subtasks": [
    {"id": "s1", "desc": "Open fridge", "primitive": true, "action": "OPEN(fridge)"},
    {"id": "s2", "desc": "Cook everything", "primitive": false}
  ]
}
```
"""

VALID_JSON_NO_FENCE = """\
Some preamble text.
{
  "think": "plain JSON",
  "subtasks": [
    {"id": "s1", "desc": "step", "primitive": true, "action": "COOK(patty)"}
  ]
}
Some trailing text.
"""

VALID_JSON_EMPTY_SUBTASKS = '```json\n{"think": "nothing to do", "subtasks": []}\n```'


class TestValidInputs:
    def test_fenced_json(self):
        result = parse_think_subtasks(VALID_JSON)
        assert isinstance(result, ThinkSubtasks)
        assert result.think == "I need to cook a burger"
        assert len(result.subtasks) == 2

    def test_bare_json(self):
        result = parse_think_subtasks(VALID_JSON_NO_FENCE)
        assert result.think == "plain JSON"
        assert len(result.subtasks) == 1

    def test_empty_subtasks(self):
        result = parse_think_subtasks(VALID_JSON_EMPTY_SUBTASKS)
        assert result.subtasks == []

    def test_subtask_fields(self):
        result = parse_think_subtasks(VALID_JSON)
        s1 = result.subtasks[0]
        assert s1.id == "s1"
        assert s1.desc == "Open fridge"
        assert s1.primitive is True
        assert s1.action == "OPEN(fridge)"

        s2 = result.subtasks[1]
        assert s2.primitive is False
        assert s2.action == ""

    def test_extra_fields_ignored(self):
        text = '```json\n{"think": "ok", "subtasks": [], "extra": "ignored"}\n```'
        result = parse_think_subtasks(text)
        assert result.think == "ok"

    def test_no_retry_fn_on_success(self):
        called = []
        def retry_fn(msg):
            called.append(msg)
            return ""
        parse_think_subtasks(VALID_JSON, retry_fn=retry_fn)
        assert called == []


# ---------------------------------------------------------------------------
# Invalid inputs — no retry_fn (should raise)
# ---------------------------------------------------------------------------

class TestInvalidInputsNoRetry:
    def test_no_json_at_all(self):
        with pytest.raises(SchemaError):
            parse_think_subtasks("nothing here")

    def test_missing_think(self):
        text = '```json\n{"subtasks": []}\n```'
        with pytest.raises(SchemaError, match="think"):
            parse_think_subtasks(text)

    def test_missing_subtasks(self):
        text = '```json\n{"think": "ok"}\n```'
        with pytest.raises(SchemaError, match="subtasks"):
            parse_think_subtasks(text)

    def test_primitive_without_action(self):
        text = '```json\n{"think":"t","subtasks":[{"id":"s1","desc":"d","primitive":true}]}\n```'
        with pytest.raises(SchemaError, match="action"):
            parse_think_subtasks(text)

    def test_subtask_missing_id(self):
        text = '```json\n{"think":"t","subtasks":[{"desc":"d","primitive":false}]}\n```'
        with pytest.raises(SchemaError, match="id"):
            parse_think_subtasks(text)

    def test_truncated_json(self):
        text = '```json\n{"think": "ok", "subtasks": ['
        with pytest.raises(SchemaError):
            parse_think_subtasks(text)

    def test_wrong_fenced_lang_still_parses(self):
        text = '```python\n{"think":"ok","subtasks":[]}\n```'
        # No fenced-json match, but balanced-brace fallback should work
        result = parse_think_subtasks(text)
        assert result.think == "ok"

    def test_prose_around_valid_json(self):
        text = 'Here is my response: {"think":"t","subtasks":[]} done.'
        result = parse_think_subtasks(text)
        assert result.think == "t"


# ---------------------------------------------------------------------------
# Retry path
# ---------------------------------------------------------------------------

VALID_RESPONSE = '```json\n{"think":"retry worked","subtasks":[]}\n```'
INVALID_RESPONSE = "not json at all"


class TestRetryPath:
    def test_retry_called_on_first_failure(self):
        calls = []
        def retry_fn(msg):
            calls.append(msg)
            return VALID_RESPONSE
        result = parse_think_subtasks(INVALID_RESPONSE, retry_fn=retry_fn)
        assert len(calls) == 1
        assert "JSON" in calls[0]  # re-prompt message
        assert result.think == "retry worked"

    def test_retry_raises_on_second_failure(self):
        """Retry path itself fails — must raise SchemaError, not retry again."""
        def retry_fn(msg):
            return "still not json"
        with pytest.raises(SchemaError):
            parse_think_subtasks(INVALID_RESPONSE, retry_fn=retry_fn)

    def test_retry_not_called_when_first_succeeds(self):
        calls = []
        def retry_fn(msg):
            calls.append(msg)
            return ""
        parse_think_subtasks(VALID_JSON, retry_fn=retry_fn)
        assert calls == []

    def test_is_retry_flag_prevents_third_call(self):
        """Calling parse with _is_retry=True on bad input raises immediately."""
        with pytest.raises(SchemaError):
            parse_think_subtasks(INVALID_RESPONSE, _is_retry=True)

    def test_retry_fn_none_raises_on_first_failure(self):
        with pytest.raises(SchemaError):
            parse_think_subtasks(INVALID_RESPONSE, retry_fn=None)
