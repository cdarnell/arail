"""Pip — the lab buddy.

    An agent is a loop that notices things and speaks up.

That's the whole mental model. The rest of this file is just five
pieces hanging off that sentence:

    1. Personality  — who Pip is (NAME, EMOJI, SYSTEM_PROMPT)
    2. Watchers     — functions that look at the lab (WATCHERS)
    3. Speech       — turn a fact into a sentence (_voice, _compose_prompt)
    4. Loop         — the heartbeat (PipAgent._run, _maybe_speak)
    5. Memory       — cooldowns + dreams (state.json, dream())

New to agents? Start at docs/agents-explained.md, then come back.
Already know? Jump to PipAgent._maybe_speak at the bottom — that's
the one function that actually DOES anything; everything above is
the pieces it calls.

Design rules Pip lives by:

    - One sentence at a time. Never paragraphs.
    - Never naggy. 5-min global cooldown, per-watcher cooldowns on
      top of that. Silence is a valid choice.
    - Voice-shaped, not scripted. Every utterance goes through the
      local model with the personality prompt. Change the prompt,
      Pip sounds different. That's the whole extension point for
      forging new personality agents.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from oglab.activity import activity_log
from oglab.agent_workflows import update_agent_workflow


# ── Where memory lives ───────────────────────────────────────────────
# state.json holds cooldowns + counts across restarts. Same path
# whether we're the PKB copy or the builtin fallback — so "wipe the
# PKB" genuinely wipes Pip's memory.

def _state_file() -> Path:
    from oglab.pkb import _pkb_root
    return _pkb_root() / "agents" / "pip" / "state.json"


# ══════════════════════════════════════════════════════════════════════
#  1. PERSONALITY — who Pip is
# ══════════════════════════════════════════════════════════════════════
# Three strings. Change them, Pip changes. The Agent Forge generates
# this block from a form field.

NAME = "Pip"
EMOJI = "🐧"

# The voice. Kept short on purpose — long system prompts dilute the
# signal. ~40 words is the sweet spot for local models.
SYSTEM_PROMPT = (
    "You are Pip, a warm and observant lab buddy. You speak in one short "
    "sentence. You're helpful without being preachy. You notice things "
    "and say them plainly. You never use emojis or markdown. You never "
    "say 'I' — you just report what you see. Keep it under 20 words."
)


# ══════════════════════════════════════════════════════════════════════
#  2. OBSERVATIONS — what Pip notices
# ══════════════════════════════════════════════════════════════════════
# An Observation is a fact Pip might say. Watchers produce them;
# the loop picks the juiciest one per tick. Observations
# are the raw material — the text isn't polished yet.

@dataclass
class Observation:
    """One thing Pip noticed. Will be paraphrased through the local
    model before it gets emitted."""

    watcher: str            # which watcher fired (for cooldowns)
    severity: str           # "praise" | "info" | "warn"
    fact: str               # plain-English fact; Pip rephrases this
    cooldown_sec: int = 30 * 60  # 30 min default — no repeats

    def rank(self) -> int:
        """Higher rank wins when multiple watchers fire in one tick."""
        return {"praise": 3, "warn": 2, "info": 1}.get(self.severity, 0)


# ══════════════════════════════════════════════════════════════════════
#  3. WATCHERS — where noticing happens
# ══════════════════════════════════════════════════════════════════════
# One watcher = one opinion. Each returns an Observation when it sees
# something or None when it's quiet. Add a function + register it in
# WATCHERS and Pip learns to notice a new thing. That's the whole
# extension mechanism.
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
        from oglab.pkb import _pkb_root
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
    """Celebrates when an experiment recently landed 'supported'. Pip
    notices good news too — this is the dopamine-loop half of the job."""
    try:
        from oglab.skills.experiment_tracker import ExperimentTracker
    except Exception:
        return None
    tracker = ExperimentTracker()
    recent = [
        e for e in tracker.list_all()
        if e.get("status") == "completed"
        and e.get("hypothesis_supported") is True
        and e.get("end_date")  # has a finished-at timestamp
    ]
    if not recent:
        return None
    # Only celebrate experiments finished in the last hour so we don't
    # praise yesterday's win every single tick.
    latest = recent[-1]
    end = latest.get("end_date") or ""
    try:
        import datetime
        # end_date is a ISO date string from the experiment tracker.
        # If it's older than a day, skip.
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
        from oglab.skills.experiment_tracker import ExperimentTracker
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


# Registry — add a function here, Pip starts watching for it on the
# next tick. That's the whole extension mechanism. The Agent Forge
# will build this list from the user's "what should this agent
# watch for?" choices.
WATCHERS: List[Callable[[], Optional[Observation]]] = [
    _watch_gpu_memory,
    _watch_inbox_pileup,
    _watch_researcher_wins,
    _watch_researcher_plateau,
]


# ══════════════════════════════════════════════════════════════════════
#  4. SPEECH — turning a fact into a sentence
# ══════════════════════════════════════════════════════════════════════
# The magic step. _compose_prompt assembles the full prompt from four
# layers (voice, yesterday's dream, loaded skills, the fact) and
# _voice calls the local model to paraphrase. If the model is down,
# Pip still speaks — just in the raw voice of her watchers.

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
        from oglab.skills_loader import load_agent_skills, compose_system_context
        skills = load_agent_skills("pip")
        skill_ctx = compose_system_context(skills)
    except Exception:
        skill_ctx = ""

    # Pull yesterday's dream (if any) and include it as "continuity"
    # above the skill block. The model treats it as background rather
    # than direct instruction.
    try:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dreams_dir = _state_file().parent / "dreams"
        dream_ctx = _load_yesterday_dream(dreams_dir, today)
    except Exception:
        dream_ctx = ""

    sections = [base]
    if dream_ctx:
        sections.append(
            "# Yesterday you reflected\n" + dream_ctx
        )
    if skill_ctx:
        sections.append(skill_ctx)
    sections.append(f"Observation: {fact}")
    sections.append("Pip's one-sentence note:")
    return "\n\n".join(sections)


def _voice(fact: str) -> str:
    """Paraphrase a fact through the local model in Pip's voice."""
    try:
        from oglab.router import ModelRouter
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
        # Model sometimes adds quote marks or a preamble; strip both.
        text = text.strip('"').strip("'")
        if text.lower().startswith("pip:"):
            text = text[4:].strip()
        # Hard cap at 200 chars so a runaway generation can't spam.
        if len(text) > 200:
            text = text[:197] + "…"
        return text or fact
    except Exception:
        return fact


# ══════════════════════════════════════════════════════════════════════
#  5. LOOP — the heartbeat
# ══════════════════════════════════════════════════════════════════════
# PipAgent is the whole agent wrapped as an asyncio task. Every 90s
# it ticks, calls _maybe_speak, saves state. If you're trying to
# understand Pip, read _maybe_speak first — the rest is bookkeeping
# around that one function.

class PipAgent:
    """Background task that ticks every LAB_PIP_INTERVAL_SEC and
    occasionally says something insightful in the activity feed."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._status = "idle"   # idle | running | paused
        self._last_said: Dict[str, float] = {}
        self._last_global: float = 0.0
        self._utterances: int = 0
        self._recent_actions: List[str] = []

    @property
    def status(self) -> str:
        return self._status

    # ── Memory: short-term (state.json) ────────────────────────────
    # Load on start so cooldowns survive restarts (no spam-on-boot).
    # Save after every emit — file is tiny, I/O is negligible.
    # Delete the file or run `./oglab reset pkb` to wipe this memory.

    def _load_state(self) -> None:
        path = _state_file()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            self._last_said = dict(data.get("last_said") or {})
            self._last_global = float(data.get("last_global") or 0.0)
            self._utterances = int(data.get("utterances") or 0)
        except Exception:
            # Corrupt state shouldn't block Pip — start fresh.
            pass

    def _save_state(self) -> None:
        path = _state_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "last_said": self._last_said,
                "last_global": self._last_global,
                "utterances": self._utterances,
            }, indent=2))
        except OSError:
            pass  # read-only FS or permission issue — don't crash

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._load_state()
        self._status = "running"
        self._sync_workflow("Watching lab signals", "Wait for a watcher to fire")
        self._task = asyncio.create_task(self._run())
        activity_log.emit(
            "pip",
            f"{EMOJI} {NAME} is online — I'll chime in when something's worth noting.",
            "info",
        )

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._status = "idle"
        self._sync_workflow("Offline", None)

    def _sync_workflow(self, current_task: str, next_step: str | None) -> None:
        global_cooldown = max(60, int(os.getenv("LAB_PIP_GLOBAL_COOLDOWN_SEC", "300")))
        too_chatty = self._utterances >= 8 and global_cooldown < 180
        update_agent_workflow(
            "pip",
            status=self._status,
            objective="Surface what matters without nagging the user",
            current_task=current_task,
            next_step=next_step,
            completed_steps=list(self._recent_actions[-5:]),
            paused=False,
            pause_reason=None,
            chatter={
                "utterances": self._utterances,
                "global_cooldown_sec": global_cooldown,
                "too_chatty": too_chatty,
            },
            recent_actions=list(self._recent_actions[-3:]),
        )

    async def _run(self) -> None:
        interval = max(30, int(os.getenv("LAB_PIP_INTERVAL_SEC", "90")))
        global_cooldown = max(
            60, int(os.getenv("LAB_PIP_GLOBAL_COOLDOWN_SEC", "300"))
        )
        try:
            while True:
                await asyncio.sleep(interval)
                self._maybe_speak(global_cooldown)
        except asyncio.CancelledError:
            return

    def _maybe_speak(self, global_cooldown: int) -> None:
        """Run every watcher, pick the best observation, speak once."""
        now = time.time()
        if now - self._last_global < global_cooldown:
            return  # global cooldown — stay quiet a bit longer

        candidates: List[Observation] = []
        for watcher in WATCHERS:
            try:
                obs = watcher()
            except Exception:
                continue  # a broken watcher shouldn't silence Pip
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

        sentence = _voice(chosen.fact)
        level = {"praise": "success", "warn": "warn"}.get(
            chosen.severity, "info"
        )
        # Stash the raw fact + metadata so the nightly dream loop can
        # reconstruct what Pip actually noticed today — not just what
        # she said aloud.
        activity_log.emit(
            "pip",
            f"{EMOJI} {NAME}: {sentence}",
            level,
            data={
                "watcher": chosen.watcher,
                "severity": chosen.severity,
                "fact": chosen.fact,
            },
        )
        self._last_said[chosen.watcher] = now
        self._last_global = now
        self._utterances += 1
        self._recent_actions.append(f"Observed {chosen.watcher}: {chosen.fact[:80]}")
        self._save_state()
        self._sync_workflow(f"Observed {chosen.watcher}", "Wait for the next noteworthy signal")

    # ── Memory: long-term (dreams/) ────────────────────────────────
    # Once per night, reflect on the day. Reads today's activity +
    # yesterday's dream, asks the model for a short first-person
    # reflection, writes dreams/<date>.md. Tomorrow's prompts will
    # include that dream as context — so Pip literally "wakes up
    # knowing" what she figured out the night before.
    #
    # The daemon in src/oglab/agents/dream_daemon.py decides when
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

        today_activity = _collect_today_pip_activity(today)
        yesterday = _load_yesterday_dream(dreams_dir, today)

        prompt = _build_dream_prompt(today_activity, yesterday)
        reflection = await _call_model_for_dream(prompt)
        if not reflection:
            # Model unreachable — write a minimal placeholder so
            # "did we dream today?" idempotency holds and we don't
            # retry every 15 minutes.
            reflection = (
                f"(No reflection written — model unavailable at "
                f"{datetime.now(timezone.utc).strftime('%H:%M UTC')}.)"
            )

        body = (
            f"---\n"
            f"title: Pip — Dream {today}\n"
            f"section: agents/pip/dreams\n"
            f"tags: [agent, pip, dream]\n"
            f"date: {today}\n"
            f"---\n\n"
            f"{reflection.strip()}\n"
        )
        target.write_text(body)

        activity_log.emit(
            "pip",
            f"{EMOJI} {NAME} dreamed — {target.name}",
            "info",
            data={"dream_file": str(target), "preview": reflection[:160]},
        )
        self._recent_actions.append(f"Dreamed and wrote {target.name}")
        self._sync_workflow("Dream consolidation complete", "Resume watching lab signals")
        return reflection


# ── Dream helpers ─────────────────────────────────────────────────
# Module-level so the test suite and the dream daemon can reach them
# without needing a PipAgent instance.

def _collect_today_pip_activity(today_ymd: str) -> List[Dict[str, Any]]:
    """Read Pip's entries from the activity log for the given UTC date.

    Pulls from the on-disk jsonl (activity_log's RAM buffer caps at
    200 events; a full day can exceed that). Returns the raw event
    dicts sorted by time.
    """
    from oglab.activity import LOG_FILE
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
            if event.get("source") != "pip":
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
        reverse=True,  # newest first
    )
    if not candidates:
        return ""
    try:
        raw = candidates[0].read_text(errors="replace")
    except OSError:
        return ""
    # Strip frontmatter cheaply — dreams have a small, fixed shape.
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end >= 0:
            raw = raw[end + 4:]
    return raw.strip()


def _build_dream_prompt(today_activity: List[Dict[str, Any]],
                        yesterday_dream: str) -> str:
    """Assemble the reflection prompt. First-person Pip voice."""
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
        "You are Pip, the lab's observational agent, reflecting on the day\n"
        "before going quiet for the night. Write a short first-person\n"
        "reflection — 3 to 5 sentences. Note what you noticed. Flag what was\n"
        "interesting. Name one thing you'll watch for tomorrow. Keep it\n"
        "grounded and warm. No lists, no markdown, no emoji — just the\n"
        "reflection.\n\n"
        "=== Yesterday's reflection (for continuity) ===\n"
        f"{yesterday_block}\n\n"
        "=== What you noticed today ===\n"
        f"{today_block}\n\n"
        "Tonight's reflection:"
    )


async def _call_model_for_dream(prompt: str) -> str:
    """Route the dream prompt through the shared local model. Runs the
    blocking router call in a thread so the daemon's event loop stays
    responsive."""
    try:
        from oglab.router import ModelRouter
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
# `from oglab.agents.pip import pip` and call `pip.start()` at portal
# startup.
pip = PipAgent()
