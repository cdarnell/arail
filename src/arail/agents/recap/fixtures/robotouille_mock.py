"""Robotouille-shaped deterministic mock environment for ReCAP tests.

This is NOT a real Robotouille integration — it replicates the action/
observation shape described in the paper so tests can run without any
external dependencies.

Goal: "cook a burger and serve it" — solvable in 12-18 steps.

Action verbs: PICK, PLACE, COOK, CHOP, SERVE, OPEN, CLOSE, INSPECT.

Inject failures via ``inject_failures=[{"at_step": N, "mode": "..."}]``
where mode is one of:
  - ``"invalid_action"``   — the action is rejected with a failure obs.
  - ``"resource_missing"`` — the required resource is unavailable.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from arail.agents.recap.environment import Action, Observation


# ---------------------------------------------------------------------------
# Recipe state machine
# ---------------------------------------------------------------------------
_RECIPE_STEPS = [
    # (required_verb, required_arg, result_state_flag)
    ("OPEN",    "fridge",    "fridge_open"),
    ("PICK",    "patty",     "have_patty"),
    ("CLOSE",   "fridge",    "fridge_closed"),
    ("PLACE",   "grill",     "patty_on_grill"),
    ("COOK",    "patty",     "patty_cooked"),
    ("PICK",    "bun",       "have_bun"),
    ("CHOP",    "lettuce",   "lettuce_chopped"),
    ("PLACE",   "plate",     "assembly_started"),
    ("INSPECT", "plate",     "assembly_ok"),
    ("SERVE",   "customer",  "served"),
]

_TERMINAL_FLAG = "served"


@dataclass
class FailureSpec:
    at_step: int
    mode: str  # "invalid_action" | "resource_missing"
    _fired: bool = field(default=False, init=False)


class RobotouilleEnv:
    """Deterministic burger-making mock environment.

    Args:
        seed: random seed (unused now, reserved for future stochastic mode).
        inject_failures: list of dicts with keys ``at_step`` and ``mode``.
    """

    def __init__(
        self,
        seed: int = 0,
        inject_failures: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._rng = random.Random(seed)
        self._failures: List[FailureSpec] = []
        if inject_failures:
            for spec in inject_failures:
                self._failures.append(
                    FailureSpec(at_step=spec["at_step"], mode=spec["mode"])
                )
        self._step_count: int = 0
        self._flags: Dict[str, bool] = {}
        self._done: bool = False

    # ------------------------------------------------------------------
    def reset(self) -> Observation:
        self._step_count = 0
        self._flags = {}
        self._done = False
        return Observation(
            text=(
                "Kitchen ready. Fridge contains patty and bun. "
                "Grill is cold. Lettuce on counter."
            ),
            failed=False,
        )

    # ------------------------------------------------------------------
    def step(self, action: Action) -> Observation:
        if self._done:
            return Observation(
                text="Episode already finished.", failed=True
            )

        # Check for injected failure at this step
        for spec in self._failures:
            if spec.at_step == self._step_count and not spec._fired:
                spec._fired = True
                self._step_count += 1
                if spec.mode == "invalid_action":
                    return Observation(
                        text=f"Invalid action: {action.raw!r} not allowed here.",
                        failed=True,
                        info={"mode": "invalid_action", "step": self._step_count - 1},
                    )
                if spec.mode == "resource_missing":
                    return Observation(
                        text=(
                            f"Resource missing: cannot execute {action.raw!r} "
                            "because a required item is unavailable."
                        ),
                        failed=True,
                        info={"mode": "resource_missing", "step": self._step_count - 1},
                    )

        # Find the matching recipe step
        obs = self._dispatch(action)
        self._step_count += 1

        if self._flags.get(_TERMINAL_FLAG):
            self._done = True

        return obs

    # ------------------------------------------------------------------
    def _dispatch(self, action: Action) -> Observation:
        """Try to advance the recipe; return descriptive observation."""
        verb = action.verb.upper()
        arg = action.args[0].lower() if action.args else ""

        # Check recipe order
        for step_verb, step_arg, flag in _RECIPE_STEPS:
            if step_verb == verb and step_arg in arg:
                if self._flags.get(flag):
                    return Observation(
                        text=f"{step_verb}({step_arg}) already done.",
                        failed=False,
                        info={"flag": flag, "already": True},
                    )
                # Check prerequisites
                prereq_ok, prereq_msg = self._check_prereqs(flag)
                if not prereq_ok:
                    return Observation(
                        text=f"Cannot {step_verb} {step_arg}: {prereq_msg}",
                        failed=True,
                        info={"flag": flag, "prereq": prereq_msg},
                    )
                self._flags[flag] = True
                return Observation(
                    text=f"Done: {step_verb}({step_arg}). State updated.",
                    failed=False,
                    info={"flag": flag},
                )

        # Unknown action — not a hard failure, just informative
        return Observation(
            text=f"Action {verb}({arg!r}) has no effect right now.",
            failed=False,
            info={"unrecognized": True},
        )

    # ------------------------------------------------------------------
    _PREREQS: Dict[str, List[str]] = {
        "have_patty":        ["fridge_open"],
        "fridge_closed":     ["fridge_open"],
        "patty_on_grill":    ["have_patty"],
        "patty_cooked":      ["patty_on_grill"],
        "assembly_started":  ["patty_cooked", "have_bun"],
        "assembly_ok":       ["assembly_started", "lettuce_chopped"],
        "served":            ["assembly_ok"],
    }

    def _check_prereqs(self, flag: str):
        for prereq in self._PREREQS.get(flag, []):
            if not self._flags.get(prereq):
                return False, f"prerequisite '{prereq}' not met"
        return True, ""

    # ------------------------------------------------------------------
    def is_terminal(self) -> bool:
        return self._done

    def score(self) -> Optional[float]:
        if self._flags.get(_TERMINAL_FLAG):
            return 1.0
        # Partial credit: fraction of recipe flags achieved
        achieved = sum(1 for _, _, f in _RECIPE_STEPS if self._flags.get(f))
        return round(achieved / len(_RECIPE_STEPS), 2)

    @property
    def step_count(self) -> int:
        return self._step_count


# ---------------------------------------------------------------------------
# Factory function used by tests
# ---------------------------------------------------------------------------
def make_env(
    seed: int = 0,
    inject_failures: Optional[List[Dict[str, Any]]] = None,
) -> RobotouilleEnv:
    """Create a fresh RobotouilleEnv, optionally with injected failures."""
    return RobotouilleEnv(seed=seed, inject_failures=inject_failures)
