"""
Adapters turn raw inputs from around the lab into normalized Source
records. Each adapter is a pure function: input -> Source. No I/O beyond
reading the input file (adapters don't embed, don't write to storage —
that's the store's job).

Adding a new source type = writing one adapter here + adding its kind
to the Literal in models/source.py.
"""
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import frontmatter

from app.models.source import Source, IngestRequest


def source_id(uri: str) -> str:
    """Deterministic ID from URI. Re-ingesting the same URI updates in place."""
    return hashlib.sha1(uri.encode()).hexdigest()[:16]


# --------------------------------------------------------------------
# Markdown (user notes, lab-generated notes)
# --------------------------------------------------------------------
def md_adapter(path: str) -> Source:
    p = Path(path)
    raw = p.read_text(encoding="utf-8", errors="ignore")
    fm = frontmatter.loads(raw)
    tags = fm.get("tags", []) or []
    if isinstance(tags, str):
        tags = [tags]
    return Source(
        id=source_id(str(p.resolve())),
        kind="markdown",
        title=fm.get("title") or p.stem,
        uri=str(p.resolve()),
        body_excerpt=fm.content[:4000],
        tags=list(tags),
        year=fm.get("year"),
        author=fm.get("author"),
        domain=fm.get("domain"),
        meta={"frontmatter": {k: v for k, v in fm.metadata.items()
                              if k not in {"tags", "title", "year", "author", "domain"}}},
        ingested_by="user",
    )


# --------------------------------------------------------------------
# API snapshot — e.g., a USDA Quickstats pull the Data Curator made
# --------------------------------------------------------------------
def api_adapter(snapshot: dict[str, Any]) -> Source:
    """
    Expects: {
      "source_name": "USDA NASS Quickstats",
      "endpoint": "https://...",
      "query": {...},
      "data": {...},            # the actual returned data
      "retrieved_at": "2026-04-20T..."
    }
    """
    uri = f"{snapshot['source_name']}::{snapshot.get('endpoint','')}::{hash_query(snapshot.get('query',{}))}"
    excerpt = _summarize_data(snapshot.get("data", {}))
    return Source(
        id=source_id(uri),
        kind="api_snapshot",
        title=f"{snapshot['source_name']} — {_query_summary(snapshot.get('query', {}))}",
        uri=uri,
        body_excerpt=excerpt,
        tags=snapshot.get("tags", []) + ["api", snapshot["source_name"].lower().replace(" ", "-")],
        year=snapshot.get("year"),
        domain=snapshot.get("domain"),
        meta={
            "endpoint": snapshot.get("endpoint"),
            "query": snapshot.get("query"),
            "retrieved_at": snapshot.get("retrieved_at", datetime.utcnow().isoformat()),
        },
        ingested_by="curator",
    )


# --------------------------------------------------------------------
# Paper — arXiv/semantic-scholar style
# --------------------------------------------------------------------
def paper_adapter(meta: dict[str, Any]) -> Source:
    uri = meta.get("doi") or meta.get("arxiv_id") or meta.get("url") or meta["title"]
    year = meta.get("year")
    if not year and meta.get("published"):
        try:
            year = int(meta["published"][:4])
        except (ValueError, TypeError):
            pass
    return Source(
        id=source_id(str(uri)),
        kind="paper",
        title=meta["title"],
        uri=str(uri),
        body_excerpt=meta.get("abstract", "")[:4000],
        tags=meta.get("tags", []) + (meta.get("categories") or []),
        year=year,
        author=", ".join(meta.get("authors", []))[:200] if meta.get("authors") else None,
        domain=meta.get("domain"),
        meta={"venue": meta.get("venue"), "doi": meta.get("doi"),
              "arxiv_id": meta.get("arxiv_id"), "url": meta.get("url")},
        ingested_by=meta.get("ingested_by", "curator"),
    )


# --------------------------------------------------------------------
# Web page — agent dropped a URL with scraped content
# --------------------------------------------------------------------
def web_adapter(page: dict[str, Any]) -> Source:
    return Source(
        id=source_id(page["url"]),
        kind="web_page",
        title=page.get("title") or page["url"],
        uri=page["url"],
        body_excerpt=(page.get("text") or "")[:4000],
        tags=page.get("tags", []) + ["web"],
        domain=page.get("domain"),
        meta={"fetched_at": page.get("fetched_at", datetime.utcnow().isoformat()),
              "host": _host_of(page["url"])},
        ingested_by=page.get("ingested_by", "agent"),
    )


# --------------------------------------------------------------------
# Dataset — CSV/Parquet with a metadata card
# --------------------------------------------------------------------
def dataset_adapter(card: dict[str, Any]) -> Source:
    """
    Expects a dataset card: {
      "name", "path_or_url", "schema", "row_count", "description", "license"
    }
    """
    uri = card["path_or_url"]
    schema_summary = ", ".join(f"{c['name']}:{c['type']}" for c in card.get("schema", []))
    excerpt = (
        f"{card.get('description', '')}\n\n"
        f"Rows: {card.get('row_count', 'unknown')}\n"
        f"Schema: {schema_summary}\n"
        f"License: {card.get('license', 'unspecified')}"
    )[:4000]
    return Source(
        id=source_id(uri),
        kind="dataset",
        title=card["name"],
        uri=uri,
        body_excerpt=excerpt,
        tags=card.get("tags", []) + ["dataset"],
        domain=card.get("domain"),
        meta={"schema": card.get("schema"), "row_count": card.get("row_count"),
              "license": card.get("license")},
        ingested_by=card.get("ingested_by", "curator"),
    )


# --------------------------------------------------------------------
# Experiment log — output of Experiment Tracker skill
# --------------------------------------------------------------------
def experiment_adapter(exp: dict[str, Any]) -> Source:
    uri = f"experiment::{exp['id']}"
    excerpt = (
        f"Hypothesis: {exp.get('hypothesis', '')}\n\n"
        f"Method: {exp.get('methodology', '')}\n\n"
        f"Results: {_fmt_results(exp.get('results', {}))}"
    )[:4000]
    return Source(
        id=source_id(uri),
        kind="experiment_log",
        title=exp.get("title") or exp.get("hypothesis", "Experiment")[:80],
        uri=uri,
        body_excerpt=excerpt,
        tags=exp.get("tags", []) + ["experiment"],
        year=_year_from(exp.get("completed_at") or exp.get("started_at")),
        domain=exp.get("domain"),
        meta={"status": exp.get("status"), "metrics": exp.get("metrics"),
              "goal_id": exp.get("goal_id")},
        ingested_by="experiment",
    )


# --------------------------------------------------------------------
# Image — soil photo, chart, diagram
# --------------------------------------------------------------------
def image_adapter(meta: dict[str, Any]) -> Source:
    """Caption + tags carry the semantic signal. Actual pixels stay on disk."""
    return Source(
        id=source_id(meta["path"]),
        kind="image",
        title=meta.get("title") or Path(meta["path"]).stem,
        uri=meta["path"],
        body_excerpt=meta.get("caption", "")[:4000],
        tags=meta.get("tags", []) + ["image"],
        domain=meta.get("domain"),
        meta={"width": meta.get("width"), "height": meta.get("height")},
        ingested_by=meta.get("ingested_by", "user"),
    )


# --------------------------------------------------------------------
# Generic dispatcher — used by the ingest endpoint
# --------------------------------------------------------------------
def adapt(req: IngestRequest) -> Source:
    """Build a Source directly from an IngestRequest (already normalized)."""
    return Source(
        id=source_id(req.uri),
        kind=req.kind,
        title=req.title,
        uri=req.uri,
        body_excerpt=req.body_excerpt[:4000],
        tags=req.tags,
        year=req.year,
        author=req.author,
        domain=req.domain,
        meta=req.meta,
        ingested_by=req.ingested_by,
    )


# --------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------
def hash_query(q: dict) -> str:
    return hashlib.sha1(repr(sorted(q.items())).encode()).hexdigest()[:8]


def _query_summary(q: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in list(q.items())[:3]) or "snapshot"


def _summarize_data(data: Any) -> str:
    if isinstance(data, list) and data:
        return f"{len(data)} records. First: {str(data[0])[:500]}"
    if isinstance(data, dict):
        keys = list(data.keys())[:10]
        return f"Keys: {keys}. Sample: {str(data)[:500]}"
    return str(data)[:1000]


def _fmt_results(r: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in r.items()) if r else "(pending)"


def _year_from(dt: Any) -> int | None:
    if not dt:
        return None
    s = str(dt)
    m = re.match(r"(\d{4})", s)
    return int(m.group(1)) if m else None


def _host_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1) if m else ""
