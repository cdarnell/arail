"""ScriptedRouter — deterministic LLM stub for ReCAP unit tests.

Maps prompt prefix strings to queued canned response strings.
Raises ``AssertionError`` if a prompt arrives that matches no prefix,
or if the queue for a matched prefix is exhausted.  This makes tests
fail loudly when prompt structure drifts rather than silently using
wrong responses.

Usage::

    router = ScriptedRouter({
        "You are starting": [valid_json_1, valid_json_2],
        "You are decomposing": [valid_json_child],
    })
    adapter = RouterAdapter(router)
    text = adapter.chat(messages)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional


@dataclass
class _FakeResponse:
    text: str
    backend: str = "scripted"
    model: str = "scripted"
    tokens_used: int = 10
    latency_ms: float = 1.0


class ScriptedRouter:
    """Drop-in replacement for ModelRouter with scripted responses.

    Args:
        responses:  Mapping from prompt-substring (not full text) to a
                    list of response strings.  The first matching key
                    (in insertion order) wins.  Responses are consumed
                    FIFO from the queue.
        fallback:   If set, used for any prompt that matches no key
                    instead of raising.  Useful for ''always succeed''
                    stubs that don't care about prompt content.
    """

    def __init__(
        self,
        responses: Dict[str, List[str]],
        fallback: Optional[str] = None,
    ) -> None:
        self._queues: Dict[str, Deque[str]] = {
            key: deque(val) for key, val in responses.items()
        }
        self._fallback = fallback
        self.calls: List[str] = []  # record of prompts received

    def complete(self, prompt: str, **kwargs: Any) -> _FakeResponse:  # noqa: ARG002
        self.calls.append(prompt)
        for key, queue in self._queues.items():
            if key in prompt:
                if not queue:
                    raise AssertionError(
                        f"ScriptedRouter queue exhausted for key {key!r}. "
                        f"Prompt (first 200 chars): {prompt[:200]!r}"
                    )
                return _FakeResponse(text=queue.popleft())
        if self._fallback is not None:
            return _FakeResponse(text=self._fallback)
        raise AssertionError(
            f"ScriptedRouter: no matching key for prompt "
            f"(first 200 chars): {prompt[:200]!r}\n"
            f"Registered keys: {list(self._queues)}"
        )

    def health_check(self) -> Dict[str, bool]:
        return {"scripted": True}


# ---------------------------------------------------------------------------
# Canned JSON helpers
# ---------------------------------------------------------------------------

def make_plan_json(subtasks: List[Dict[str, Any]], think: str = "ok") -> str:
    """Return a fenced-JSON string suitable for parse_think_subtasks."""
    import json
    data = {"think": think, "subtasks": subtasks}
    return f"```json\n{json.dumps(data)}\n```"


def primitive(id: str, desc: str, action: str) -> Dict[str, Any]:
    return {"id": id, "desc": desc, "primitive": True, "action": action}


def nonprimitive(id: str, desc: str) -> Dict[str, Any]:
    return {"id": id, "desc": desc, "primitive": False}


def empty_plan(think: str = "nothing to do") -> str:
    return make_plan_json([], think=think)
