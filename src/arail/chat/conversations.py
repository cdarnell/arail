"""Conversation store — Tier 1 of the lab's chat memory.

Implements the persistence contract in docs/conversation-memory.md and
ADR-0002 (the sprint doc sprints/2026-07-16-arail-chat-memory/ARCHITECTURE.md
is the design of record; this module is its storage/rehydration subset):

- ``lab/pkb/conversations/<cid>/transcript.jsonl`` + ``meta.json`` — under
  the PKB root, deliberately: "wipe the PKB = forget me" is a privacy
  contract, and anything in lab/data/ would survive a PKB wipe.
- **``.jsonl``, never ``.json``** — pkb's ``_PKB_TEXT_SUFFIXES`` includes
  ``.json``; a ``.json`` transcript would be vector-indexed into the wiki
  (pinned invariant, guarded by tests).
- The transcript is an append-only EVENT LOG; turn state is derived by
  folding events by ``turn_id``. Terminal events: completed / failed /
  interrupted / abandoned. A turn with no terminal event is an orphan; the
  startup sweep appends ``turn.interrupted`` — appending a terminal event
  is what resolves an orphan, so the sweep is idempotent.
- Every record carries ``v`` (schema version 1) and a per-turn monotonic
  ``seq``. One bad line never eats the log: parse failures are skipped
  per-line and counted.
- Single-user by design: no user_id, anywhere, ever.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_V = 1
TERMINAL_TYPES = {"turn.completed", "turn.failed",
                  "turn.interrupted", "turn.abandoned"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def conversations_root() -> Path:
    override = os.getenv("ARAIL_CONVERSATIONS_DIR", "").strip()
    if override:
        return Path(override)
    from arail.config import PKB_ROOT
    return Path(PKB_ROOT) / "conversations"


class ConversationStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else conversations_root()

    # ── plumbing ────────────────────────────────────────────────────
    def _dir(self, cid: str) -> Path:
        safe = "".join(c for c in cid if c.isalnum() or c in "._-")
        if not safe or safe != cid:
            raise ValueError(f"bad conversation id: {cid!r}")
        return self.root / cid

    def _transcript(self, cid: str) -> Path:
        return self._dir(cid) / "transcript.jsonl"

    def _meta_path(self, cid: str) -> Path:
        return self._dir(cid) / "meta.json"

    # ── lifecycle ───────────────────────────────────────────────────
    def create(self, title: str = "") -> Dict[str, Any]:
        cid = "c_" + uuid.uuid4().hex[:20]
        d = self._dir(cid)
        d.mkdir(parents=True, exist_ok=True)
        meta = {"conversation_id": cid,
                "title": title or "New conversation",
                "schema_version": SCHEMA_V,
                "created_at": _now(), "updated_at": _now()}
        self._meta_path(cid).write_text(json.dumps(meta, indent=2))
        self._transcript(cid).touch()
        return meta

    def get_meta(self, cid: str) -> Optional[Dict[str, Any]]:
        path = self._meta_path(cid)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return None

    def rename(self, cid: str, title: str) -> Optional[Dict[str, Any]]:
        meta = self.get_meta(cid)
        if meta is None:
            return None
        meta["title"] = title.strip() or meta["title"]
        meta["updated_at"] = _now()
        self._meta_path(cid).write_text(json.dumps(meta, indent=2))
        return meta

    def delete(self, cid: str) -> bool:
        """The PKB-wipe contract in miniature: rm the dir, it is forgotten."""
        d = self._dir(cid)
        if not d.exists():
            return False
        shutil.rmtree(d)
        return True

    def list(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not self.root.exists():
            return out
        for d in sorted(self.root.iterdir()):
            if not d.is_dir():
                continue
            meta = self.get_meta(d.name)
            if meta is None:
                continue
            transcript = self._transcript(d.name)
            try:
                size = transcript.stat().st_size
            except OSError:
                size = 0
            folded = self.fold(d.name, last_n_turns=0)   # counts only
            out.append({**meta, "bytes": size,
                        "turns": folded["turn_count"]})
        out.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
        return out

    # ── event log ───────────────────────────────────────────────────
    def append_event(self, cid: str, event: Dict[str, Any]) -> Dict[str, Any]:
        event.setdefault("v", SCHEMA_V)
        event.setdefault("ts", _now())
        event["conversation_id"] = cid
        path = self._transcript(cid)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False,
                               default=str) + "\n")
            f.flush()
        meta = self.get_meta(cid)
        if meta is not None:
            meta["updated_at"] = _now()
            self._meta_path(cid).write_text(json.dumps(meta, indent=2))
        return event

    def start_turn(self, cid: str, content: str, *, branch: str = "A",
                   model: Optional[str] = None,
                   backend: Optional[str] = None) -> str:
        turn_id = "t_" + uuid.uuid4().hex[:20]
        self.append_event(cid, {
            "type": "turn.started", "turn_id": turn_id, "branch": branch,
            "seq": 0, "role": "user", "content": content,
            "model": model, "backend": backend,
        })
        return turn_id

    def complete_turn(self, cid: str, turn_id: str, reply: str, *,
                      seq: int = 1, tokens_used: Optional[int] = None,
                      latency_ms: Optional[float] = None) -> None:
        self.append_event(cid, {
            "type": "turn.completed", "turn_id": turn_id, "seq": seq,
            "reply": reply, "tokens_used": tokens_used,
            "latency_ms": latency_ms,
        })

    def fail_turn(self, cid: str, turn_id: str, reason: str, *,
                  partial_text: str = "", seq: int = 1) -> None:
        self.append_event(cid, {
            "type": "turn.failed", "turn_id": turn_id, "seq": seq,
            "reason": reason, "partial_text": partial_text,
        })

    # ── fold (derive state from the event log) ──────────────────────
    def fold(self, cid: str, last_n_turns: int = 200) -> Dict[str, Any]:
        """Fold events by turn_id → ordered turns with terminal status.

        Per-line JSON errors are skipped and counted, never fatal (only
        the last line can ever be torn — append + flush per record).
        """
        path = self._transcript(cid)
        turns: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        skipped = 0
        if path.exists():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        skipped += 1
                        continue
                    tid = ev.get("turn_id")
                    if not tid:
                        continue
                    turn = turns.get(tid)
                    if turn is None:
                        turn = {"turn_id": tid, "status": "in_flight",
                                "branch": ev.get("branch", "A"),
                                "user": None, "reply": "", "partial": "",
                                "model": None, "backend": None}
                        turns[tid] = turn
                        order.append(tid)
                    etype = ev.get("type")
                    if etype == "turn.started":
                        turn["user"] = ev.get("content", "")
                        turn["model"] = ev.get("model")
                        turn["backend"] = ev.get("backend")
                    elif etype == "turn.progress":
                        turn["partial"] += str(ev.get("delta") or "")
                    elif etype == "turn.completed":
                        turn["status"] = "completed"
                        turn["reply"] = ev.get("reply", "")
                    elif etype == "turn.failed":
                        turn["status"] = "failed"
                        turn["partial"] = ev.get("partial_text") or turn["partial"]
                        turn["reason"] = ev.get("reason")
                    elif etype == "turn.interrupted":
                        turn["status"] = "interrupted"
                        turn["partial"] = ev.get("partial_text") or turn["partial"]
                    elif etype == "turn.abandoned":
                        turn["status"] = "abandoned"

        selected = order[-last_n_turns:] if last_n_turns else []
        messages: List[Dict[str, Any]] = []
        for tid in selected:
            t = turns[tid]
            if t["user"]:
                messages.append({"role": "user", "content": t["user"]})
            if t["status"] == "completed":
                messages.append({"role": "assistant", "content": t["reply"],
                                 "model": t["model"], "backend": t["backend"]})
            elif t["status"] in ("failed", "interrupted") and t["partial"]:
                messages.append({"role": "assistant", "content": t["partial"],
                                 "status": t["status"],
                                 "model": t["model"], "backend": t["backend"]})
        return {"conversation_id": cid, "messages": messages,
                "turns": [turns[t] for t in selected],
                "turn_count": len(order), "skipped_lines": skipped}

    # ── crash recovery ──────────────────────────────────────────────
    def sweep_orphans(self) -> int:
        """Append turn.interrupted to every turn with no terminal event.

        Idempotent: appending the terminal event is what resolves the
        orphan, so a second sweep finds nothing.
        """
        resolved = 0
        if not self.root.exists():
            return 0
        for d in self.root.iterdir():
            if not d.is_dir():
                continue
            cid = d.name
            folded = self.fold(cid, last_n_turns=10**6)
            for turn in folded["turns"]:
                if turn["status"] == "in_flight":
                    self.append_event(cid, {
                        "type": "turn.interrupted",
                        "turn_id": turn["turn_id"],
                        "seq": 999,
                        "reason": "server_restart",
                        "partial_text": turn["partial"],
                    })
                    resolved += 1
        return resolved
