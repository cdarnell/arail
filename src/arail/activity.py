"""ActivityLog — global event bus for the Arail portal.

All agents, skills, and system components emit events here.
The portal streams them to the dashboard via SSE.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional


from arail.config import DATA_DIR

LOG_FILE = DATA_DIR / "activity.jsonl"
_log = logging.getLogger(__name__)


class ActivityLog:
    """Singleton event bus.  Thread-safe for sync emitters,
    asyncio-safe for SSE subscribers."""

    _instance: Optional["ActivityLog"] = None

    def __new__(cls) -> "ActivityLog":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        self._buffer: deque[Dict[str, Any]] = deque(maxlen=200)
        # (queue, owning event loop) — the loop is needed so sync emitters on
        # OTHER threads can hand the event over with call_soon_threadsafe.
        self._subscribers: list[
            tuple[asyncio.Queue[Dict[str, Any]], Optional[asyncio.AbstractEventLoop]]
        ] = []
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._emit_count = 0
        # Load last events from disk — TAIL-read (the old read_text() pulled
        # the whole file into memory; boot cost grew with lab age).
        for line in self._tail_lines(200):
            try:
                self._buffer.append(json.loads(line))
            except (ValueError, TypeError):
                continue  # one bad line never blocks replay

    @staticmethod
    def _tail_lines(n: int, *, chunk: int = 262_144) -> list:
        """Last *n* lines of the active log (+ rotated .1 when short)."""
        out: list[str] = []
        for path in (LOG_FILE.with_suffix(".jsonl.1"), LOG_FILE):
            if not path.exists():
                continue
            try:
                size = path.stat().st_size
                with open(path, "rb") as f:
                    f.seek(max(0, size - chunk))
                    blob = f.read().decode("utf-8", errors="replace")
                lines = blob.split("\n")
                if size > chunk and lines:
                    lines = lines[1:]   # drop the torn first line
                out.extend(ln for ln in lines if ln.strip())
            except OSError as e:
                _log.warning("activity log replay failed: %s", e)
        return out[-n:]

    def emit(self, source: str, message: str,
             level: str = "info", data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Emit an event.  Called from sync or async code."""
        event: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "message": message,
            "level": level,  # info, success, warn, error
        }
        if data:
            event["data"] = data

        self._buffer.append(event)

        # Persist (never re-emit here — we'd recurse into this same handler
        # if emit() fails. Log to stdlib so it surfaces in uvicorn's log.)
        try:
            # Rotation: check size every 256 emits; >10MB rolls to .jsonl.1
            # (single overwrite — two files bound the disk). Single-process
            # append (single-worker uvicorn), so os.replace is safe here.
            self._emit_count += 1
            if self._emit_count % 256 == 0:
                try:
                    if LOG_FILE.stat().st_size > 10 * 1024 * 1024:
                        os.replace(LOG_FILE, LOG_FILE.with_suffix(".jsonl.1"))
                except OSError:
                    pass
            with open(LOG_FILE, "a") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except OSError as e:
            _log.warning("activity log write failed: %s", e)

        # Fan-out to SSE subscribers. asyncio.Queue is NOT thread-safe: a
        # put_nowait from a foreign thread enqueues the item but does not wake
        # an idle event loop, so the subscriber's `await q.get()` can sit on a
        # delivered event until unrelated traffic wakes the loop. Hand the put
        # to the queue's own loop with call_soon_threadsafe in that case.
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        dead: list[tuple[asyncio.Queue, Optional[asyncio.AbstractEventLoop]]] = []
        for entry in list(self._subscribers):
            q, loop = entry
            if loop is None or loop is running:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(entry)
            elif loop.is_closed():
                dead.append(entry)
            else:
                def _put(q: asyncio.Queue = q) -> None:
                    try:
                        q.put_nowait(event)
                    except asyncio.QueueFull:
                        pass  # subscriber stalled — drop this event for them
                try:
                    loop.call_soon_threadsafe(_put)
                except RuntimeError:
                    dead.append(entry)  # loop shut down mid-flight
        for entry in dead:
            if entry in self._subscribers:
                self._subscribers.remove(entry)

        return event

    def recent(self, n: int = 50) -> List[Dict[str, Any]]:
        return list(self._buffer)[-n:]

    async def subscribe(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Yields events as they arrive.  Used by the SSE endpoint."""
        q: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=100)
        entry = (q, asyncio.get_running_loop())
        self._subscribers.append(entry)
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            if entry in self._subscribers:
                self._subscribers.remove(entry)


# Convenience — importable singleton
activity_log = ActivityLog()
