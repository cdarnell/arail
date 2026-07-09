"""world_sources.wikipedia — build a World's initial dictionary from REAL
Wikipedia content (WK-3, the "sourced bootstrap").

Given a subject and a term budget (≤512), fetch the most common/important
terms for that subject via the MediaWiki + REST APIs, define them from real
article summaries (each carrying its canonical URL as ``source``), link them
into a closed related-graph, and return a spec+terms pair that
``world_forge.write_bundle`` seals into a **sourced** World.

Airgap: every network call happens inside ONE
``egress.allow_bootstrap_fetch`` scope — consent-gated (an approved
ConsentStore record), host-allowlisted to Wikipedia/Wikimedia, and audited
to lab/data/egress.jsonl. Outside that scope the airgap is unchanged.

Dependencies: ``requests`` + stdlib ``json`` only. Responses are JSON (the
MediaWiki API and the REST summary endpoint) — no HTML parsing.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from arail.egress import allow_bootstrap_fetch
from arail.world_forge import (
    assert_closed_sourced_graph,
    compute_provenance_tier,
    slugify,
)

_log = logging.getLogger(__name__)

API = "https://en.wikipedia.org/w/api.php"
REST_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
BOOTSTRAP_HOSTS = ["wikipedia.org", "wikimedia.org"]
_UA = "Arail/0.1 (world-forge sourced bootstrap)"
_TIMEOUT = 20
MAX_TERMS_CAP = 512

# Titles that are navigation/meta, not concepts.
_SKIP_PREFIXES = ("List of", "Index of", "Outline of", "Glossary of",
                  "Wikipedia:", "Template:", "Category:", "Portal:", "Help:",
                  "File:", "Draft:", "Module:")
_SKIP_SUBSTR = ("(disambiguation)",)


class BootstrapCancelled(Exception):
    """The operator cancelled the fetch mid-run."""


class BootstrapEmpty(Exception):
    """No usable terms were produced (bad subject / all summaries missing)."""


@dataclass
class BootstrapResult:
    spec: dict
    terms: list[dict]
    tier: str
    counts: dict
    stats: dict = field(default_factory=dict)


def _skip_title(title: str) -> bool:
    """True for navigation/meta titles that aren't real concepts."""
    if not title:
        return True
    if title.startswith(_SKIP_PREFIXES):
        return True
    return any(s in title for s in _SKIP_SUBSTR)


def _get(session, url: str, params: Optional[dict] = None, cancel=None) -> Optional[dict]:
    """One GET → parsed JSON, or None. Backs off once on 429/503, then skips.
    Cancellation is checked before the call."""
    if cancel is not None and cancel.is_set():
        raise BootstrapCancelled()
    for attempt in (1, 2):
        try:
            r = session.get(url, params=params, headers={"User-Agent": _UA}, timeout=_TIMEOUT)
        except Exception as e:  # noqa: BLE001
            _log.warning("wikipedia: request failed %s: %s", url, e)
            return None
        status = getattr(r, "status_code", 200)
        if status in (429, 503) and attempt == 1:
            time.sleep(2.0)
            continue
        if status != 200:
            return None
        try:
            return r.json()
        except Exception:  # noqa: BLE001
            return None
    return None


def _resolve_subject(session, subject: str, cancel) -> Optional[str]:
    """Subject string → canonical article title (top search hit)."""
    data = _get(session, API, {
        "action": "query", "list": "search", "srsearch": subject,
        "srlimit": 1, "format": "json", "maxlag": 5,
    }, cancel)
    try:
        hits = data["query"]["search"]
        return hits[0]["title"] if hits else None
    except Exception:  # noqa: BLE001
        return None


def _links_of(session, title: str, cancel, limit: int = 500) -> list[str]:
    """Namespace-0 outbound links of a page (paginated)."""
    out: list[str] = []
    cont: dict = {}
    while len(out) < limit:
        params = {"action": "query", "prop": "links", "titles": title,
                  "plnamespace": 0, "pllimit": 500, "format": "json", "maxlag": 5}
        params.update(cont)
        data = _get(session, API, params, cancel)
        if not data:
            break
        try:
            pages = data["query"]["pages"]
            for _pid, page in pages.items():
                for l in page.get("links", []):
                    t = l.get("title", "")
                    if t and not _skip_title(t):
                        out.append(t)
        except Exception:  # noqa: BLE001
            break
        cont = data.get("continue", {})
        if not cont:
            break
    return out


def _category_members(session, subject_title: str, cancel, limit: int = 300) -> list[str]:
    data = _get(session, API, {
        "action": "query", "list": "categorymembers",
        "cmtitle": f"Category:{subject_title}", "cmnamespace": 0,
        "cmlimit": min(limit, 500), "format": "json", "maxlag": 5,
    }, cancel)
    try:
        return [m["title"] for m in data["query"]["categorymembers"]
                if not _skip_title(m.get("title", ""))]
    except Exception:  # noqa: BLE001
        return []


def _summary(session, title: str, cancel) -> Optional[dict]:
    """REST summary for a title → {short, definition, source} or None."""
    from urllib.parse import quote
    data = _get(session, REST_SUMMARY + quote(title.replace(" ", "_"), safe=""), None, cancel)
    if not data or data.get("type") == "disambiguation":
        return None
    extract = str(data.get("extract", "")).strip()
    if not extract:
        return None
    desc = str(data.get("description", "")).strip()
    # short = the wikipedia one-line description, else first sentence
    short = desc or (extract.split(". ")[0][:200])
    try:
        url = data["content_urls"]["desktop"]["page"]
    except Exception:  # noqa: BLE001
        url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
    return {"short": short[:200], "definition": extract[:600], "source": url}


def bootstrap_subject(
    subject: str,
    max_terms: int,
    *,
    consent_id: str,
    progress_cb: Optional[Callable[[str, int, int, str], None]] = None,
    cancel: Optional[threading.Event] = None,
    session: Any = None,
) -> BootstrapResult:
    """Build a sourced World dictionary for ``subject`` from Wikipedia.

    All network I/O runs inside the consent-gated bootstrap-fetch scope.
    """
    subject = (subject or "").strip()
    if not subject:
        raise BootstrapEmpty("empty subject")
    budget = max(4, min(int(max_terms), MAX_TERMS_CAP))
    if session is None:
        import requests
        session = requests.Session()

    def prog(stage: str, done: int, total: int, note: str = "") -> None:
        if progress_cb:
            try:
                progress_cb(stage, done, total, note)
            except Exception:  # noqa: BLE001
                pass

    t0 = time.monotonic()
    calls = {"n": 0}

    with allow_bootstrap_fetch(
        f"world-bootstrap: {subject[:80]}", BOOTSTRAP_HOSTS, consent_id=consent_id,
    ):
        # 1. RESOLVE
        prog("resolve", 0, 1, subject)
        title = _resolve_subject(session, subject, cancel)
        calls["n"] += 1
        if not title:
            raise BootstrapEmpty(f"could not resolve a Wikipedia page for {subject!r}")
        prog("resolve", 1, 1, title)

        # 2. HARVEST candidate titles: subject-page links + category members,
        #    ranked by how often they appear across the pools (a link that
        #    shows up in both the page body and the category is more central).
        prog("harvest", 0, budget, "gathering candidates")
        pool: dict[str, int] = {}
        for t in _links_of(session, title, cancel, limit=max(budget * 3, 150)):
            pool[t] = pool.get(t, 0) + 2      # body links weighted higher
        calls["n"] += 1
        for t in _category_members(session, title, cancel):
            pool[t] = pool.get(t, 0) + 1
        calls["n"] += 1
        pool.pop(title, None)
        ranked = sorted(pool, key=lambda k: (-pool[k], k))[:budget]
        if not ranked:
            # last resort: the subject page itself is at least one real term
            ranked = [title]
        prog("harvest", len(ranked), budget, f"{len(ranked)} candidates")

        # 3. DEFINE via REST summaries (serial; each carries a real URL source)
        terms: list[dict] = []
        by_title_slug: dict[str, str] = {}
        for i, cand in enumerate(ranked):
            if cancel is not None and cancel.is_set():
                raise BootstrapCancelled()
            summ = _summary(session, cand, cancel)
            calls["n"] += 1
            prog("define", i + 1, len(ranked), cand)
            if not summ:
                continue
            slug = slugify(cand)
            if not slug or slug in by_title_slug.values():
                continue
            by_title_slug[cand] = slug
            terms.append({
                "slug": slug, "term": cand, "category": "core-concepts",
                "short": summ["short"], "definition": summ["definition"],
                "example": "", "related": [], "source": summ["source"],
            })
        if not terms:
            raise BootstrapEmpty("no article summaries were available for the harvested terms")

        # 4. CATEGORIZE — v1: one honest bucket. (Section-based clustering is a
        #    follow-up; a single sourced category is truthful and gate-valid.)
        categories = [{"id": "core-concepts", "label": f"{title}: Core Concepts"}]

        # 5. LINK: related edges = links among the SELECTED terms only (closed).
        prog("link", 0, len(terms), "linking")
        slug_set = {t["slug"] for t in terms}
        title_to_slug = by_title_slug
        for i, t in enumerate(terms):
            if cancel is not None and cancel.is_set():
                raise BootstrapCancelled()
            links = _links_of(session, t["term"], cancel, limit=200)
            calls["n"] += 1
            rel: list[str] = []
            for lt in links:
                ls = title_to_slug.get(lt, "")
                if ls and ls in slug_set and ls != t["slug"] and ls not in rel:
                    rel.append(ls)
                if len(rel) >= 6:
                    break
            t["related"] = rel
            prog("link", i + 1, len(terms), "")

    # (scope closed — airgap restored)

    # 6. GATE + provenance
    prog("gate", 0, 1, "sealing")
    declared = {c["id"] for c in categories}
    gate = assert_closed_sourced_graph(terms, declared)
    # closed-by-construction, but drop any stragglers defensively
    if not gate.ok:
        present = {t["slug"] for t in terms}
        for t in terms:
            t["related"] = [r for r in t["related"] if r in present and r != t["slug"]]
    tier, counts = compute_provenance_tier([t["source"] for t in terms])
    prog("gate", 1, 1, f"{len(terms)} terms · {tier}")

    slug = slugify(subject)[:48] or slugify(title)[:48]
    display = title
    spec = {
        "_bootstrap_notice": (
            f"SOURCED from Wikipedia for '{subject}' (consent {consent_id}). "
            "Each term cites its article URL."
        ),
        "slug": slug,
        "display_name": display,
        "categories": categories,
        "knowledge_sources": [
            {"kind": "url", "ref": "https://en.wikipedia.org/", "trust": "primary"}
        ],
    }
    avg_edges = round(sum(len(t["related"]) for t in terms) / max(1, len(terms)), 2)
    return BootstrapResult(
        spec=spec, terms=terms, tier=tier, counts=counts,
        stats={"calls": calls["n"], "elapsed_s": round(time.monotonic() - t0, 1),
               "avg_edges": avg_edges, "term_count": len(terms)},
    )
