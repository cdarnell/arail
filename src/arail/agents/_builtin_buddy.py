"""Buddy — ARAIL's actively helpful lab partner.

    An agent is a loop that notices things and speaks up.

That's the whole mental model. Buddy is the personality agent that
ships with ARAIL — observant like an old-school pair-programming
buddy AND proactive about the user's current goal: pointing at
techniques to try, items worth reviewing, or research worth running.

Five pieces hang off the loop:

    1. Personality  — who Buddy is (NAME, EMOJI, SYSTEM_PROMPT)
    2. Watchers     — observe lab state (WATCHERS, reactive)
    3. Suggesters   — propose goal-aware actions (SUGGESTERS, proactive)
    4. Speech       — turn a fact into a sentence (_voice, _compose_prompt)
    5. Memory       — cooldowns + dreams (state.json, dream())

The loop in BuddyAgent._run runs two cadences. Every interval tick
(default 90s) it polls WATCHERS — the same passive-observation loop
that shipped as Pip. Every suggestion interval (default 15 min) and
only when a goal is active, it polls SUGGESTERS for goal-anchored
proposals. Reactive observations and goal-aware suggestions share
the same global cooldown so Buddy never double-talks.

New to agents? Start at docs/agents-explained.md, then come back.
Already know? Jump to BuddyAgent._maybe_speak / _maybe_suggest at
the bottom — those two functions are the ones that actually emit;
everything above is the pieces they call.

Design rules Buddy lives by:

    - One sentence at a time. Never paragraphs.
    - Active without being naggy. 5-min global cooldown shared
      across watchers and suggesters; per-target cooldowns layered
      on top so the same skill / experiment / phase nudge isn't
      reissued every tick. Silence is a valid choice.
    - Voice-shaped, not scripted. Every utterance goes through the
      local model with the personality prompt. Change the prompt,
      Buddy sounds different. That's the whole extension point for
      forging new personality agents.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from arail.activity import activity_log
from arail.agent_workflows import update_agent_workflow


# ── Where memory lives ───────────────────────────────────────────────
# state.json holds cooldowns + counts across restarts. Same path
# whether we're the PKB copy or the builtin fallback — so "wipe the
# PKB" genuinely wipes Buddy's memory.

def _state_file() -> Path:
    from arail.pkb import _pkb_root
    return _pkb_root() / "agents" / "buddy" / "state.json"


# ══════════════════════════════════════════════════════════════════════
#  1. PERSONALITY — who Buddy is
# ══════════════════════════════════════════════════════════════════════
# Three strings. Change them, Buddy changes. The Agent Forge generates
# this block from a form field.

NAME = "Buddy"
EMOJI = "🐧"

# The voice. A touch longer than passive Pip — Buddy needs space for
# action verbs ("Worth a look:", "Try the X skill:", "Run a sweep…").
# ~50 words is the sweet spot for local models given the active
# framing.
SYSTEM_PROMPT = (
    "You are Buddy, ARAIL's warm, observant, and actively helpful "
    "lab partner. You speak in one short sentence. You notice things "
    "and say them plainly, but you also point at techniques to try, "
    "items worth reviewing, or research worth running — always tied "
    "to the user's current goal. You're helpful without being "
    "preachy. You never use emojis or markdown. You never say 'I' — "
    "you just name what matters. Keep it under 25 words."
)


# ══════════════════════════════════════════════════════════════════════
#  2. OBSERVATIONS — what Buddy notices or proposes
# ══════════════════════════════════════════════════════════════════════
# An Observation is a fact Buddy might say. Watchers and suggesters
# both produce them; the loop picks the juiciest one per cadence and
# emits it. Observations are the raw material — the text isn't
# polished yet.

@dataclass
class Observation:
    """One thing Buddy might say. Will be paraphrased through the
    local model before it gets emitted."""

    watcher: str            # which watcher / suggester fired (for cooldowns)
    severity: str           # "praise" | "info" | "warn" | "suggest"
    fact: str               # plain-English fact; Buddy rephrases this
    cooldown_sec: int = 30 * 60  # 30 min default — no repeats
    suggestion: Optional[Dict[str, Any]] = None  # structured action payload

    def rank(self) -> int:
        """Higher rank wins when multiple observations land in one tick."""
        return {"praise": 3, "warn": 2, "info": 1, "suggest": 1}.get(
            self.severity, 0
        )


# ══════════════════════════════════════════════════════════════════════
#  3a. WATCHERS — reactive observation
# ══════════════════════════════════════════════════════════════════════
# One watcher = one opinion about the lab right now. Each returns an
# Observation when it sees something or None when it's quiet. Add a
# function + register it in WATCHERS and Buddy learns to notice a new
# thing. That's the whole reactive extension mechanism.
#
# Rules: fast (no network), independent (no shared state), honest
# (raise? nope, return None). Thresholds live inside each function
# so you can tune them without a central config.

def _watch_gpu_memory() -> Optional[Observation]:
    """Fires when RAM is very hot (proxy for GPU on unified-memory Macs).

    We don't have a dedicated GPU-memory check on every platform; RAM
    pressure is a reasonable proxy because loading a 16 GB model shows
    up in virtual_memory() regardless of the accelerator.
    """
    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError:
        return None
    pct = psutil.virtual_memory().percent
    if pct >= 92:
        return Observation(
            watcher="gpu",
            severity="warn",
            fact=f"RAM is at {pct:.0f}%. If a deep model is loaded, it's "
                 f"about to swap or crash.",
            cooldown_sec=20 * 60,
        )
    return None


def _watch_inbox_pileup() -> Optional[Observation]:
    """Fires when the PKB inbox has several unread files that have been
    sitting there a while. Gentle nudge to ingest or clear."""
    try:
        from arail.pkb import _pkb_root
    except Exception:
        return None
    inbox = _pkb_root() / "inbox"
    if not inbox.exists():
        return None
    now = time.time()
    stale = [
        p for p in inbox.iterdir()
        if p.is_file()
        and not p.name.startswith(".")
        and (now - p.stat().st_mtime) > 6 * 3600  # 6h old
    ]
    if len(stale) >= 3:
        return Observation(
            watcher="inbox",
            severity="info",
            fact=f"There are {len(stale)} files in the PKB inbox that "
                 f"have been sitting unread for over 6 hours.",
            cooldown_sec=4 * 3600,  # 4h — inbox stuff isn't urgent
        )
    return None


def _watch_researcher_wins() -> Optional[Observation]:
    """Celebrates when an experiment recently landed 'supported'.
    Buddy notices good news too — this is the dopamine-loop half of
    the job."""
    try:
        from arail.skills.experiment_tracker import ExperimentTracker
    except Exception:
        return None
    tracker = ExperimentTracker()
    recent = [
        e for e in tracker.list_all()
        if e.get("status") == "completed"
        and e.get("hypothesis_supported") is True
        and e.get("end_date")
    ]
    if not recent:
        return None
    latest = recent[-1]
    end = latest.get("end_date") or ""
    try:
        import datetime
        parsed = datetime.date.fromisoformat(end)
        today = datetime.date.today()
        if (today - parsed).days > 0:
            return None
    except Exception:
        return None
    return Observation(
        watcher="researcher-win",
        severity="praise",
        fact=f"Experiment {latest.get('id', '?')} just landed "
             f"'supported': {latest.get('hypothesis', '')[:80]}.",
        cooldown_sec=3 * 3600,  # don't over-celebrate the same win
    )


def _watch_researcher_plateau() -> Optional[Observation]:
    """Fires when the last several experiments reached the same
    verdict. Suggests a pivot — the research angle is saturated."""
    try:
        from arail.skills.experiment_tracker import ExperimentTracker
    except Exception:
        return None
    tracker = ExperimentTracker()
    completed = [
        e for e in tracker.list_all() if e.get("status") == "completed"
    ]
    if len(completed) < 4:
        return None
    last_four = completed[-4:]
    verdicts = {e.get("hypothesis_supported") for e in last_four}
    if len(verdicts) == 1 and next(iter(verdicts)) is not None:
        kind = "all supported" if next(iter(verdicts)) else "all falsified"
        return Observation(
            watcher="plateau",
            severity="info",
            fact=f"The last four experiments all came back {kind}. "
                 f"Might be time to sharpen the question or pivot domains.",
            cooldown_sec=2 * 3600,
        )
    return None


# Registry — add a function here, Buddy starts watching for it on the
# next tick. That's the whole reactive extension mechanism.
WATCHERS: List[Callable[[], Optional[Observation]]] = [
    _watch_gpu_memory,
    _watch_inbox_pileup,
    _watch_researcher_wins,
    _watch_researcher_plateau,
]


# ══════════════════════════════════════════════════════════════════════
#  3b. SUGGESTERS — proactive, goal-anchored
# ══════════════════════════════════════════════════════════════════════
# A suggester takes the current goal record and returns an Observation
# proposing an action — a technique to try, an item to review, an
# experiment worth running, or a phase nudge. They run on a slower
# cadence than watchers (default 15 min) and only when a goal is set.
#
# Every suggester is read-only. Failures are silent — a broken
# suggester never silences Buddy as a whole. Network calls are
# avoided so the suggestion tick doesn't stall the event loop.

# Skills tagged with one of these domains apply to every goal.
_DOMAIN_AGNOSTIC = {"general", "meta"}


def _goal_domain(goal: Dict[str, Any]) -> str:
    """Pull the parsed domain out of a goal record. Falls back to ''
    when the goal hasn't been parsed yet."""
    parsed = goal.get("parsed") or {}
    return str(parsed.get("domain") or "").strip().lower()


def _suggest_skill_for_goal(goal: Dict[str, Any]) -> Optional[Observation]:
    """Surface an installed skill whose domain matches the goal's.

    Per-skill cooldown via the watcher name (``skill:<id>``) means
    Buddy rotates through every matching skill before going quiet on
    the technique-suggestion front.
    """
    try:
        from arail.skills_loader import list_installed_skills
    except Exception:
        return None
    domain = _goal_domain(goal)
    skills = list_installed_skills()
    matches = [
        s for s in skills
        if (s.domain or "").lower() == domain
        or (s.domain or "").lower() in _DOMAIN_AGNOSTIC
    ]
    if not matches:
        return None
    # Sort by id so per-target cooldown rotates deterministically:
    # the alphabetically-first uncooled skill wins each tick.
    matches.sort(key=lambda s: s.id)
    skill = matches[0]
    return Observation(
        watcher=f"skill:{skill.id}",
        severity="suggest",
        fact=f"Worth a look: skill '{skill.name}' fits this goal — "
             f"open lab/pkb/skills/{skill.id}/SKILL.md.",
        cooldown_sec=6 * 3600,
        suggestion={
            "kind": "skill",
            "target": skill.id,
            "link": f"/knowledge/skills/{skill.id}",
        },
    )


def _suggest_pending_review(goal: Dict[str, Any]) -> Optional[Observation]:
    """Flag a completed experiment that has been sitting > 48h."""
    try:
        from arail.skills.experiment_tracker import ExperimentTracker
    except Exception:
        return None
    tracker = ExperimentTracker()
    try:
        all_exps = tracker.list_all()
    except Exception:
        return None
    completed = [
        e for e in all_exps
        if e.get("status") == "completed"
        and e.get("hypothesis_supported") is not None
        and e.get("end_date")
    ]
    if not completed:
        return None
    import datetime
    today = datetime.date.today()
    stale: List[Tuple[int, Dict[str, Any]]] = []
    for exp in completed:
        try:
            end_d = datetime.date.fromisoformat(str(exp.get("end_date", "")))
        except Exception:
            continue
        age_days = (today - end_d).days
        if age_days >= 2:
            stale.append((age_days, exp))
    if not stale:
        return None
    # Oldest first — give the user a chance to clear the queue.
    stale.sort(key=lambda pair: pair[0], reverse=True)
    age, exp = stale[0]
    exp_id = str(exp.get("id", "?"))
    hyp = (exp.get("hypothesis") or "")[:60]
    verdict = "supported" if exp.get("hypothesis_supported") else "falsified"
    return Observation(
        watcher=f"review:{exp_id}",
        severity="suggest",
        fact=f"Experiment {exp_id} ({verdict}) closed {age} days ago "
             f"and hasn't been revisited: {hyp}.",
        cooldown_sec=24 * 3600,
        suggestion={
            "kind": "review",
            "target": exp_id,
            "link": f"/research/experiments/{exp_id}",
        },
    )


def _suggest_next_experiment(goal: Dict[str, Any]) -> Optional[Observation]:
    """Flag a concept in the goal that no logged experiment touches.

    Crude word-overlap heuristic: pull tokens of length ≥ 5 from each
    sub_objective, drop any that appear in any tracked experiment's
    hypothesis / methodology / variables blob, and propose the first
    miss as a worthwhile sweep.
    """
    try:
        from arail.skills.experiment_tracker import ExperimentTracker
    except Exception:
        return None
    parsed = goal.get("parsed") or {}
    sub_obj = parsed.get("sub_objectives") or []
    if not isinstance(sub_obj, list) or not sub_obj:
        return None

    tracker = ExperimentTracker()
    try:
        exps = tracker.list_all()
    except Exception:
        return None

    if not exps:
        # No experiments at all yet — encourage the very first one.
        first = str(sub_obj[0])[:80]
        return Observation(
            watcher="next:first",
            severity="suggest",
            fact=f"No experiments logged yet — '{first}' looks like a "
                 f"natural first run.",
            cooldown_sec=12 * 3600,
            suggestion={
                "kind": "experiment",
                "target": first,
                "link": "/research",
            },
        )

    haystack_parts: List[str] = []
    for e in exps:
        haystack_parts.append(str(e.get("hypothesis") or ""))
        haystack_parts.append(str(e.get("methodology") or ""))
        variables = e.get("variables") or []
        if isinstance(variables, list):
            haystack_parts.append(" ".join(str(v) for v in variables))
    haystack = " ".join(haystack_parts).lower()

    for sub in sub_obj:
        sub_text = str(sub)
        terms = [t.strip(".,;:()[]'\"") for t in sub_text.lower().split()
                 if len(t) >= 5]
        for term in terms:
            if term and term not in haystack:
                return Observation(
                    watcher=f"next:{term}",
                    severity="suggest",
                    fact=f"Goal mentions '{term}' but no experiment covers "
                         f"it yet — worth a sweep.",
                    cooldown_sec=12 * 3600,
                    suggestion={
                        "kind": "experiment",
                        "target": term,
                        "link": "/research",
                    },
                )
    return None


# Phase boundaries in the researcher pipeline (see arail.agents.researcher).
# Crossing one of these triggers a one-time nudge per goal-id.
_PHASE_THRESHOLDS: Tuple[Tuple[float, str, str], ...] = (
    (0.3, "experiments", "Experiment phase reached — sketch a hypothesis "
                          "before kicking off runs."),
    (0.5, "sources",     "Sources phase — review program.md and confirm the "
                          "research substrate looks right."),
    (0.7, "run",         "Runs are firing — keep an eye on the activity log "
                          "for early signal."),
    (0.9, "analyze",     "Analysis underway — line up the validation set "
                          "before the report drops."),
)


def _suggest_phase_action(goal: Dict[str, Any]) -> Optional[Observation]:
    """Nudge when researcher progress crosses a phase boundary.

    Watcher key is ``phase:<goal_id>:<phase>`` so each phase fires
    exactly once per goal — the 24h cooldown blocks duplicate fires
    well past any realistic phase duration.
    """
    progress = float(goal.get("progress") or 0.0)
    goal_id = str(goal.get("id") or "")
    if not goal_id:
        return None
    crossed: Optional[Tuple[float, str, str]] = None
    for thr, key, msg in _PHASE_THRESHOLDS:
        if progress >= thr:
            crossed = (thr, key, msg)
    if crossed is None:
        return None
    _, key, msg = crossed
    return Observation(
        watcher=f"phase:{goal_id}:{key}",
        severity="suggest",
        fact=msg,
        cooldown_sec=24 * 3600,
        suggestion={
            "kind": "phase",
            "target": key,
            "link": "/research",
        },
    )


# Registry — order is "user-relevance descending": phase nudges are
# tied to the goal lifecycle, reviews and skills are concrete
# breadcrumbs, the experiment-gap heuristic is most speculative.
SUGGESTERS: List[Callable[[Dict[str, Any]], Optional[Observation]]] = [
    _suggest_phase_action,
    _suggest_pending_review,
    _suggest_skill_for_goal,
    _suggest_next_experiment,
]


# ══════════════════════════════════════════════════════════════════════
#  4. SPEECH — turning a fact into a sentence
# ══════════════════════════════════════════════════════════════════════
# The magic step. _compose_prompt assembles the full prompt from four
# layers (voice, yesterday's dream, loaded skills, the fact) and
# _voice calls the local model to paraphrase. If the model is down,
# Buddy still speaks — just in the raw voice of the watcher.

def _compose_prompt(fact: str) -> str:
    """Build the full LLM prompt: base voice + skills + yesterday's
    dream + observation.

    All three context blocks load from disk on each call — small
    markdown files, negligible I/O, and the "edit a file, next
    utterance reflects the change" behavior is worth more than a
    microsecond of cache wisdom.
    """
    base = SYSTEM_PROMPT
    try:
        from arail.skills_loader import load_agent_skills, compose_system_context
        skills = load_agent_skills("buddy")
        skill_ctx = compose_system_context(skills)
    except Exception:
        skill_ctx = ""

    try:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dreams_dir = _state_file().parent / "dreams"
        dream_ctx = _load_yesterday_dream(dreams_dir, today)
    except Exception:
        dream_ctx = ""

    sections = [base]
    if dream_ctx:
        sections.append("# Yesterday you reflected\n" + dream_ctx)
    if skill_ctx:
        sections.append(skill_ctx)
    sections.append(f"Observation: {fact}")
    sections.append(f"{NAME}'s one-sentence note:")
    return "\n\n".join(sections)


def _voice(fact: str) -> str:
    """Paraphrase a fact through the local model in Buddy's voice."""
    try:
        from arail.router import ModelRouter
    except Exception:
        return fact
    try:
        router = ModelRouter()
    except Exception:
        return fact

    prompt = _compose_prompt(fact)
    try:
        response = router.complete(prompt, max_tokens=60, temperature=0.6)
        text = (response.text or "").strip()
        text = text.strip('"').strip("'")
        prefix = NAME.lower() + ":"
        if text.lower().startswith(prefix):
            text = text[len(prefix):].strip()
        if len(text) > 200:
            text = text[:197] + "…"
        return text or fact
    except Exception:
        return fact


# ══════════════════════════════════════════════════════════════════════
#  5. LOOP — the heartbeat
# ══════════════════════════════════════════════════════════════════════
# BuddyAgent is the whole agent wrapped as an asyncio task. Two
# cadences run off one timer: the reactive watcher poll happens every
# tick, the proactive suggestion poll happens every Nth tick (and
# only when a goal is active). _maybe_speak / _maybe_suggest share
# _emit so the cooldown bookkeeping is consistent.

class BuddyAgent:
    """Background task that ticks every LAB_BUDDY_INTERVAL_SEC and
    occasionally says something insightful — or actively helpful —
    in the activity feed."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._status = "idle"   # idle | running | paused
        self._last_said: Dict[str, float] = {}
        self._last_global: float = 0.0
        self._last_suggest_check: float = 0.0
        self._utterances: int = 0
        self._suggestions: int = 0
        self._recent_actions: List[str] = []

    @property
    def status(self) -> str:
        return self._status

    # ── Memory: short-term (state.json) ────────────────────────────
    # Load on start so cooldowns survive restarts (no spam-on-boot).
    # Save after every emit — file is tiny, I/O is negligible.
    # Delete the file or run `./arail reset pkb` to wipe this memory.

    def _load_state(self) -> None:
        path = _state_file()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            self._last_said = dict(data.get("last_said") or {})
            self._last_global = float(data.get("last_global") or 0.0)
            self._last_suggest_check = float(
                data.get("last_suggest_check") or 0.0
            )
            self._utterances = int(data.get("utterances") or 0)
            self._suggestions = int(data.get("suggestions") or 0)
        except Exception:
            # Corrupt state shouldn't block Buddy — start fresh.
            pass

    def _save_state(self) -> None:
        path = _state_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "last_said": self._last_said,
                "last_global": self._last_global,
                "last_suggest_check": self._last_suggest_check,
                "utterances": self._utterances,
                "suggestions": self._suggestions,
            }, indent=2))
        except OSError:
            pass  # read-only FS or permission issue — don't crash

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._load_state()
        self._status = "running"
        self._sync_workflow(
            "Watching lab signals",
            "Pair on the goal, surface what matters",
        )
        self._task = asyncio.create_task(self._run())
        activity_log.emit(
            "buddy",
            f"{EMOJI} {NAME} is online — observing and chiming in with "
            f"goal-aware ideas.",
            "info",
        )

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._status = "idle"
        self._sync_workflow("Offline", None)

    def _sync_workflow(self, current_task: str, next_step: Optional[str]) -> None:
        global_cooldown = max(60, int(os.getenv("LAB_BUDDY_GLOBAL_COOLDOWN_SEC", "300")))
        chatter_total = self._utterances + self._suggestions
        too_chatty = chatter_total >= 8 and global_cooldown < 180
        update_agent_workflow(
            "buddy",
            status=self._status,
            objective="Observe the lab and offer goal-aware suggestions",
            current_task=current_task,
            next_step=next_step,
            completed_steps=list(self._recent_actions[-5:]),
            paused=False,
            pause_reason=None,
            chatter={
                "utterances": self._utterances,
                "suggestions": self._suggestions,
                "global_cooldown_sec": global_cooldown,
                "too_chatty": too_chatty,
            },
            recent_actions=list(self._recent_actions[-3:]),
        )

    async def _run(self) -> None:
        interval = max(30, int(os.getenv("LAB_BUDDY_INTERVAL_SEC", "90")))
        global_cooldown = max(
            60, int(os.getenv("LAB_BUDDY_GLOBAL_COOLDOWN_SEC", "300"))
        )
        suggest_interval = max(
            180, int(os.getenv("LAB_BUDDY_SUGGEST_INTERVAL_SEC", "900"))
        )
        try:
            while True:
                await asyncio.sleep(interval)
                self._maybe_speak(global_cooldown)
                now = time.time()
                if now - self._last_suggest_check >= suggest_interval:
                    self._maybe_suggest(global_cooldown)
                    self._last_suggest_check = now
        except asyncio.CancelledError:
            return

    def _maybe_speak(self, global_cooldown: int) -> None:
        """Reactive — run watchers, pick the best observation, speak once."""
        now = time.time()
        if now - self._last_global < global_cooldown:
            return  # global cooldown — stay quiet a bit longer

        candidates: List[Observation] = []
        for watcher in WATCHERS:
            try:
                obs = watcher()
            except Exception:
                continue  # a broken watcher shouldn't silence Buddy
            if obs is None:
                continue
            last = self._last_said.get(obs.watcher, 0.0)
            if now - last < obs.cooldown_sec:
                continue
            candidates.append(obs)

        if not candidates:
            return

        # Pick the most interesting one; tie-breaker is "praise first"
        # because good news is cheap to deliver and feels good.
        candidates.sort(key=lambda o: o.rank(), reverse=True)
        chosen = candidates[0]
        self._emit(chosen, kind="watch")

    def _maybe_suggest(self, global_cooldown: int) -> None:
        """Proactive — when a goal is active, offer one goal-aware
        suggestion (technique, review, experiment, or phase nudge)."""
        try:
            from arail.goals import GoalStore
            goal = GoalStore().get_current()
        except Exception:
            return
        if not goal:
            return  # no goal → nothing to anchor to → stay quiet

        now = time.time()
        # Don't double-talk: if the reactive cadence emitted in the
        # last 5 min, hold off so Buddy isn't paragraph-shaped.
        if now - self._last_global < min(global_cooldown, 300):
            return

        candidates: List[Observation] = []
        for suggester in SUGGESTERS:
            try:
                obs = suggester(goal)
            except Exception:
                continue
            if obs is None:
                continue
            last = self._last_said.get(obs.watcher, 0.0)
            if now - last < obs.cooldown_sec:
                continue
            candidates.append(obs)

        if not candidates:
            return

        # All suggesters return severity="suggest" → ranks tie. Pick
        # randomly so the user gets variety across cadences.
        random.shuffle(candidates)
        chosen = candidates[0]
        self._emit(chosen, kind="suggest")

    def _emit(self, obs: Observation, *, kind: str) -> None:
        sentence = _voice(obs.fact)
        level = {
            "praise": "success",
            "warn": "warn",
            "suggest": "suggest",
        }.get(obs.severity, "info")
        data: Dict[str, Any] = {
            "watcher": obs.watcher,
            "severity": obs.severity,
            "fact": obs.fact,
        }
        if obs.suggestion:
            data["suggestion"] = obs.suggestion
        activity_log.emit(
            "buddy",
            f"{EMOJI} {NAME}: {sentence}",
            level,
            data=data,
        )
        now = time.time()
        self._last_said[obs.watcher] = now
        self._last_global = now
        if kind == "suggest":
            self._suggestions += 1
            verb = "Suggested"
        else:
            self._utterances += 1
            verb = "Observed"
        self._recent_actions.append(f"{verb} {obs.watcher}: {obs.fact[:80]}")
        self._save_state()
        self._sync_workflow(
            f"{verb} {obs.watcher}",
            "Wait for the next noteworthy signal or goal nudge",
        )

    # ── Memory: long-term (dreams/) ────────────────────────────────
    # Once per night, reflect on the day. Reads today's activity +
    # yesterday's dream, asks the model for a short first-person
    # reflection, writes dreams/<date>.md. Tomorrow's prompts will
    # include that dream as context — so Buddy literally "wakes up
    # knowing" what they figured out the night before.
    #
    # The daemon in src/arail/agents/dream_daemon.py decides when
    # to call this (once per heavy window, 22:00-08:00 default).

    async def dream(self) -> str:
        """Reflect on today's activity. Write dreams/<date>.md.

        Returns the dream body (minus frontmatter) so the caller can
        log a preview. Idempotent — if today's dream already exists,
        does nothing and returns an empty string.
        """
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dreams_dir = _state_file().parent / "dreams"
        dreams_dir.mkdir(parents=True, exist_ok=True)
        target = dreams_dir / f"{today}.md"
        if target.exists():
            return ""  # already dreamed today

        today_activity = _collect_today_buddy_activity(today)
        yesterday = _load_yesterday_dream(dreams_dir, today)

        prompt = _build_dream_prompt(today_activity, yesterday)
        reflection = await _call_model_for_dream(prompt)
        if not reflection:
            reflection = (
                f"(No reflection written — model unavailable at "
                f"{datetime.now(timezone.utc).strftime('%H:%M UTC')}.)"
            )

        body = (
            f"---\n"
            f"title: {NAME} — Dream {today}\n"
            f"section: agents/buddy/dreams\n"
            f"tags: [agent, buddy, dream]\n"
            f"date: {today}\n"
            f"---\n\n"
            f"{reflection.strip()}\n"
        )
        target.write_text(body)

        activity_log.emit(
            "buddy",
            f"{EMOJI} {NAME} dreamed — {target.name}",
            "info",
            data={"dream_file": str(target), "preview": reflection[:160]},
        )
        self._recent_actions.append(f"Dreamed and wrote {target.name}")
        self._sync_workflow(
            "Dream consolidation complete",
            "Resume watching lab signals",
        )
        return reflection


# ── Dream helpers ─────────────────────────────────────────────────
# Module-level so the test suite and the dream daemon can reach them
# without needing a BuddyAgent instance.

def _collect_today_buddy_activity(today_ymd: str) -> List[Dict[str, Any]]:
    """Read Buddy's entries from the activity log for the given UTC date.

    Pulls from the on-disk jsonl (activity_log's RAM buffer caps at
    200 events; a full day can exceed that). Returns the raw event
    dicts sorted by time.
    """
    from arail.activity import LOG_FILE
    if not LOG_FILE.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        for line in LOG_FILE.read_text().splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("source") != "buddy":
                continue
            ts = (event.get("ts") or "")[:10]  # YYYY-MM-DD
            if ts != today_ymd:
                continue
            rows.append(event)
    except OSError:
        return []
    return rows


def _load_yesterday_dream(dreams_dir: Path, today_ymd: str) -> str:
    """Return the content (minus frontmatter) of the most recent dream
    that isn't today's. Empty string when none exist yet."""
    if not dreams_dir.exists():
        return ""
    candidates = sorted(
        (p for p in dreams_dir.glob("*.md")
         if p.stem != today_ymd and not p.stem.startswith(".")),
        reverse=True,
    )
    if not candidates:
        return ""
    try:
        raw = candidates[0].read_text(errors="replace")
    except OSError:
        return ""
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end >= 0:
            raw = raw[end + 4:]
    return raw.strip()


def _build_dream_prompt(today_activity: List[Dict[str, Any]],
                        yesterday_dream: str) -> str:
    """Assemble the reflection prompt. First-person Buddy voice."""
    bullets: List[str] = []
    for event in today_activity:
        ts = (event.get("ts") or "")[11:16]
        data = event.get("data") or {}
        fact = data.get("fact") or event.get("message") or ""
        sev = data.get("severity") or "info"
        bullets.append(f"- [{ts}] ({sev}) {fact}")

    today_block = "\n".join(bullets) if bullets else "- (quiet day — nothing fired)"
    yesterday_block = (
        yesterday_dream if yesterday_dream
        else "(no reflection from yesterday — this is the first dream)"
    )

    return (
        "You are Buddy, ARAIL's lab partner, reflecting on the day before\n"
        "going quiet for the night. Write a short first-person reflection\n"
        "— 3 to 5 sentences. Note what you noticed and what you suggested.\n"
        "Flag what was interesting. Name one thing you'll watch for or\n"
        "propose tomorrow. Keep it grounded and warm. No lists, no\n"
        "markdown, no emoji — just the reflection.\n\n"
        "=== Yesterday's reflection (for continuity) ===\n"
        f"{yesterday_block}\n\n"
        "=== What you noticed and suggested today ===\n"
        f"{today_block}\n\n"
        "Tonight's reflection:"
    )


async def _call_model_for_dream(prompt: str) -> str:
    """Route the dream prompt through the shared local model. Runs the
    blocking router call in a thread so the daemon's event loop stays
    responsive."""
    try:
        from arail.router import ModelRouter
    except Exception:
        return ""
    try:
        router = ModelRouter()
    except Exception:
        return ""

    def _blocking_call() -> str:
        try:
            response = router.complete(prompt, max_tokens=280, temperature=0.7)
            return (response.text or "").strip()
        except Exception:
            return ""

    return await asyncio.to_thread(_blocking_call)


# Module-level singleton — mirrors the researcher pattern. Import as
# `from arail.agents.buddy import buddy` and call `buddy.start()` at
# portal startup.
buddy = BuddyAgent()
