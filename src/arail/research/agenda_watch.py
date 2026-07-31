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

Reading a finding, generically:
  • TEXT, NOT RAW BYTES — a fetched page's visible text (script/style/head
    stripped) is what gets hashed, diffed, and shown — not the raw HTTP body,
    so a rotating CSRF token or analytics build ID buried in markup no longer
    counts as "the page changed." Works identically for HTML, and passes
    plain text/JSON through unchanged (there's nothing to strip).
  • DIFF OVER FIRST-N — once a prior snapshot exists, a finding shows what
    actually changed (a bounded unified diff), not just the head of the new
    document. The very first look at a feed is a baseline: no finding, no
    diff possible yet, matching the original behavior.
  • RETAINED, NOT DELETED — a bounded number of unreviewed findings per feed
    are kept (oldest pruned first) instead of the previous single-slot
    behavior, so a person who checks in weekly doesn't lose every
    intermediate change to the last one.
  • WORLD-DECLARED EXTRACTION, STILL GENERIC — a World may ship an optional,
    seal-exempt ``scout-patterns.json`` sidecar declaring regex patterns to
    run over fetched text (e.g. an APR-percentage shape for a finance World,
    a driver-version shape for a games World). This module has zero
    knowledge of what any pattern means — it validates, bounds, and runs
    whatever the mounted World declares, and surfaces literal matched
    strings as "candidate values (code-extracted, unverified)" — never
    asserted as fact, never auto-applied anywhere, just made visible to the
    human reviewing the finding.

State lives at ``DATA_DIR/agenda-watch.json`` — per-user runtime, keyed to
the mounted World's slug, reset on a World switch (a different World has a
different horizon). Per-feed text snapshots (used for diffing) live
alongside it under ``DATA_DIR/agenda-watch/``.
"""

from __future__ import annotations

import difflib
import hashlib
import html.parser
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
SNAPSHOT_SUBDIR = "agenda-watch"
SCOUT_SUBDIR = "sources/scout"
SCOUT_PATTERNS_FILE = "scout-patterns.json"

_URL_RE = re.compile(r"^https?://\S+$")
_DEFAULT_WATCH_HOURS = 24.0
_FETCH_TIMEOUT_SEC = 20
_MAX_FETCH_BYTES = 512 * 1024
_EXCERPT_CHARS = 1500
_DIFF_CHARS = 2000
_MAX_UNREVIEWED_PER_FEED = 5

# World-declared extraction patterns (scout-patterns.json) are semi-trusted
# input — sealed alongside the World, but not code this module wrote. Bound
# everything defensively: a short regex-length cap plus the existing
# _MAX_FETCH_BYTES cap on the text being matched keeps a hostile or careless
# pattern's blast radius small without needing a full regex-safety analyzer.
_MAX_PATTERN_LEN = 200
_MAX_PATTERNS = 20
_MAX_PATTERN_MATCHES = 10


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


# ── text snapshots (for diffing) ────────────────────────────────────

def _slugish(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return s[:48] or "feed"


def _snapshot_path(data_dir: Path, world: str, feed: WatchFeed) -> Path:
    name = f"{world}-{_slugish(feed.node)}-{_slugish(feed.url)}.txt"
    return Path(data_dir) / SNAPSHOT_SUBDIR / name


def _read_snapshot(data_dir: Path, world: str, feed: WatchFeed) -> Optional[str]:
    try:
        return _snapshot_path(data_dir, world, feed).read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return None


def _write_snapshot(data_dir: Path, world: str, feed: WatchFeed, text: str) -> None:
    path = _snapshot_path(data_dir, world, feed)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# ── visible-text extraction (generic — no per-World knowledge) ─────────

class _TextExtractor(html.parser.HTMLParser):
    """Collects visible text, dropping script/style/head content. Plain
    text or JSON fed in has no tags to strip, so it passes through
    effectively unchanged — this is not an HTML-only code path."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._chunks: List[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:  # noqa: D401
        if tag in ("script", "style", "head"):
            self._skip_depth += 1

    def handle_startendtag(self, tag: str, attrs: Any) -> None:
        pass  # self-closing tags (<br/>, <meta/>) never carry visible text

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "head") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)


def _visible_text(raw: str) -> str:
    """Extract human-visible text from a fetched page. Generic across every
    World's feeds — no domain knowledge of what the text means, only how to
    strip non-visible markup. Never raises: malformed input falls back to
    the raw text rather than losing the fetch entirely."""
    try:
        parser = _TextExtractor()
        parser.feed(raw)
        parser.close()
        text = "".join(parser._chunks)
    except Exception:  # noqa: BLE001 — a parse hiccup must not sink the tick
        text = raw
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


# ── World-declared extraction patterns (optional, generic) ─────────────

def _load_scout_patterns(staged_dir: Path) -> List[Dict[str, Any]]:
    """Read and validate the mounted World's optional scout-patterns.json
    sidecar. Absent or malformed → empty list, logged, never raised — a
    typo in an authored sidecar must not break scouting for every feed."""
    path = staged_dir / SCOUT_PATTERNS_FILE
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        _log.warning("agenda_watch: %s is not valid JSON: %s", path, e)
        return []
    if not isinstance(doc, dict) or doc.get("schema") != "arail.scout-patterns/v1":
        _log.warning("agenda_watch: %s missing/unrecognized schema, ignoring", path)
        return []
    raw_patterns = doc.get("patterns")
    if not isinstance(raw_patterns, list):
        return []

    out: List[Dict[str, Any]] = []
    for p in raw_patterns[:_MAX_PATTERNS]:
        if not isinstance(p, dict):
            continue
        label = str(p.get("label") or "").strip()
        regex_src = str(p.get("regex") or "")
        if not label or not regex_src or len(regex_src) > _MAX_PATTERN_LEN:
            _log.warning("agenda_watch: skipping oversized/empty pattern in %s", path)
            continue
        try:
            compiled = re.compile(regex_src)
        except re.error as e:
            _log.warning("agenda_watch: skipping invalid regex %r: %s", regex_src, e)
            continue
        try:
            max_matches = int(p.get("max_matches", _MAX_PATTERN_MATCHES))
        except (TypeError, ValueError):
            max_matches = _MAX_PATTERN_MATCHES
        max_matches = max(1, min(max_matches, _MAX_PATTERN_MATCHES))
        out.append({"label": label, "regex": compiled, "max_matches": max_matches})
    return out


def _extract_candidates(text: str, patterns: List[Dict[str, Any]]
                         ) -> "Dict[str, List[str]]":
    """Run validated, bounded patterns over already-capped text. Returns
    literal matched substrings only — never a transformation, never a
    number the pattern didn't itself match verbatim."""
    candidates: Dict[str, List[str]] = {}
    for p in patterns:
        matches: List[str] = []
        for m in p["regex"].finditer(text):
            matches.append(m.group(0))
            if len(matches) >= p["max_matches"]:
                break
        if matches:
            candidates[p["label"]] = matches
    return candidates


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


def _finding_markdown(world: str, feed: WatchFeed, text: str,
                      old_sha: str, new_sha: str,
                      old_text: Optional[str],
                      candidates: "Dict[str, List[str]]") -> str:
    checked = datetime.now(timezone.utc).isoformat()

    if old_text is not None:
        diff_lines = list(difflib.unified_diff(
            old_text.splitlines(), text.splitlines(), lineterm=""))
        diff_body = "\n".join(diff_lines)[:_DIFF_CHARS]
        if not diff_body.strip():
            diff_body = "(no line-level differences detected in extracted text)"
        section_title = f"## Change (unified diff, first {_DIFF_CHARS} characters)"
        section_body = diff_body
    else:
        excerpt = text.strip()[:_EXCERPT_CHARS]
        note = "" if excerpt else " — no visible text extracted; the page may be JavaScript-rendered"
        section_title = f"## Excerpt (first {_EXCERPT_CHARS} characters of extracted text{note})"
        section_body = excerpt or "(empty)"

    # The excerpt/diff is untrusted web content headed for a human review
    # queue — fence it so it renders as inert text, not markdown/instructions.
    section_body = section_body.replace("```", "`‌``")

    candidates_section = ""
    if candidates:
        lines = [
            "## Candidate values (code-extracted, unverified)\n",
            "Literal substrings the mounted World's declared extraction "
            "patterns matched in the fetched text. These are not verified, "
            "not vetted, and not asserted as fact by any agent — a human "
            "must confirm before using one.\n",
        ]
        for label, values in candidates.items():
            fenced = ", ".join(f"`{v}`" for v in values)
            lines.append(f"- **{label}**: {fenced}")
        candidates_section = "\n".join(lines) + "\n\n"

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
        f"{candidates_section}"
        f"{section_title}\n\n"
        "```\n"
        f"{section_body}\n"
        "```\n\n"
        f"Source: {feed.url}\n"
    )


def _write_finding(pkb_root: Path, world: str, feed: WatchFeed, text: str,
                   old_sha: str, new_sha: str,
                   old_text: Optional[str],
                   candidates: "Dict[str, List[str]]") -> str:
    scout_dir = pkb_root / SCOUT_SUBDIR
    scout_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{world}-{_slugish(feed.node)}-{_slugish(feed.url)}"
    # Retain a bounded history of unreviewed findings per feed instead of
    # collapsing to one — a person who checks in weekly shouldn't lose every
    # intermediate change to only the latest. Approved findings are never
    # touched; only the oldest unreviewed ones are pruned once the cap
    # would otherwise be exceeded.
    try:
        from arail import compiled_kb
        approved = compiled_kb.approved_paths(pkb_root)
    except Exception:  # noqa: BLE001 — pruning is best-effort
        approved = set()
    unreviewed = [
        old for old in scout_dir.glob(f"{stem}-*.md")
        if old.relative_to(pkb_root).as_posix() not in approved
    ]
    unreviewed.sort(key=lambda p: p.stat().st_mtime)
    overflow = len(unreviewed) - (_MAX_UNREVIEWED_PER_FEED - 1)
    for old in unreviewed[:max(0, overflow)]:
        old.unlink(missing_ok=True)
    path = scout_dir / f"{stem}-{new_sha[:8]}.md"
    path.write_text(_finding_markdown(world, feed, text, old_sha, new_sha,
                                       old_text, candidates))
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

    patterns = _load_scout_patterns(staged)

    if pkb_root is None:
        from arail.config import PKB_ROOT as pkb_root
    pkb_root = Path(pkb_root)

    from arail.agents.consent import ConsentStore
    store = ConsentStore()

    state_file = _state_path(data_dir)
    data_dir_resolved = state_file.parent
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
        raw_text = str(result.finding.get("watch_data") or "")
        text = _visible_text(raw_text)
        new_sha = _sha(text)
        old_sha = entry.get("sha256")
        if old_sha is None:
            entry["sha256"] = new_sha        # first look = baseline, no finding
            _write_snapshot(data_dir_resolved, world, feed, text)
            continue
        if new_sha == old_sha:
            continue
        old_text = _read_snapshot(data_dir_resolved, world, feed)
        candidates = _extract_candidates(text, patterns)
        try:
            rel = _write_finding(pkb_root, world, feed, text, old_sha, new_sha,
                                  old_text, candidates)
            findings.append(rel)
            entry["sha256"] = new_sha
            _write_snapshot(data_dir_resolved, world, feed, text)
        except Exception as e:  # noqa: BLE001 — one bad write must not stop the pass
            _log.warning("agenda_watch: could not stage finding for %s: %s",
                         feed.url, e)

    _save_state(state_file, state)
    return {"ok": True, "state": "watched", "world": world, "checked": checked,
            "findings": len(findings), "finding_paths": findings,
            "pending_consent": pending_consent}
