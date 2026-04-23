"""Operator redirects for live agents.

Redirects are lightweight steering notes that let a human bend an
agent's current run without killing it. The redirect store is file
backed so the UI and the agent loop can both see the same intent.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from arail.config import DATA_DIR

_LOCK = threading.Lock()


def _redirect_file() -> Path:
    return DATA_DIR / "agent_redirects.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict[str, dict[str, Any]]:
    path = _redirect_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for agent_id, payload in data.items():
        if isinstance(agent_id, str) and isinstance(payload, dict):
            out[agent_id] = payload
    return out


def _save(data: dict[str, dict[str, Any]]) -> None:
    path = _redirect_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def set_agent_redirect(agent_id: str, instruction: str, *, preset: str = "", label: str = "") -> dict[str, Any]:
    if not agent_id:
        raise ValueError("agent_id is required")
    if not instruction.strip():
        raise ValueError("instruction is required")

    with _LOCK:
        data = _load()
        current = dict(data.get(agent_id) or {})
        redirect = {
            **current,
            "agent_id": agent_id,
            "instruction": instruction.strip(),
            "preset": preset.strip(),
            "label": (label or preset or "custom").strip(),
            "updated_at": _now_iso(),
        }
        redirect.setdefault("created_at", redirect["updated_at"])
        data[agent_id] = redirect
        _save(data)
        return redirect


def get_agent_redirect(agent_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _load().get(agent_id)


def clear_agent_redirect(agent_id: str) -> dict[str, Any] | None:
    with _LOCK:
        data = _load()
        removed = data.pop(agent_id, None)
        _save(data)
        return removed


def redirect_profile(redirect: dict[str, Any] | None) -> dict[str, Any]:
    preset = str((redirect or {}).get("preset") or "").strip().lower()
    instruction = str((redirect or {}).get("instruction") or "").strip().lower()

    broaden_search = preset == "broaden-search" or "resume search" in instruction or "broaden search" in instruction
    skip_fetch = (
        preset in {"measurement", "stop-fetching", "autoresearch"}
        or "stop fetching" in instruction
        or "pause fetching" in instruction
        or "no more sources" in instruction
    ) and not broaden_search
    focus_measurement = (
        preset in {"measurement", "autoresearch"}
        or "measure" in instruction
        or "metric" in instruction
        or "eval" in instruction
        or "instrument" in instruction
    )
    prefer_autoresearch = (
        preset == "autoresearch"
        or "autoresearch" in instruction
        or "auto research" in instruction
        or "loop" in instruction
        or "sweep" in instruction
    )

    return {
        "skip_fetch": skip_fetch,
        "focus_measurement": focus_measurement,
        "prefer_autoresearch": prefer_autoresearch,
        "broaden_search": broaden_search,
    }