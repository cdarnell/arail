"""Environment abstraction for ReCAP (Sprint 1).

Defines the Protocol that any environment must satisfy, plus the
Action and Observation value types used throughout the recap module.

Sprint 2 will add a ResearcherEnvironment that wraps the Researcher
pipeline stages — only the Protocol shape needs to accommodate that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, Tuple, runtime_checkable


@dataclass(frozen=True)
class Action:
    """A single primitive action to execute in the environment.

    ``verb`` is a short uppercase command string (e.g. ``"PICK"``).
    ``args`` is an ordered tuple of string arguments.
    ``raw`` is the unparsed string from the subtask ``action`` field;
    kept for logging.
    """

    verb: str
    args: Tuple[str, ...] = field(default_factory=tuple)
    raw: str = ""

    @classmethod
    def from_subtask(cls, subtask: Any) -> "Action":
        """Build an Action from a parsed subtask dict or object.

        Accepts either a dict with an ``action`` key or an object
        with an ``action`` attribute.  Parses ``VERB(arg1, arg2)``
        syntax; falls back to the whole string as the verb.
        """
        if isinstance(subtask, dict):
            raw = subtask.get("action", "")
        else:
            raw = getattr(subtask, "action", "")
        raw = raw.strip()
        if "(" in raw and raw.endswith(")"):
            verb, rest = raw.split("(", 1)
            args_str = rest[:-1]  # strip trailing ")"
            args = tuple(a.strip() for a in args_str.split(",") if a.strip())
        else:
            verb = raw
            args = ()
        return cls(verb=verb.upper(), args=args, raw=raw)


@dataclass(frozen=True)
class Observation:
    """The result of executing an action (or resetting an environment).

    ``text``   — human-readable description of what happened.
    ``failed`` — True when the action was rejected or caused an error.
    ``info``   — optional structured metadata from the environment.
    """

    text: str
    failed: bool = False
    info: Optional[Dict[str, Any]] = None


@runtime_checkable
class Environment(Protocol):
    """Protocol that all ReCAP environments must satisfy.

    Implementations:
    - ``fixtures.robotouille_mock.RobotouilleEnv``  (Sprint 1)
    - ``researcher_env.ResearcherEnvironment``      (Sprint 2)
    """

    def reset(self) -> Observation:
        """Reset to initial state; return the initial observation."""
        ...

    def step(self, action: Action) -> Observation:
        """Apply ``action``; return the resulting observation."""
        ...

    def is_terminal(self) -> bool:
        """True when the episode is over (success or permanent failure)."""
        ...

    def score(self) -> Optional[float]:
        """Episode score in [0, 1], or None if not yet computable."""
        ...
