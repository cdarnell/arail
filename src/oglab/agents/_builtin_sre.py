"""SRE Watch — reliability agent for OGLab.

    An agent is a loop that notices things and speaks up.

This one watches for crashes and errors. It reads activity.jsonl on
every tick, fingerprints recent error events, and emits alerts into
the activity feed when:

    1. A new error pattern appears that hasn't been seen before.
    2. The same pattern recurs 3+ times in a 30-minute window.
    3. The portal's /api/jobs/state endpoint stops responding.

The mental model:

    1. Personality  — who SRE is (NAME, EMOJI, SYSTEM_PROMPT)
    2. Watchers     — functions that scan for problems (WATCHERS)
    3. Speech       — raw fact preferred; precision > personality
    4. Loop         — the heartbeat (SREAgent._run, _maybe_speak)
    5. Memory       — fingerprints + cooldowns (state.json)

Design rules:

    - Technical strings stay technical. No LLM paraphrasing unless
      the fact is ambiguous. Error messages must be reproducible.
    - Per-fingerprint cooldowns so one stuck loop doesn't flood the feed.
    - 3-minute global cooldown — enough quiet time between cascades.
    - Never hard-fail on log read errors; return None from watchers.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from oglab.activity import activity_log


# ── Where memory lives ───────────────────────────────────────────────
def _state_file() -> Path:
    from oglab.pkb import _pkb_root
    return _pkb_root() / "agents" / "sre" / "state.json"


def _activity_log_path() -> Path:
    from oglab.pkb import _pkb_root
    root = _pkb_root()
    # activity.jsonl lives in lab/data/, two levels up from pkb root
    return root.parent.parent / "data" / "activity.jsonl"


# ══════════════════════════════════════════════════════════════════════
#  1. PERSONALITY — who SRE is
# ══════════════════════════════════════════════════════════════════════

NAME = "SRE"
EMOJI = "🔥"

# SRE prefers raw technical facts over LLM paraphrasing, so this
# system prompt is a fallback — only used if the fact itself is empty.
SYSTEM_PROMPT = (
    "You are an SRE bot. You report incidents in one clinical sentence. "
    "State the error type, source, and occurrence count. No emojis. "
    "No softening language. Under 25 words."
)


# ══════════════════════════════════════════════════════════════════════
#  2. OBSERVATIONS — what SRE notices
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Observation:
    watcher: str
    severity: str           # "warn" | "error" (mapped to "warn" in emit)
    fact: str
    cooldown_key: str       # fingerprint or watcher name for per-key cooldown
    cooldown_sec: int = 10 * 60

    def rank(self) -> int:
        return {"error": 3, "warn": 2, "info": 1}.get(self.severity, 0)


# ══════════════════════════════════════════════════════════════════════
#  3. HELPERS — log reading & fingerprinting
# ══════════════════════════════════════════════════════════════════════

def _fingerprint(source: str, message: str) -> str:
    """Stable short ID for a (source, message) pair.

    Uses the first 40 chars of the message so similar messages from
    the same source collapse into one fingerprint.
    """
    return f"{source}::{message[:40]}"


def _tail_jsonl(path: Path, n: int) -> List[dict]:
    """Read the last n lines of a JSONL file. Fast for large files."""
    if not path.exists():
        return []
    try:
        with path.open("rb") as f:
            # Seek to end, walk backwards collecting newlines
            f.seek(0, 2)
            size = f.tell()
            buf = bytearray()
            lines_found = 0
            pos = size
            chunk = 4096
            while pos > 0 and lines_found <= n:
                read_size = min(chunk, pos)
                pos -= read_size
                f.seek(pos)
                buf = bytearray(f.read(read_size)) + buf
                lines_found = buf.count(b"\n")
            raw_lines = buf.decode("utf-8", errors="replace").splitlines()
            tail = raw_lines[-n:] if len(raw_lines) >= n else raw_lines
        events = []
        for line in tail:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return events
    except OSError:
        return []


def _parse_ts(ts_str: str) -> float:
    """Parse an ISO 8601 timestamp string to a Unix float. Returns 0 on error."""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


# ══════════════════════════════════════════════════════════════════════
#  4. WATCHERS — where noticing happens
# ══════════════════════════════════════════════════════════════════════

def _watch_recent_errors() -> Optional[Observation]:
    """Fires when a new error/warn pattern appears in the last 5 minutes.

    Reads the last 200 lines of activity.jsonl. For each event with
    level 'error' or 'warn', computes a fingerprint. Returns an
    Observation for the first fingerprint that's genuinely new (not
    in seen_fingerprints state). Per-fingerprint cooldown: 10 min.
    """
    log_path = _activity_log_path()
    events = _tail_jsonl(log_path, 200)
    if not events:
        return None

    now = time.time()
    cutoff = now - 5 * 60  # 5 minutes ago

    # Load seen fingerprints from state (we'll update state after emit)
    seen: Dict[str, float] = {}
    state_path = _state_file()
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text())
            seen = dict(data.get("seen_fingerprints") or {})
        except Exception:
            pass

    for ev in reversed(events):
        if ev.get("level") not in ("error", "warn"):
            continue
        ts = _parse_ts(ev.get("ts", ""))
        if ts < cutoff:
            break  # events are chronological; once we're past 5min, stop
        source = ev.get("source", "?")
        message = ev.get("message", "")
        fp = _fingerprint(source, message)
        first_seen = seen.get(fp, 0.0)
        if now - first_seen < 10 * 60:
            continue  # already surfaced recently
        # New fingerprint — report it
        level_word = "[ERROR]" if ev.get("level") == "error" else "[WARN]"
        fact = f"{level_word} {source}: {message[:120]}"
        return Observation(
            watcher="recent-errors",
            severity="warn",
            fact=fact,
            cooldown_key=fp,
            cooldown_sec=10 * 60,
        )
    return None


def _watch_crash_recurrence() -> Optional[Observation]:
    """Fires when the same error pattern recurs 3+ times in 30 minutes.

    Reads the last 500 lines. Counts fingerprint occurrences in a
    30-minute window. If any fingerprint hits ≥3 occurrences, returns
    a warn observation. Per-fingerprint cooldown: 15 min.
    """
    log_path = _activity_log_path()
    events = _tail_jsonl(log_path, 500)
    if not events:
        return None

    now = time.time()
    window_start = now - 30 * 60

    # Load last-said for recurrence watcher
    last_said: Dict[str, float] = {}
    state_path = _state_file()
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text())
            last_said = dict(data.get("last_said") or {})
        except Exception:
            pass

    counts: Dict[str, int] = {}
    fp_examples: Dict[str, str] = {}
    for ev in events:
        if ev.get("level") not in ("error", "warn"):
            continue
        ts = _parse_ts(ev.get("ts", ""))
        if ts < window_start:
            continue
        source = ev.get("source", "?")
        message = ev.get("message", "")
        fp = _fingerprint(source, message)
        counts[fp] = counts.get(fp, 0) + 1
        if fp not in fp_examples:
            fp_examples[fp] = f"{source}: {message[:80]}"

    for fp, count in counts.items():
        if count < 3:
            continue
        cooldown_key = f"recurrence::{fp}"
        last = last_said.get(cooldown_key, 0.0)
        if now - last < 15 * 60:
            continue
        fact = f"[RECURRENCE] {fp_examples[fp]!r} fired {count}x in 30 min."
        return Observation(
            watcher="crash-recurrence",
            severity="warn",
            fact=fact,
            cooldown_key=cooldown_key,
            cooldown_sec=15 * 60,
        )
    return None


def _watch_service_health() -> Optional[Observation]:
    """Fires when the portal's /api/jobs/state endpoint is unreachable.

    A quick GET with a 2-second timeout. If it fails or times out,
    we surface a warn. Cooldown: 10 min (keyed to 'service-health').
    """
    try:
        import urllib.request
        port = int(os.getenv("PORTAL_PORT", "8080"))
        url = f"http://127.0.0.1:{port}/api/jobs/state"
        req = urllib.request.urlopen(url, timeout=2)
        req.read()
        return None  # healthy
    except OSError:
        return Observation(
            watcher="service-health",
            severity="warn",
            fact=f"Portal /api/jobs/state is unreachable — portal may be down.",
            cooldown_key="service-health",
            cooldown_sec=10 * 60,
        )
    except Exception:
        return None  # unexpected error — don't spam


WATCHERS: List[Callable[[], Optional[Observation]]] = [
    _watch_recent_errors,
    _watch_crash_recurrence,
    _watch_service_health,
]


# ══════════════════════════════════════════════════════════════════════
#  5. LOOP — the heartbeat
# ══════════════════════════════════════════════════════════════════════

class SREAgent:
    """Background task that ticks every LAB_SRE_INTERVAL_SEC (default 120s)
    and surfaces crashes, error recurrences, and service downtime in the
    activity feed."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._status = "idle"
        self._last_said: Dict[str, float] = {}
        self._last_global: float = 0.0
        self._seen_fingerprints: Dict[str, float] = {}

    @property
    def status(self) -> str:
        return self._status

    # ── Memory ─────────────────────────────────────────────────────

    def _load_state(self) -> None:
        path = _state_file()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            self._last_said = dict(data.get("last_said") or {})
            self._last_global = float(data.get("last_global") or 0.0)
            self._seen_fingerprints = dict(data.get("seen_fingerprints") or {})
        except Exception:
            pass

    def _save_state(self) -> None:
        path = _state_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "last_said": self._last_said,
                "last_global": self._last_global,
                "seen_fingerprints": self._seen_fingerprints,
            }, indent=2))
        except OSError:
            pass

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._load_state()
        self._status = "running"
        self._task = asyncio.create_task(self._run())
        activity_log.emit(
            "sre",
            f"{EMOJI} {NAME} Watch is online — monitoring for crashes and errors.",
            "info",
        )

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._status = "idle"

    async def _run(self) -> None:
        interval = max(30, int(os.getenv("LAB_SRE_INTERVAL_SEC", "120")))
        global_cooldown = max(
            60, int(os.getenv("LAB_SRE_COOLDOWN_SEC", "180"))
        )
        try:
            while True:
                await asyncio.sleep(interval)
                self._maybe_speak(global_cooldown)
        except asyncio.CancelledError:
            return

    def _maybe_speak(self, global_cooldown: int) -> None:
        """Run every watcher, pick the highest-ranked observation, emit once."""
        now = time.time()
        if now - self._last_global < global_cooldown:
            return

        candidates: List[Observation] = []
        for watcher in WATCHERS:
            try:
                obs = watcher()
            except Exception:
                continue
            if obs is None:
                continue
            # Per-key cooldown check (fingerprint or watcher name)
            last = self._last_said.get(obs.cooldown_key, 0.0)
            if now - last < obs.cooldown_sec:
                continue
            candidates.append(obs)

        if not candidates:
            return

        candidates.sort(key=lambda o: o.rank(), reverse=True)
        chosen = candidates[0]

        # SRE prefers raw facts — skip LLM unless fact is somehow empty.
        sentence = chosen.fact or f"{EMOJI} Unspecified incident from {chosen.watcher}."

        activity_log.emit(
            "sre",
            f"{EMOJI} {NAME}: {sentence}",
            "warn",
            data={
                "watcher": chosen.watcher,
                "severity": chosen.severity,
                "fact": chosen.fact,
            },
        )

        # Mark this fingerprint as seen so recent-errors doesn't repeat it.
        if chosen.watcher == "recent-errors":
            # Extract the fingerprint from the cooldown_key
            self._seen_fingerprints[chosen.cooldown_key] = now

        self._last_said[chosen.cooldown_key] = now
        self._last_global = now
        self._save_state()


# ── Singleton export ─────────────────────────────────────────────────
# The loader discovers this via the module attribute named after the
# agent folder (agent_id == "sre", so it looks for `sre.sre`).
sre = SREAgent()
