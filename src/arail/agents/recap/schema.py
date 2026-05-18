"""JSON schema contract for ReCAP LLM responses.

The LLM must emit (inside a ```json``` fenced block):

    {
      "think": "free-text reasoning",
      "subtasks": [
        {"id": "s1", "desc": "...", "primitive": true,  "action": "OPEN(door_1)"},
        {"id": "s2", "desc": "...", "primitive": false}
      ]
    }

``parse_think_subtasks`` extracts and validates this shape.

On first ``ValidationError``: emits one re-prompt and retries via
the supplied ``retry_fn``.  On a second failure: raises ``SchemaError``.
The caller must NOT call this function again recursively from the
retry path — ``_parse_internal`` carries a ``_is_retry`` flag that
converts a second failure directly into ``SchemaError``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class SchemaError(Exception):
    """Raised when the LLM response could not be parsed into a valid plan."""


@dataclass
class Subtask:
    id: str
    desc: str
    primitive: bool
    action: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"id": self.id, "desc": self.desc, "primitive": self.primitive}
        if self.primitive:
            d["action"] = self.action
        return d


@dataclass
class ThinkSubtasks:
    think: str
    subtasks: List[Subtask] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "think": self.think,
            "subtasks": [s.to_dict() for s in self.subtasks],
        }


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def _validate(data: Dict[str, Any]) -> ThinkSubtasks:
    """Validate a parsed dict against the schema; raise SchemaError on failure."""
    if not isinstance(data, dict):
        raise SchemaError("Response is not a JSON object")
    if "think" not in data:
        raise SchemaError("Missing required field 'think'")
    if "subtasks" not in data:
        raise SchemaError("Missing required field 'subtasks'")
    if not isinstance(data["subtasks"], list):
        raise SchemaError("'subtasks' must be a list")

    subtasks: List[Subtask] = []
    for i, item in enumerate(data["subtasks"]):
        if not isinstance(item, dict):
            raise SchemaError(f"subtask[{i}] is not an object")
        for req in ("id", "desc", "primitive"):
            if req not in item:
                raise SchemaError(f"subtask[{i}] missing required field '{req}'")
        if not isinstance(item["primitive"], bool):
            raise SchemaError(f"subtask[{i}].primitive must be bool")
        action = item.get("action", "")
        if item["primitive"] and not action:
            raise SchemaError(
                f"subtask[{i}] is primitive but missing 'action'"
            )
        subtasks.append(Subtask(
            id=str(item["id"]),
            desc=str(item["desc"]),
            primitive=bool(item["primitive"]),
            action=str(action),
        ))

    return ThinkSubtasks(think=str(data["think"]), subtasks=subtasks)


# ---------------------------------------------------------------------------
# JSON extraction from text
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Optional[str]:
    """Extract a JSON string from the LLM response.

    Strategy:
    1. Look for a ```json fenced block.
    2. Fall back to scanning for the first balanced {...}.
    """
    # Strategy 1: fenced block
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)

    # Strategy 2: first balanced brace pair
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


# ---------------------------------------------------------------------------
# Public parse function
# ---------------------------------------------------------------------------
_RE_PROMPT_TEXT = (
    "Your last response did not match the required JSON shape. "
    "Re-emit only the JSON object."
)


def parse_think_subtasks(
    text: str,
    retry_fn: Optional[Callable[[str], str]] = None,
    *,
    _is_retry: bool = False,
) -> ThinkSubtasks:
    """Parse and validate the LLM response text into a ``ThinkSubtasks``.

    Args:
        text:      Raw LLM response string.
        retry_fn:  Optional callable ``(re_prompt: str) -> str`` that
                   issues a re-prompt and returns the new response.
                   Used for the single retry path.
        _is_retry: Internal flag; do NOT set from outside.  When True,
                   any validation failure raises ``SchemaError``
                   immediately (no further retry).

    Returns:
        ``ThinkSubtasks`` on success.

    Raises:
        ``SchemaError`` if parsing fails after one retry (or on first
        failure when ``retry_fn`` is None).
    """
    raw_json = _extract_json(text)
    if raw_json is None:
        err_msg = "No JSON object found in LLM response"
        logger.warning("prompt_trace schema_error: %s", err_msg)
        parse_error: Optional[Exception] = SchemaError(err_msg)
        data = None
    else:
        try:
            data = json.loads(raw_json)
            parse_error = None
        except json.JSONDecodeError as exc:
            err_msg = f"JSON decode error: {exc}"
            logger.warning("prompt_trace schema_error: %s", err_msg)
            parse_error = SchemaError(err_msg)
            data = None

    if parse_error is None and data is not None:
        try:
            return _validate(data)
        except SchemaError as exc:
            err_msg = str(exc)
            logger.warning("prompt_trace schema_error validation: %s", err_msg)
            parse_error = exc

    # At this point we have a parse_error.
    if _is_retry:
        # Already in retry path — raise immediately.
        raise SchemaError(str(parse_error))

    if retry_fn is None:
        raise SchemaError(str(parse_error))

    # Issue exactly one re-prompt.
    retry_response = retry_fn(_RE_PROMPT_TEXT)
    return parse_think_subtasks(retry_response, retry_fn=None, _is_retry=True)
