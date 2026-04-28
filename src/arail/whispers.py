"""WhisperStore — backing store for the corner-toast whisper component.

The personality agent (currently ``pip``) publishes short, low-volume
notifications via :func:`record_whisper`. The portal's ``nav.js`` polls
``/api/whispers/recent`` every 15s and surfaces unseen entries as
bottom-right toasts. See ``docs/design.md`` §6.

Storage is a small JSON file under ``DATA_DIR/whispers.json`` — flat
list, capped at the most recent 50 entries. Tracking which whispers
the *user* has seen happens client-side (the JS keeps a Set of IDs
for the lifetime of the tab); the server returns the recent N and
trusts the client to dedupe. That's good enough for ambient toasts
and avoids needing per-session state on the server.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Iterable

from arail.config import DATA_DIR


WHISPERS_FILE = DATA_DIR / "whispers.json"
MAX_KEEP = 50
DEFAULT_RECENT = 10
VALID_TONES = {"purple", "blue", "green", "amber"}


class WhisperStore:
    """Bounded deque of recent whispers, persisted to JSON."""

    def __init__(self, path: Path = WHISPERS_FILE, max_keep: int = MAX_KEEP) -> None:
        self.path = path
        self.max_keep = max_keep
        self._lock = threading.Lock()
        self._buf: Deque[dict[str, Any]] = deque(maxlen=max_keep)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            if isinstance(data, list):
                for entry in data[-self.max_keep:]:
                    self._buf.append(entry)
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(list(self._buf), indent=2, default=str))

    def record(
        self,
        text: str,
        agent: str | None = None,
        thread_id: str | None = None,
        tone: str = "purple",
        ttl: int | None = None,
    ) -> dict[str, Any]:
        if tone not in VALID_TONES:
            tone = "purple"
        entry = {
            "id": uuid.uuid4().hex[:12],
            "text": text,
            "agent": agent,
            "thread_id": thread_id,
            "tone": tone,
            "ttl": ttl,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._buf.append(entry)
            self._save()
        return entry

    def recent(self, n: int = DEFAULT_RECENT) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._buf)[-n:]

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()
            self._save()


# Process-wide singleton.
whisper_store = WhisperStore()


def record_whisper(text: str, **kwargs: Any) -> dict[str, Any]:
    """Convenience for agents: ``record_whisper("found 3 papers", agent="pip")``."""
    return whisper_store.record(text, **kwargs)
