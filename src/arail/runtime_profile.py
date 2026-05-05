"""Runtime performance profile — interactive / balanced / throughput.

Resolves three signals into one mode + source label:

1. Manual override (30-min TTL) — operator's explicit pin
2. Presence (last request <5min ago) — operator is here, snap to interactive
3. Time-of-day (`current_window() == "heavy"`) — nobody's here, batch hard
4. Default — balanced

Persistence: override + ttl in ``lab/data/runtime_profile.json``; presence
timestamp in-memory only (re-stamped on next request after restart).
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Any, Literal

from arail.config import DATA_DIR
from arail.scheduler import current_window

Profile = Literal["interactive", "balanced", "throughput"]
Source = Literal["override", "presence", "window", "default"]

PRESENCE_IDLE_SEC_DEFAULT = 300
OVERRIDE_TTL_SEC_DEFAULT = 1800

_VALID_PROFILES: tuple[Profile, ...] = ("interactive", "balanced", "throughput")

_PARAMS: dict[Profile, dict[str, Any]] = {
    "interactive": {
        "airllm_max_tokens_cap": 256,
        "inference_concurrency": 1,
        "autoresearch": "paused",
        "aerollm_ring_depth": 1,
        "aerollm_batch": 1,
    },
    "balanced": {
        "airllm_max_tokens_cap": 512,
        "inference_concurrency": 1,
        "autoresearch": "normal",
        "aerollm_ring_depth": 2,
        "aerollm_batch": 1,
    },
    "throughput": {
        "airllm_max_tokens_cap": 1024,
        "inference_concurrency": 1,
        "autoresearch": "aggressive",
        "aerollm_ring_depth": 4,
        "aerollm_batch": 4,
    },
}

_STATE_PATH = DATA_DIR / "runtime_profile.json"
_lock = threading.Lock()
_override: dict[str, Any] | None = None  # {"profile": Profile, "set_at": float, "ttl_sec": int}
_last_presence_ts: float = 0.0
_loaded = False


def _presence_idle_sec() -> int:
    import os
    raw = os.getenv("ARAIL_PRESENCE_IDLE_SEC", "")
    try:
        v = int(raw)
        return v if v > 0 else PRESENCE_IDLE_SEC_DEFAULT
    except ValueError:
        return PRESENCE_IDLE_SEC_DEFAULT


def _load_state_locked() -> None:
    """Hydrate _override from disk on first use. Caller holds _lock."""
    global _override, _loaded
    if _loaded:
        return
    _loaded = True
    if not _STATE_PATH.exists():
        return
    try:
        data = json.loads(_STATE_PATH.read_text())
    except (OSError, ValueError):
        return
    ov = data.get("override")
    if isinstance(ov, dict) and ov.get("profile") in _VALID_PROFILES:
        _override = {
            "profile": ov["profile"],
            "set_at": float(ov.get("set_at", time.time())),
            "ttl_sec": int(ov.get("ttl_sec", OVERRIDE_TTL_SEC_DEFAULT)),
        }


def _persist_locked() -> None:
    """Write current _override to disk. Caller holds _lock."""
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"override": _override}
    _STATE_PATH.write_text(json.dumps(payload, indent=2))


def set_override(profile: Profile, ttl_sec: int = OVERRIDE_TTL_SEC_DEFAULT) -> None:
    if profile not in _VALID_PROFILES:
        raise ValueError(f"unknown profile: {profile!r}")
    if ttl_sec <= 0:
        raise ValueError(f"ttl_sec must be positive, got {ttl_sec}")
    global _override
    with _lock:
        _load_state_locked()
        _override = {
            "profile": profile,
            "set_at": time.time(),
            "ttl_sec": ttl_sec,
        }
        _persist_locked()


def clear_override() -> None:
    global _override
    with _lock:
        _load_state_locked()
        _override = None
        _persist_locked()


def mark_presence(now: float | None = None) -> None:
    """Record that the operator just hit the portal.

    O(1) module-level float write. Safe under CPython GIL without a lock —
    we don't take _lock here because the middleware calls this on every
    request and lock contention would be the wrong shape for an idle ping.
    """
    global _last_presence_ts
    _last_presence_ts = time.time() if now is None else now


def _override_age_locked() -> float | None:
    """Seconds since override set; None if no active override. Caller holds _lock."""
    global _override
    if _override is None:
        return None
    age = time.time() - _override["set_at"]
    if age >= _override["ttl_sec"]:
        # Expired — silently clear and persist
        _override = None
        _persist_locked()
        return None
    return age


def resolve(now: datetime | None = None) -> tuple[Profile, Source]:
    """Resolve the active profile + the signal that picked it."""
    with _lock:
        _load_state_locked()
        age = _override_age_locked()
        if age is not None and _override is not None:
            return (_override["profile"], "override")

    if _last_presence_ts > 0 and (time.time() - _last_presence_ts) < _presence_idle_sec():
        return ("interactive", "presence")

    if current_window(now) == "heavy":
        return ("throughput", "window")

    return ("balanced", "default")


def params(profile: Profile) -> dict[str, Any]:
    if profile not in _VALID_PROFILES:
        raise ValueError(f"unknown profile: {profile!r}")
    return dict(_PARAMS[profile])


def snapshot() -> dict[str, Any]:
    """JSON-serializable snapshot for /api/runtime/profile + scheduler.state()."""
    profile, source = resolve()
    out: dict[str, Any] = {
        "profile": profile,
        "source": source,
        "params": params(profile),
        "window": current_window(),
        "presence_idle_sec": _presence_idle_sec(),
    }

    with _lock:
        _load_state_locked()
        if _override is not None:
            age = time.time() - _override["set_at"]
            remaining = max(0, int(_override["ttl_sec"] - age))
            out["override_expires_in_sec"] = remaining
            out["override_profile"] = _override["profile"]
        else:
            out["override_expires_in_sec"] = None
            out["override_profile"] = None

    if _last_presence_ts > 0:
        out["last_presence_sec_ago"] = int(time.time() - _last_presence_ts)
    else:
        out["last_presence_sec_ago"] = None

    return out


def _reset_for_tests() -> None:
    """Test-only: wipe in-memory state and the on-disk file."""
    global _override, _last_presence_ts, _loaded
    with _lock:
        _override = None
        _last_presence_ts = 0.0
        _loaded = True
        if _STATE_PATH.exists():
            _STATE_PATH.unlink()
