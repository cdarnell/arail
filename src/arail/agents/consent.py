"""Agent consent / network allowlist system.

Agents have ZERO network access by default.  When an agent wants to
fetch something from the internet it must:

1. Submit a ``ConsentRequest`` (url + reason).
2. Wait for the user to approve or deny via the portal UI.
3. If approved, the fetch proceeds and the response is cached locally.
4. If the user checks "remember domain", that domain is added to the
   persistent allowlist so future requests skip the prompt.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


from arail.config import DATA_DIR as _DATA_DIR

CONSENT_DIR = _DATA_DIR / "consent"


class ConsentStore:
    """Manages pending requests and the domain allowlist."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        # Late-bind the default so tests (and env changes) that repoint
        # CONSENT_DIR at construction time are honored.
        self.data_dir = data_dir if data_dir is not None else CONSENT_DIR
        self.pending_file = self.data_dir / "pending.json"
        self.allowlist_file = self.data_dir / "allowlist.json"
        self.history_file = self.data_dir / "history.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ── Allowlist ────────────────────────────────────────────────────

    def list_allowed(self) -> List[str]:
        return self._load(self.allowlist_file, default=[])

    def is_allowed(self, url: str) -> bool:
        domain = urlparse(url).netloc
        return domain in self.list_allowed()

    def add_domain(self, url: str) -> None:
        domain = urlparse(url).netloc
        allowed = self.list_allowed()
        if domain not in allowed:
            allowed.append(domain)
            self._save(self.allowlist_file, allowed)

    def remove_domain(self, domain: str) -> None:
        allowed = self.list_allowed()
        if domain in allowed:
            allowed.remove(domain)
            self._save(self.allowlist_file, allowed)

    # ── Pending requests ─────────────────────────────────────────────

    def request_access(self, url: str, reason: str,
                       agent: str = "default") -> Dict[str, Any]:
        """Agent calls this to ask for network access.

        Returns the request record.  If the domain is already on the
        allowlist the request is auto-approved.
        """
        domain = urlparse(url).netloc
        req: Dict[str, Any] = {
            "id": uuid.uuid4().hex[:8],
            "url": url,
            "domain": domain,
            "reason": reason,
            "agent": agent,
            "status": "pending",
            "created_at": _now(),
        }

        if self.is_allowed(url):
            req["status"] = "auto_approved"
            self._append_history(req)
            return req

        pending = self.list_pending()
        pending.append(req)
        self._save(self.pending_file, pending)
        return req

    def list_pending(self) -> List[Dict[str, Any]]:
        return self._load(self.pending_file, default=[])

    def approve(self, request_id: str, *,
                remember_domain: bool = False) -> None:
        pending = self.list_pending()
        approved = None
        remaining = []
        for r in pending:
            if r["id"] == request_id:
                r["status"] = "approved"
                r["resolved_at"] = _now()
                approved = r
            else:
                remaining.append(r)
        self._save(self.pending_file, remaining)

        if approved:
            self._append_history(approved)
            if remember_domain:
                self.add_domain(approved["url"])

    def is_approved(self, request_id: str) -> bool:
        """True iff ``request_id`` resolved to approved/auto_approved.

        Used by egress.allow_bootstrap_fetch to verify that a scoped
        airgap exemption is backed by a real recorded consent — the
        history file is the durable artifact of the user's decision.
        """
        for r in self._load(self.history_file, default=[]):
            if r.get("id") == request_id and r.get("status") in (
                "approved", "auto_approved",
            ):
                return True
        return False

    def deny(self, request_id: str) -> None:
        pending = self.list_pending()
        remaining = []
        for r in pending:
            if r["id"] == request_id:
                r["status"] = "denied"
                r["resolved_at"] = _now()
                self._append_history(r)
            else:
                remaining.append(r)
        self._save(self.pending_file, remaining)

    # ── Internals ────────────────────────────────────────────────────

    def _append_history(self, record: Dict[str, Any]) -> None:
        history = self._load(self.history_file, default=[])
        history.append(record)
        self._save(self.history_file, history)

    def _load(self, path: Path, default: Any = None) -> Any:
        if not path.exists():
            return default if default is not None else []
        return json.loads(path.read_text())

    def _save(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2, default=str))
        # Consent state (allowlist / pending / history) records where agents
        # may reach — keep it owner-only, matching lab/data/secrets.env.
        try:
            path.chmod(0o600)
        except OSError:
            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
