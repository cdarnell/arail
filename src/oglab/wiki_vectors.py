"""Optional LanceDB helpers for wiki semantic associations.

This module is intentionally optional: if LanceDB is not installed,
callers should treat the returned edge list as empty and continue.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from pathlib import Path
from typing import Any


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_\-/]{2,}")
_VECTOR_DIM = 128
_TABLE_NAME = "wiki_nodes"


def _hash_embedding(text: str, dim: int = _VECTOR_DIM) -> list[float]:
    """Deterministic sparse embedding used as a local fallback.

    We hash tokens into a fixed vector space and L2-normalize. This is
    lightweight and fully offline; LanceDB handles nearest-neighbor lookups.
    """
    vec = [0.0] * dim
    toks = _TOKEN_RE.findall((text or "").lower())
    if not toks:
        return vec

    for tok in toks:
        h = hashlib.sha1(tok.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "little") % dim
        sign = 1.0 if (h[4] & 1) == 0 else -1.0
        vec[idx] += sign

    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0:
        return vec
    return [v / norm for v in vec]


def _enabled() -> bool:
    return os.getenv("WIKI_SEMANTIC_EDGES", "1").lower() not in {
        "0", "false", "off", "no"
    }


def semantic_edges_for_pages(
    pages: dict[str, Any],
    pkb_root: Path,
    *,
    k: int = 3,
    min_score: float = 0.22,
    max_edges: int = 300,
) -> list[dict[str, Any]]:
    """Build semantic-association edges using a local LanceDB index.

    Returns edges in graph format: {source,target,type,label,score}.
    """
    if not _enabled() or len(pages) < 3:
        return []

    try:
        import lancedb  # type: ignore[import-not-found]
    except Exception:
        return []

    cache_dir = pkb_root / ".wiki-cache" / "lancedb"
    cache_dir.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(cache_dir))

    rows: list[dict[str, Any]] = []
    for slug, page in pages.items():
        text = "\n".join([
            page.title,
            " ".join(page.tags or []),
            (page.body_md or "")[:1800],
        ])
        rows.append({
            "slug": slug,
            "section": page.section,
            "title": page.title,
            "vector": _hash_embedding(text),
        })

    # Rebuild per compile for consistency with current PKB state.
    try:
        table = db.create_table(_TABLE_NAME, data=rows, mode="overwrite")
    except TypeError:
        # Compatibility with older LanceDB versions that may not support
        # mode="overwrite".
        if _TABLE_NAME in db.table_names():
            try:
                db.drop_table(_TABLE_NAME)
            except Exception:
                pass
        table = db.create_table(_TABLE_NAME, data=rows)

    results: list[dict[str, Any]] = []
    seen_undirected: set[tuple[str, str]] = set()

    for row in rows:
        slug = row["slug"]
        slug_escaped = slug.replace("'", "''")
        try:
            hits = (
                table.search(row["vector"])
                .where(f"slug != '{slug_escaped}'")
                .limit(max(1, k))
                .to_list()
            )
        except Exception:
            continue

        for hit in hits:
            target = hit.get("slug")
            if not target or target == slug:
                continue

            dist = float(hit.get("_distance", 1.0))
            score = max(0.0, 1.0 - dist)
            if score < min_score:
                continue

            a, b = sorted((slug, target))
            pair = (a, b)
            if pair in seen_undirected:
                continue
            seen_undirected.add(pair)

            results.append({
                "source": slug,
                "target": target,
                "type": "semantic",
                "label": "semantic",
                "score": round(score, 3),
            })
            if len(results) >= max_edges:
                return results

    return results
