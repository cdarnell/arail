"""
Canvas client for other lab skills.

Usage from Data Curator, Insight Generator, agents, or anywhere:

    from core.knowledge_canvas.client import canvas

    canvas.ingest({"kind": "paper", "title": "...", "uri": "...", ...})

    results = canvas.query(semantic="nitrogen timing", must_tags=["peanuts"])

If the canvas backend isn't running, ingest calls queue to a local
JSONL file and flush when the backend comes back. Querying without a
backend returns []. This keeps the lab functional even when the canvas
service is down — it's additive, not load-bearing.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


CANVAS_URL = os.getenv("CANVAS_URL", "http://localhost:8000")
QUEUE_PATH = Path(os.getenv("CANVAS_QUEUE", ".canvas_queue.jsonl"))
TIMEOUT = 5.0


class CanvasClient:
    def __init__(self, url: str = CANVAS_URL):
        self.url = url.rstrip("/")

    # ------------------------------------------------------------------
    def ingest(self, source: dict[str, Any]) -> dict | None:
        """
        Drop a source into the canvas. Accepts a dict with at minimum:
          kind, title, uri
        Optional: body_excerpt, tags, year, author, domain, meta, ingested_by
        """
        try:
            r = httpx.post(f"{self.url}/api/sources/ingest", json=source, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            self._queue(source, reason=str(e))
            return None

    def ingest_many(self, sources: list[dict]) -> list[dict]:
        results = []
        for s in sources:
            r = self.ingest(s)
            if r:
                results.append(r)
        return results

    # ------------------------------------------------------------------
    def query(self, **kwargs) -> list[dict]:
        """
        Hybrid search. Any combination of:
          semantic: str
          must_tags, must_not_tags: list[str]
          kinds: list[str]
          domain: str
          year_from, year_to: int
          k: int (default 20)
        """
        try:
            r = httpx.post(f"{self.url}/api/sources/query", json=kwargs, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json().get("results", [])
        except Exception:
            return []

    # ------------------------------------------------------------------
    def link(self, src_id: str, dst_id: str, rel: str = "LINKS_TO", **props):
        """Create a typed edge between two sources."""
        try:
            r = httpx.post(
                f"{self.url}/api/sources/link",
                json={"src_id": src_id, "dst_id": dst_id, "rel": rel, "props": props},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    def flush_queue(self) -> int:
        """Replay queued ingests once the backend is back. Returns count sent."""
        if not QUEUE_PATH.exists():
            return 0
        sent = 0
        remaining: list[str] = []
        for line in QUEUE_PATH.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                r = httpx.post(
                    f"{self.url}/api/sources/ingest",
                    json=entry["source"], timeout=TIMEOUT,
                )
                r.raise_for_status()
                sent += 1
            except Exception:
                remaining.append(line)
        QUEUE_PATH.write_text("\n".join(remaining) + ("\n" if remaining else ""))
        return sent

    # ------------------------------------------------------------------
    def _queue(self, source: dict, reason: str = ""):
        entry = {
            "queued_at": datetime.utcnow().isoformat(),
            "reason": reason,
            "source": source,
        }
        with QUEUE_PATH.open("a") as f:
            f.write(json.dumps(entry) + "\n")


# Module-level singleton for ergonomic `from ... import canvas`
canvas = CanvasClient()
