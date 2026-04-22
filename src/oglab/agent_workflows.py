"""Persistent agent workflow snapshots.

This module tracks the operational state that matters most for agents:
their current objective, what they already finished, what they plan to
do next, whether they are paused, and whether they are getting chatty.

Production defaults to LanceDB-backed workflow recall, but every update
is first persisted to a local JSON snapshot for durability and disaster
recovery. If LanceDB is unavailable or degraded, the JSON copy remains
readable and the lab continues operating.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oglab.config import DATA_DIR

_LOCK = threading.Lock()
_TABLE_NAME = "agent_workflows"
_LAST_LANCE_SYNC_AT: str | None = None
_LAST_LANCE_SYNC_ERROR: str | None = None


def _workflow_file() -> Path:
    return DATA_DIR / "agent_workflows.json"


def _lance_dir() -> Path:
    raw = os.getenv("LANCE_PATH")
    if raw:
        return Path(raw).expanduser()
    return DATA_DIR / "lance"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict[str, dict[str, Any]]:
    path = _workflow_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for agent_id, value in data.items():
        if isinstance(agent_id, str) and isinstance(value, dict):
            out[agent_id] = value
    return out


def _save(data: dict[str, dict[str, Any]]) -> None:
    path = _workflow_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def _workflow_summary(snapshot: dict[str, Any]) -> str:
    objective = str(snapshot.get("objective") or "").strip()
    current_task = str(snapshot.get("current_task") or "").strip()
    next_step = str(snapshot.get("next_step") or "").strip()
    completed = snapshot.get("completed_steps") or []
    recent = "; ".join(str(step).strip() for step in completed[-3:] if str(step).strip())
    pause_reason = str(snapshot.get("pause_reason") or "").strip()
    chatter = snapshot.get("chatter") or {}
    return "\n".join(
        part
        for part in [
            f"agent: {snapshot.get('agent_id', '')}",
            f"status: {snapshot.get('status', '')}",
            f"objective: {objective}",
            f"current: {current_task}",
            f"next: {next_step}",
            f"completed: {recent}",
            f"pause: {pause_reason}",
            f"chatty: {bool(chatter.get('too_chatty'))}",
        ]
        if part.split(": ", 1)[1]
    )


def _hash_embedding(text: str, dim: int = 128) -> list[float]:
    try:
        from oglab.wiki_vectors import _hash_embedding as _wiki_hash_embedding

        return _wiki_hash_embedding(text, dim=dim)
    except Exception:
        return [0.0] * dim


def _sync_lance_rows(rows: list[dict[str, Any]]) -> None:
    global _LAST_LANCE_SYNC_AT, _LAST_LANCE_SYNC_ERROR
    try:
        import lancedb  # type: ignore[import-not-found]
    except Exception:
        return

    lance_dir = _lance_dir()
    lance_dir.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(lance_dir))
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized_rows.append({
            "agent_id": row.get("agent_id", ""),
            "status": row.get("status", ""),
            "objective": row.get("objective", ""),
            "current_task": row.get("current_task", ""),
            "next_step": row.get("next_step", ""),
            "pause_reason": row.get("pause_reason", ""),
            "updated_at": row.get("updated_at", ""),
            "summary": _workflow_summary(row),
            "vector": _hash_embedding(_workflow_summary(row)),
        })

    try:
        db.create_table(_TABLE_NAME, data=normalized_rows, mode="overwrite")
    except TypeError:
        if _TABLE_NAME in db.table_names():
            try:
                db.drop_table(_TABLE_NAME)
            except Exception:
                pass
        db.create_table(_TABLE_NAME, data=normalized_rows)

    _LAST_LANCE_SYNC_AT = _now_iso()
    _LAST_LANCE_SYNC_ERROR = None


def update_agent_workflow(agent_id: str, **fields: Any) -> dict[str, Any]:
    """Create or update a durable workflow snapshot for one agent."""
    global _LAST_LANCE_SYNC_ERROR
    if not agent_id:
        raise ValueError("agent_id is required")

    with _LOCK:
        data = _load()
        current = dict(data.get(agent_id) or {})
        merged = {**current, **{k: v for k, v in fields.items() if v is not None}}
        merged["agent_id"] = agent_id
        merged.setdefault("completed_steps", [])
        merged.setdefault("recent_actions", [])
        merged.setdefault("chatter", {})
        merged["updated_at"] = _now_iso()
        data[agent_id] = merged
        _save(data)
        try:
            _sync_lance_rows(list(data.values()))
        except Exception as exc:
            _LAST_LANCE_SYNC_ERROR = f"{type(exc).__name__}: {exc}"
        return merged


def get_agent_workflow(agent_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _load().get(agent_id)


def list_agent_workflows() -> list[dict[str, Any]]:
    with _LOCK:
        rows = list(_load().values())
    rows.sort(key=lambda row: str(row.get("agent_id") or ""))
    return rows


def workflow_health() -> dict[str, Any]:
    rows = list_agent_workflows()
    path = _workflow_file()
    lance_dir = _lance_dir()
    try:
        from importlib import metadata as importlib_metadata

        lancedb_version = importlib_metadata.version("lancedb")
    except Exception:
        lancedb_version = None

    memory_mode = "json-only"
    if lancedb_version:
        memory_mode = "lancedb+json-dr" if _LAST_LANCE_SYNC_ERROR is None else "lancedb-degraded+json-dr"

    return {
        "workflow_file": str(path),
        "workflow_file_exists": path.exists(),
        "lance_path": str(lance_dir),
        "lance_path_exists": lance_dir.exists(),
        "snapshot_count": len(rows),
        "agents": [row.get("agent_id") for row in rows],
        "lancedb_version": lancedb_version,
        "memory_mode": memory_mode,
        "json_dr_enabled": True,
        "last_lance_sync_at": _LAST_LANCE_SYNC_AT,
        "last_lance_sync_error": _LAST_LANCE_SYNC_ERROR,
    }