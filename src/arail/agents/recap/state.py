"""ContextNode, ContextTree, sliding-window, §A truncation.

Paper references:
  §2.1  ContextNode (T, S) semantics
  §2.4  Sliding window K=64 over chat-message history
  §A    Truncation policy: keep entry 0, drop entries 2–3, re-emit reminder

StateEntry tuples:
  ("act",          subtask_dict, Observation)  — primitive step executed
  ("child_return", subtask_id,   summary_str)  — child node completed
  ("note",         text)                        — free-form annotation
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

from arail.agents.recap.prompts import PERIODIC_RULE_REMINDER

# The "pinned" system/rules message is always index 0 in history.
_PINNED_INDEX = 0

# Default sliding-window size (paper §2.4).
WINDOW_K: int = 64

# Periodic rule reminder is re-inserted after truncation (§A).
_REMINDER_MESSAGE: Dict[str, str] = {
    "role": "system",
    "content": PERIODIC_RULE_REMINDER,
}

# Type alias for state entries
StateEntry = Tuple[Any, ...]


# ---------------------------------------------------------------------------
# ContextNode
# ---------------------------------------------------------------------------
@dataclass
class ContextNode:
    """A single node in the ReCAP context tree.

    ``T`` is the task description; ``S`` is the accumulated state
    (list of StateEntry tuples).  ``history`` is the raw list of
    chat-message dicts for this node; the adapter windows it before
    each LLM call.
    """

    T: str
    S: List[StateEntry] = field(default_factory=list)
    parent: Optional["ContextNode"] = field(default=None, repr=False)
    children: List["ContextNode"] = field(default_factory=list, repr=False)
    depth: int = 0
    retries: int = 0
    plan: Any = None  # ThinkSubtasks | None — set after first LLM call
    history: List[Dict[str, Any]] = field(default_factory=list, repr=False)

    def add_child(self, child: "ContextNode") -> None:
        child.parent = self
        self.children.append(child)

    def serialize(self) -> Dict[str, Any]:
        """Return a JSON-serialisable dict for debug/logging."""
        return {
            "T": self.T,
            "depth": self.depth,
            "retries": self.retries,
            "state_entries": len(self.S),
            "history_len": len(self.history),
            "children": [c.serialize() for c in self.children],
        }


# ---------------------------------------------------------------------------
# ContextTree
# ---------------------------------------------------------------------------
class ContextTree:
    """Thin wrapper around the root ContextNode."""

    def __init__(self, root: ContextNode) -> None:
        self.root = root
        self._all: List[ContextNode] = [root]
        self._created_at: float = time.time()

    def add(self, node: ContextNode) -> None:
        self._all.append(node)

    def __iter__(self) -> Iterator[ContextNode]:
        return iter(self._all)

    def __len__(self) -> int:
        return len(self._all)

    def serialize_for_debug(self) -> str:
        """Return JSON string of the full tree for debug output."""
        return json.dumps(
            {
                "created_at": self._created_at,
                "node_count": len(self._all),
                "tree": self.root.serialize(),
            },
            indent=2,
        )


# ---------------------------------------------------------------------------
# Sliding-window  (paper §2.4)
# ---------------------------------------------------------------------------
def window(history: List[Dict[str, Any]], k: int = WINDOW_K) -> List[Dict[str, Any]]:
    """Return the windowed view of ``history`` for LLM consumption.

    Invariant: ``result[0] is history[0]`` always (pinned system/rules).
    Of the remaining entries, keep only the most recent ``k-1``.

    If ``len(history) == 0`` returns [].
    If ``k == 0`` treats it as k=1 (only pinned entry).
    """
    if not history:
        return []
    effective_k = max(k, 1)
    pinned = history[_PINNED_INDEX]
    tail = history[1:]  # everything after the pinned entry
    if len(tail) <= effective_k - 1:
        return history[:]
    # Keep only the most recent (effective_k - 1) tail entries.
    # When effective_k == 1, tail_k == 0 so we return only the pinned entry.
    tail_k = effective_k - 1
    if tail_k == 0:
        return [pinned]
    return [pinned] + tail[-tail_k:]


# ---------------------------------------------------------------------------
# §A truncation policy
# ---------------------------------------------------------------------------
def truncate_for_context(
    history: List[Dict[str, Any]],
    max_chars: int,
    *,
    flatten_fn=None,
) -> List[Dict[str, Any]]:
    """Apply the §A truncation policy to bring the flattened prompt under
    ``max_chars``.

    Policy (§A):
    1. Keep entry 0 (system rules / initial decomp summary) always.
    2. Drop entries at indices 2 and 3 (earliest non-pinned context).
    3. Re-insert the periodic rule reminder at the end.
    4. If still over budget, keep dropping oldest non-pinned entries
       (index 1 onward) until under budget or only the pinned entry
       remains.

    ``flatten_fn`` is used to estimate character count; if None we
    estimate by summing ``len(entry["content"])`` for all entries.
    """
    def _size(msgs: List[Dict[str, Any]]) -> int:
        if flatten_fn:
            return len(flatten_fn(msgs))
        return sum(len(m.get("content", "")) for m in msgs)

    result = list(history)

    if _size(result) <= max_chars:
        return result

    # Step 1: already keeping index 0.
    # Step 2: drop indices 2–3 if they exist (1-indexed after pinned).
    # In 0-indexed list: indices 2 and 3.
    drop_indices = {2, 3}
    result = [m for i, m in enumerate(result) if i not in drop_indices]

    # Step 3: re-append the periodic rule reminder
    result.append(_REMINDER_MESSAGE.copy())

    if _size(result) <= max_chars:
        return result

    # Step 4: iteratively drop oldest non-pinned entries (index 1).
    # The last entry is the periodic rule reminder; protect it by popping
    # from index 1 (oldest non-pinned), not from the end.
    while len(result) > 2 and _size(result) > max_chars:
        result.pop(1)

    return result
