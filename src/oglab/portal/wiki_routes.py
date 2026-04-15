"""OGLab Wiki — FastAPI router.

Registered in ``portal/app.py`` as ``app.include_router(wiki_router)``.
Kept in its own module so the wiki feature can be stripped by a fork
that wants to ship without it — just delete this file and remove the
one include line.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from oglab import wiki
from oglab.activity import activity_log
from oglab.config import PKM_ROOT

_log = logging.getLogger(__name__)

router = APIRouter()

_PORTAL_DIR = Path(__file__).parent
_templates = Jinja2Templates(directory=_PORTAL_DIR / "templates")


# ── Helpers ─────────────────────────────────────────────────────────────

def _load_or_build() -> dict[str, Any]:
    """Load the manifest, kicking off a build if it's missing."""
    return wiki.load_manifest(PKM_ROOT)


def _repo_root() -> Path | None:
    """Locate the repo root by walking up from src/oglab/portal/ to a
    directory that contains ``pyproject.toml``. Returns None if not
    found so docgen stays optional."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return None


# ── HTML pages ──────────────────────────────────────────────────────────

@router.get("/wiki", response_class=HTMLResponse)
async def wiki_landing(request: Request):
    manifest = _load_or_build()
    pages = manifest.get("pages", {})

    sections: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    for p in pages.values():
        sec = p.get("section", "other")
        sections[sec] = sections.get(sec, 0) + 1
        for t in p.get("tags", []):
            tag_counts[t] = tag_counts.get(t, 0) + 1

    recent = sorted(pages.values(), key=lambda p: p.get("modified", 0), reverse=True)[:12]
    tags_sorted = sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))

    link_count = sum(len(p.get("outgoing", [])) for p in pages.values())

    return _templates.TemplateResponse(request, "wiki/landing.html", {
        "page_count": len(pages),
        "link_count": link_count,
        "tag_count": len(tag_counts),
        "built_at": manifest.get("built_at", ""),
        "sections": sections,
        "recent_pages": recent,
        "tags": tags_sorted,
    })


@router.get("/wiki/graph", response_class=HTMLResponse)
async def wiki_graph_page(request: Request):
    return _templates.TemplateResponse(request, "wiki/graph.html")


@router.get("/wiki/tag/{tag}", response_class=HTMLResponse)
async def wiki_tag_page(request: Request, tag: str):
    manifest = _load_or_build()
    pages = manifest.get("pages", {})
    matching = [p for p in pages.values() if tag in p.get("tags", [])]
    matching.sort(key=lambda p: p.get("title", ""))
    return _templates.TemplateResponse(request, "wiki/landing.html", {
        "page_count": len(matching),
        "link_count": 0,
        "tag_count": 1,
        "built_at": manifest.get("built_at", ""),
        "sections": {f"tag: {tag}": len(matching)},
        "recent_pages": matching,
        "tags": [(tag, len(matching))],
    })


@router.get("/wiki/search", response_class=HTMLResponse)
async def wiki_search_page(request: Request, q: str = ""):
    if not q:
        return await wiki_landing(request)
    manifest = _load_or_build()
    pages = manifest.get("pages", {})
    q_lower = q.lower()
    matches = [
        p for p in pages.values()
        if q_lower in p.get("title", "").lower()
        or q_lower in p.get("body_md", "").lower()
        or any(q_lower in t for t in p.get("tags", []))
    ]
    matches.sort(key=lambda p: p.get("title", ""))
    return _templates.TemplateResponse(request, "wiki/landing.html", {
        "page_count": len(matches),
        "link_count": 0,
        "tag_count": 0,
        "built_at": manifest.get("built_at", ""),
        "sections": {f"search: {q}": len(matches)},
        "recent_pages": matches,
        "tags": [],
    })


@router.get("/wiki/{slug:path}", response_class=HTMLResponse)
async def wiki_page(request: Request, slug: str):
    # ``slug:path`` eats everything, including our other /wiki/... pages —
    # let them win first.
    if slug in ("", "graph") or slug.startswith(("tag/", "search", "new")):
        raise HTTPException(404)

    manifest = _load_or_build()
    pages = manifest.get("pages", {})
    page = pages.get(slug)
    if not page:
        # Fall back to title match for friendlier URLs.
        for candidate in pages.values():
            if wiki.slugify(candidate.get("title", "")) == slug:
                page = candidate
                break
    if not page:
        raise HTTPException(404, detail=f"Wiki page not found: {slug}")

    # Rebuild Page objects once so we can render the body with wikilinks.
    page_objs: dict[str, wiki.Page] = {}
    for s, p in pages.items():
        page_objs[s] = wiki.Page(
            slug=s,
            title=p.get("title", s),
            path=Path(p.get("path", "")),
            section=p.get("section", ""),
            tags=p.get("tags", []),
            aliases=p.get("aliases", []),
            outgoing=p.get("outgoing", []),
            backlinks=p.get("backlinks", []),
            source_ref=p.get("source_ref"),
            body_md=p.get("body_md", ""),
            modified=p.get("modified", 0.0),
        )
    rendered = wiki.render_page(page_objs[page["slug"]], page_objs)

    backlink_pages = [
        {"slug": s, "title": pages[s].get("title", s)}
        for s in page.get("backlinks", [])
        if s in pages
    ]
    outgoing_pages = [
        {"slug": s, "title": pages[s].get("title", s)}
        for s in page.get("outgoing", [])
        if s in pages
    ]

    neighborhood_slugs = set(page.get("outgoing", [])) | set(page.get("backlinks", []))
    graph = manifest.get("graph", {})
    neighborhood_nodes = [
        n for n in graph.get("nodes", []) if n.get("id") in neighborhood_slugs
    ]

    return _templates.TemplateResponse(request, "wiki/page.html", {
        "page": page,
        "rendered_html": rendered,
        "backlinks": backlink_pages,
        "outgoing": outgoing_pages,
        "neighborhood_nodes": neighborhood_nodes,
    })


# ── JSON API ────────────────────────────────────────────────────────────

@router.get("/api/wiki/pages")
async def api_pages():
    manifest = _load_or_build()
    pages = manifest.get("pages", {})
    return [
        {
            "slug": p["slug"],
            "title": p.get("title", p["slug"]),
            "section": p.get("section", ""),
            "tags": p.get("tags", []),
            "backlinks": len(p.get("backlinks", [])),
            "outgoing": len(p.get("outgoing", [])),
        }
        for p in pages.values()
    ]


@router.get("/api/wiki/page/{slug:path}")
async def api_page(slug: str):
    manifest = _load_or_build()
    pages = manifest.get("pages", {})
    page = pages.get(slug)
    if not page:
        raise HTTPException(404)
    return page


@router.get("/api/wiki/graph")
async def api_graph():
    manifest = _load_or_build()
    return manifest.get("graph", {"nodes": [], "edges": []})


@router.get("/api/wiki/search")
async def api_search(q: str = ""):
    manifest = _load_or_build()
    pages = manifest.get("pages", {})
    if not q:
        return []
    q_lower = q.lower()
    results = []
    for p in pages.values():
        score = 0
        if q_lower in p.get("title", "").lower():
            score += 3
        if any(q_lower in t for t in p.get("tags", [])):
            score += 2
        if q_lower in p.get("body_md", "").lower():
            score += 1
        if score:
            results.append({
                "slug": p["slug"],
                "title": p.get("title"),
                "section": p.get("section"),
                "score": score,
            })
    results.sort(key=lambda r: -r["score"])
    return results[:40]


@router.post("/api/wiki/rebuild")
async def api_rebuild():
    try:
        repo = _repo_root()
        result = wiki.compile_wiki(PKM_ROOT, repo_root=repo)
    except Exception as e:  # noqa: BLE001
        _log.exception("wiki rebuild failed")
        activity_log.emit("wiki", f"Rebuild failed: {e}", "error")
        return JSONResponse({"error": str(e)}, status_code=500)

    activity_log.emit(
        "wiki",
        f"Wiki rebuilt: {result.page_count} pages, "
        f"{result.link_count} links, "
        f"{result.tag_count} tags ({result.elapsed_ms} ms)",
        "success",
    )
    return {
        "page_count": result.page_count,
        "link_count": result.link_count,
        "tag_count": result.tag_count,
        "elapsed_ms": result.elapsed_ms,
    }
