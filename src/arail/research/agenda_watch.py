"""World-generic horizon scouting — act on the mounted World's agenda.json.

Every sealed World already declares what it cares about: ``agenda.json``
(``dac.world-agenda/v1``) carries ``watches[]`` with feeds and a cadence,
derived from the World's ``spec.knowledge_sources``. Until now nothing read
it. This module is that consumer: on a Librarian tick, each URL-shaped feed
that is due per its cadence is fetched through the consent-gated scouting
pipeline (``arail.research.scouting``), and a CHANGE since the last look
becomes a finding staged into the PKB review queue — a proposal brought to
the World owner's attention, never an auto-approved fact.

The same loop serves every World with zero domain-specific code: the AI
World's agenda points at arXiv, so a new industry development surfaces as a
reviewable finding; the Video Games World's agenda points at vendor driver
pages, so a new driver release surfaces the same way. The World's own sealed
declaration is the only thing that changes what gets watched.

Honesty rails, in order of enforcement:
  • AIRGAPPED-INERT — ``is_airgapped()`` short-circuits before any consent or
    network machinery is touched. The default lab never fetches.
  • CONSENT — each feed URL needs an approved ``ConsentStore`` record. A
    scheduled agent never self-approves; a pending request waits for the
    operator, a denied one disables the feed.
  • VERBATIM URLS ONLY — feeds are taken byte-for-byte from the sealed
    agenda.json. This module never composes a URL, so no user/hardware/game
    data can leak into one (same structural guarantee as scouting.py).
  • HUMAN GATE — findings are markdown files under ``sources/scout/`` in the
    PKB: pending in the Compiled-KB review queue until the operator approves.
    Each change gets a hash-suffixed filename so approval of one snapshot
    never auto-approves the next.

State lives at ``DATA_DIR/agenda-watch.json`` — per-user runtime, keyed to
the mounted World's slug, reset on a World switch (a different World has a
different horizon).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from arail.airgap import is_airgapped
from arail.research import scouting

_log = logging.getLogger(__name__)

STATE_NAME = "agenda-watch.json"
SCOUT_SUBDIR = "sources/scout"

_URL_RE = re.compile(r"^https?://\S+$")
_DEFAULT_WATCH_HOURS = 24.0
_FETCH_TIMEOUT_SEC = 20
_MAX_FETCH_BYTES = 512 * 1024
_EXCERPT_CHARS = 1500


def _watch_interval_sec() -> float:
    import os
    raw = os.getenv("ARAIL_SCOUT_WATCH_HOURS", "")
    try:
        v = float(raw)
        return v * 3600.0 if v > 0 else _DEFAULT_WATCH_HOURS * 3600.0
    except ValueError:
        return _DEFAULT_WATCH_HOURS * 3600.0


@dataclass
class WatchFeed:
    node: str
    url: str          # verbatim from the sealed agenda — never composed here
    cadence: str


def load_watches(agenda: Dict[str, Any]) -> List[WatchFeed]:
    """Extract the fetchable feeds from a dac.world-agenda/v1 document.

    Feeds are free strings; only URL-shaped ones are actionable (a feed like
    "vendor documentation (NVIDIA, AMD, …)" is a human note, not a fetch
    target) — those are skipped, never guessed into URLs.
    """
    out: List[WatchFeed] = []
    for watch in (agenda or {}).get("watches") or []:
        if not isinstance(watch, dict):
            continue
        node = str(watch.get("node") or "").strip() or "world"
        cadence = str(watch.get("cadence") or "occasional").strip()
        for feed in watch.get("feeds") or []:
            if isinstance(feed, str) and _URL_RE.match(feed.strip()):
                out.append(WatchFeed(node=node, url=feed.strip(), cadence=cadence))
    return out


# ── state ────────────────────────────────────────────────────────────

def _state_path(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from arail.config import DATA_DIR as data_dir  # late for test repoints
    return Path(data_dir) / STATE_NAME


def _load_state(path: Path, world: str) -> Dict[str, Any]:
    try:
        state = json.loads(path.read_text())
        if state.get("world") == world:
            return state
    except Exception:
        pass
    return {"world": world, "feeds": {}}


def _save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)


# ── fetch + finding ──────────────────────────────────────────────────

def _fetch_text(url: str) -> str:
    """One bounded GET of a declared feed. Runs inside scouting's
    allow_egress scope, so it is audited to egress.jsonl and hard-blocked
    in airgapped mode by the guard itself."""
    import requests
    resp = requests.get(url, timeout=_FETCH_TIMEOUT_SEC, stream=True,
                        headers={"User-Agent": "Arail/0.1 (world agenda watch)"})
    resp.raise_for_status()
    chunks: List[bytes] = []
    size = 0
    for chunk in resp.iter_content(chunk_size=16384):
        chunks.append(chunk)
        size += len(chunk)
        if size >= _MAX_FETCH_BYTES:
            break
    return b"".join(chunks).decode(resp.encoding or "utf-8", "replace")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _slugish(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return s[:48] or "feed"


def _finding_markdown(world: str, feed: WatchFeed, text: str,
                      old_sha: str, new_sha: str) -> str:
    checked = datetime.now(timezone.utc).isoformat()
    excerpt = text.strip()[:_EXCERPT_CHARS]
    # The excerpt is untrusted web content headed for a human review queue —
    # fence it so it renders as inert text, not as markdown/instructions.
    excerpt = excerpt.replace("```", "`‌``")
    return (
        "---\n"
        f'title: "Scout finding: {feed.node} changed"\n'
        f"tags: [scout, world-{world}]\n"
        "---\n\n"
        f"# Scout finding — {feed.node}\n\n"
        "The Librarian's horizon watch noticed a change at a source this "
        "World declares in its agenda. Approving this file admits the "
        "excerpt below into the knowledge base; rejecting it discards the "
        "finding. Nothing was installed, downloaded, or adopted.\n\n"
        f"- World: {world}\n"
        f"- Watch: {feed.node}\n"
        f"- Feed: {feed.url}\n"
        f"- Checked: {checked}\n"
        f"- Change: content {old_sha[:8]} → {new_sha[:8]}\n\n"
        f"## Excerpt (first {_EXCERPT_CHARS} characters, verbatim)\n\n"
        "```\n"
        f"{excerpt}\n"
        "```\n\n"
        f"Source: {feed.url}\n"
    )


def _write_finding(pkb_root: Path, world: str, feed: WatchFeed, text: str,
                   old_sha: str, new_sha: str) -> str:
    scout_dir = pkb_root / SCOUT_SUBDIR
    scout_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{world}-{_slugish(feed.node)}-{_slugish(feed.url)}"
    # Prune superseded, still-unreviewed findings for the same feed so the
    # queue holds one live finding per feed, not a pile-up.
    try:
        from arail import compiled_kb
        approved = compiled_kb.approved_paths(pkb_root)
    except Exception:  # noqa: BLE001 — pruning is best-effort
        approved = set()
    for old in scout_dir.glob(f"{stem}-*.md"):
        rel = old.relative_to(pkb_root).as_posix()
        if rel not in approved:
            old.unlink(missing_ok=True)
    path = scout_dir / f"{stem}-{new_sha[:8]}.md"
    path.write_text(_finding_markdown(world, feed, text, old_sha, new_sha))
    return path.relative_to(pkb_root).as_posix()


# ── consent bookkeeping ──────────────────────────────────────────────

def _ensure_consent(store, feed: WatchFeed, entry: Dict[str, Any]) -> str:
    """Resolve this feed's consent to approved|pending|denied, requesting
    once and never re-nagging a denial. The stored consent_id is the durable
    link to the operator's decision."""
    consent_id = entry.get("consent_id")
    if consent_id:
        if store.is_approved(consent_id):
            return "approved"
        if any(r.get("id") == consent_id for r in store.list_pending()):
            return "pending"
        return "denied"  # resolved but not approved — respect the no
    record = store.request_access(
        feed.url,
        f"World agenda watch: '{feed.node}' feed declared by the mounted World",
        agent="librarian-scout")
    entry["consent_id"] = record.get("id")
    if record.get("status") in ("approved", "auto_approved"):
        return "approved"
    return "pending"


# ── the tick ─────────────────────────────────────────────────────────

def tick(data_dir: Optional[Path] = None,
         pkb_root: Optional[Path] = None,
         now: Optional[float] = None) -> Dict[str, Any]:
    """One horizon-watch pass. Cheap no-op in airgapped mode or with no
    mounted World; otherwise checks each due, consented feed and stages
    change findings for review. Never raises for a watch failure."""
    if is_airgapped():
        return {"ok": True, "state": "inert_airgapped", "checked": 0, "findings": 0}

    from arail import world_mount as wm
    record = wm.current_mount()
    if record is None:
        return {"ok": True, "state": "no_world", "checked": 0, "findings": 0}
    world = record.world

    staged = Path(record.staged_dir)
    try:
        agenda = json.loads((staged / "agenda.json").read_text())
    except Exception:
        return {"ok": True, "state": "no_agenda", "checked": 0, "findings": 0}
    feeds = load_watches(agenda)
    if not feeds:
        return {"ok": True, "state": "no_url_feeds", "checked": 0, "findings": 0}

    if pkb_root is None:
        from arail.config import PKB_ROOT as pkb_root
    pkb_root = Path(pkb_root)

    from arail.agents.consent import ConsentStore
    store = ConsentStore()

    state_file = _state_path(data_dir)
    state = _load_state(state_file, world)
    t = now if now is not None else time.time()
    interval = _watch_interval_sec()

    checked = 0
    findings: List[str] = []
    pending_consent = 0
    for feed in feeds:
        entry = state["feeds"].setdefault(feed.url, {})
        last = entry.get("last_checked_ts")
        if last is not None and (t - float(last)) < interval:
            continue
        consent = _ensure_consent(store, feed, entry)
        entry["consent"] = consent
        if consent == "pending":
            pending_consent += 1
            continue
        if consent == "denied":
            continue

        ctx = scouting.ScoutContext(
            consent_id=entry["consent_id"],
            reason=f"world agenda watch: {feed.node}"[:200],
            fetcher=lambda url=feed.url: _fetch_text(url))
        result = scouting.check_watch(f"agenda-watch:{feed.node}", ctx)
        if result.state != "finding":
            _log.info("agenda_watch: %s → %s (%s)",
                      feed.url, result.state, result.message)
            if result.state == "inert_airgapped":
                break  # mode flipped mid-pass; stop touching the network
            entry["last_checked_ts"] = t
            continue

        checked += 1
        entry["last_checked_ts"] = t
        text = str(result.finding.get("watch_data") or "")
        new_sha = _sha(text)
        old_sha = entry.get("sha256")
        if old_sha is None:
            entry["sha256"] = new_sha        # first look = baseline, no finding
            continue
        if new_sha == old_sha:
            continue
        try:
            rel = _write_finding(pkb_root, world, feed, text, old_sha, new_sha)
            findings.append(rel)
            entry["sha256"] = new_sha
        except Exception as e:  # noqa: BLE001 — one bad write must not stop the pass
            _log.warning("agenda_watch: could not stage finding for %s: %s",
                         feed.url, e)

    _save_state(state_file, state)
    return {"ok": True, "state": "watched", "world": world, "checked": checked,
            "findings": len(findings), "finding_paths": findings,
            "pending_consent": pending_consent}
