"""Arail PKM — Personal Knowledge Management for your lab.

Three operations:
  ingest  — process inbox/ into sources/
  compile — merge sources/ + agents/ + notes/ → compiled/ + index.md
  browse  — search and list the knowledge base
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _pkb_root() -> Path:
    """Resolve PKM root via central config (honors LAB_PKM env)."""
    from arail.config import PKB_ROOT
    return PKB_ROOT


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _date_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Ingest ───────────────────────────────────────────────────────────────

# Extension → target subfolder under sources/
_EXT_MAP = {
    ".pdf":  "papers",
    ".epub": "papers",
    ".csv":  "datasets",
    ".tsv":  "datasets",
    ".json": "datasets",
    ".jsonl": "datasets",
    ".parquet": "datasets",
    ".md":   "articles",
    ".txt":  "articles",
    ".html": "articles",
    ".htm":  "articles",
    ".rst":  "articles",
    # Images — screenshots, diagrams, scans — land in sources/images so
    # the reader can render them inline instead of choking on the bytes.
    ".png":  "images",
    ".jpg":  "images",
    ".jpeg": "images",
    ".gif":  "images",
    ".webp": "images",
    ".svg":  "images",
    ".bmp":  "images",
    ".avif": "images",
    ".heic": "images",
    # Video — screencasts, recorded demos. Raw bytes served by
    # /api/pkb/raw; inline playback still needs a <video> element in
    # the reader, which is a follow-up.
    ".mp4":  "videos",
    ".mov":  "videos",
    ".webm": "videos",
    ".mkv":  "videos",
    ".m4v":  "videos",
    # Audio — interviews, podcasts, voice memos.
    ".mp3":  "audio",
    ".wav":  "audio",
    ".m4a":  "audio",
    ".ogg":  "audio",
    ".flac": "audio",
    ".aac":  "audio",
}


def ingest(pkb_root: Path | None = None) -> dict[str, Any]:
    """Process everything in inbox/ → sources/.

    Returns a summary dict of actions taken. ``destinations`` maps the
    original inbox filename to the post-ingest path (relative to the
    PKB root) for every file that moved — callers can use it to build
    "Open" links pointing at the file's final location.
    """
    root = pkb_root or _pkb_root()
    inbox = root / "inbox"
    if not inbox.exists():
        return {"moved": 0, "urls_fetched": 0, "errors": [], "destinations": {}}

    moved = 0
    urls_fetched = 0
    errors: list[str] = []
    destinations: dict[str, str] = {}

    # Process links.txt (URL bookmarks dropped in inbox)
    links_file = inbox / "links.txt"
    if links_file.exists():
        bookmarks = root / "sources" / "bookmarks.md"
        try:
            lines = links_file.read_text().strip().splitlines()
            with open(bookmarks, "a") as f:
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        f.write(f"{line}\n")
                        urls_fetched += 1
            links_file.unlink()
        except OSError as e:
            errors.append(f"links.txt: {e}")

    # Process quick.txt (quick notes → journal)
    quick_file = inbox / "quick.txt"
    if quick_file.exists():
        journal = root / "notes" / "journal.md"
        try:
            quick_text = quick_file.read_text().strip()
            if quick_text:
                with open(journal, "r+") as f:
                    content = f.read()
                    f.seek(0)
                    # Insert after the header block
                    header_end = content.find("---\n")
                    if header_end >= 0:
                        insert_at = header_end + 4
                        new_content = (
                            content[:insert_at] + "\n"
                            + f"## {_date_prefix()}\n\n{quick_text}\n\n"
                            + content[insert_at:]
                        )
                    else:
                        new_content = content + f"\n## {_date_prefix()}\n\n{quick_text}\n"
                    f.write(new_content)
                    f.truncate()
            quick_file.unlink()
            moved += 1
        except OSError as e:
            errors.append(f"quick.txt: {e}")

    # Process all other files by extension
    for item in sorted(inbox.iterdir()):
        if item.name.startswith(".") or item.name in ("links.txt", "quick.txt"):
            continue
        if item.is_file():
            ext = item.suffix.lower()
            subfolder = _EXT_MAP.get(ext, "articles")  # default to articles
            dest_dir = root / "sources" / subfolder
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_name = f"{_date_prefix()}_{item.name}"
            dest = dest_dir / dest_name
            try:
                shutil.move(str(item), str(dest))
                moved += 1
                destinations[item.name] = dest.relative_to(root).as_posix()
            except OSError as e:
                errors.append(f"{item.name}: {e}")

    return {
        "moved": moved,
        "urls_fetched": urls_fetched,
        "errors": errors,
        "destinations": destinations,
    }


# ── Compile ──────────────────────────────────────────────────────────────

def _collect_tags(text: str) -> list[str]:
    """Extract #hashtags from text."""
    return sorted(set(re.findall(r"#(\w[\w-]*)", text)))


def _collect_stars(text: str) -> list[str]:
    """Extract ⭐-prefixed lines."""
    return [line.strip() for line in text.splitlines()
            if line.strip().startswith("⭐")]


def _scan_tree(folder: Path) -> list[dict[str, Any]]:
    """Walk a folder, returning metadata for each markdown/text file."""
    entries: list[dict[str, Any]] = []
    if not folder.exists():
        return entries
    for p in sorted(folder.rglob("*")):
        if p.is_file() and p.suffix in (".md", ".txt", ".rst"):
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            stat = p.stat()
            entries.append({
                "path": str(p),
                "rel": str(p.relative_to(folder.parent.parent)),  # relative to pkm root
                "name": p.stem,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                            .strftime("%Y-%m-%d %H:%M"),
                "size": stat.st_size,
                "lines": text.count("\n") + 1,
                "tags": _collect_tags(text),
                "stars": _collect_stars(text),
                "preview": text[:200].replace("\n", " ").strip(),
            })
    return entries


def compile_index(pkb_root: Path | None = None) -> dict[str, Any]:
    """Build index.md at the PKM root. Returns compile stats."""
    root = pkb_root or _pkb_root()
    sections = {
        "sources": root / "sources",
        "agents": root / "agents",
        "notes": root / "notes",
        "inference": root / "inference",
        "compiled": root / "compiled",
    }

    all_entries: list[dict[str, Any]] = []
    section_stats: dict[str, int] = {}
    all_tags: set[str] = set()
    all_stars: list[str] = []

    for name, folder in sections.items():
        entries = _scan_tree(folder)
        section_stats[name] = len(entries)
        for e in entries:
            all_tags.update(e["tags"])
            all_stars.extend(e["stars"])
            e["section"] = name
        all_entries.extend(entries)

    # Build index.md
    lines = [
        "# Knowledge Index",
        "",
        f"*Auto-generated by `pkm-compile` — {_ts()} UTC*",
        "",
        f"**Total items:** {len(all_entries)}  ",
        f"**Sources:** {section_stats.get('sources', 0)} · "
        f"**Agent work:** {section_stats.get('agents', 0)} · "
        f"**Notes:** {section_stats.get('notes', 0)} · "
        f"**Inference:** {section_stats.get('inference', 0)} · "
        f"**Compiled:** {section_stats.get('compiled', 0)}",
        "",
    ]

    # Tags cloud
    if all_tags:
        lines.append("## Tags")
        lines.append("")
        lines.append(" ".join(f"`#{t}`" for t in sorted(all_tags)))
        lines.append("")

    # Starred items
    if all_stars:
        lines.append("## Starred")
        lines.append("")
        for s in all_stars[:20]:
            lines.append(f"- {s}")
        lines.append("")

    # Recent changes (top 15)
    recent = sorted(all_entries, key=lambda e: e["modified"], reverse=True)[:15]
    if recent:
        lines.append("## Recent")
        lines.append("")
        for e in recent:
            lines.append(f"- `{e['modified']}` **{e['section']}/** [{e['name']}]({e['rel']})")
        lines.append("")

    # Full catalog by section
    for name in ("sources", "agents", "notes", "inference", "compiled"):
        section_entries = [e for e in all_entries if e["section"] == name]
        if not section_entries:
            continue
        lines.append(f"## {name.title()}")
        lines.append("")
        for e in section_entries:
            tag_str = " ".join(f"`#{t}`" for t in e["tags"][:5]) if e["tags"] else ""
            lines.append(f"- [{e['name']}]({e['rel']}) — {e['lines']} lines {tag_str}")
        lines.append("")

    index_path = root / "index.md"
    index_path.write_text("\n".join(lines))

    return {
        "total": len(all_entries),
        "sections": section_stats,
        "tags": sorted(all_tags),
        "starred": len(all_stars),
        "index_path": str(index_path),
    }


# ── Browse / Search ──────────────────────────────────────────────────────

def browse(pkb_root: Path | None = None) -> dict[str, Any]:
    """Return a structured view of the entire PKM for the portal UI."""
    root = pkb_root or _pkb_root()
    if not root.exists():
        return {"exists": False, "root": str(root)}

    sections = {}
    # Order matters — this is the sidebar tree order on /dac.
    # `research` promoted above `sources` so the cockpit contract
    # files are easy to spot.
    for name in ("inbox", "research", "sources", "agents", "notes", "inference", "compiled"):
        folder = root / name
        if not folder.exists():
            sections[name] = {"count": 0, "items": []}
            continue
        items = []
        for p in sorted(folder.rglob("*")):
            if p.is_file() and not p.name.startswith("."):
                try:
                    if _is_low_signal_experiment_file(root, p):
                        continue
                    if _is_world_machinery(p):
                        continue
                    stat = p.stat()
                    items.append({
                        "path": str(p.relative_to(root)),
                        "name": p.name,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                                    .strftime("%Y-%m-%d %H:%M"),
                    })
                except OSError:
                    continue
        sections[name] = {"count": len(items), "items": items}

    return {
        "exists": True,
        "root": str(root),
        "sections": sections,
    }


def _is_low_signal_experiment_file(root: Path, p: Path) -> bool:
    """Hide stale autogenerated experiment stubs from /dac tree."""
    rel = str(p.relative_to(root)).replace("\\", "/")
    if not rel.startswith("agents/experiments/"):
        return False
    if p.name == "_rollup.md":
        return False
    if p.suffix.lower() not in {".md", ".txt", ".rst"}:
        return False
    try:
        text = p.read_text(errors="replace")
    except OSError:
        return False
    t = text.lower()
    has_structured_signal = (
        "**outcome:**" in t or
        "## results" in t or
        "## conclusion" in t or
        "## what was measured" in t
    )
    if has_structured_signal:
        return False

    stripped = t.strip()
    placeholder_hypothesis = (
        "**hypothesis:** [hypothesis" in t or
        "**hypothesis:** hypotheses:" in t
    )
    looks_like_legacy_stub = (
        stripped.startswith("# experiment ") and
        "**domain:**" in t and
        "**status:**" in t and
        placeholder_hypothesis
    )
    return looks_like_legacy_stub and len(stripped) < 240


_PKB_TEXT_SUFFIXES = (".md", ".txt", ".rst", ".csv", ".json", ".html")


def _is_world_machinery(p: Path) -> bool:
    """True for staged World bundle-machinery files (agenda/drift/roster/spec/
    terms.json under sources/world-*/). Excluded from every KB surface — the
    world's knowledge reaches the KB as per-term pages, not raw bundle JSON.
    Delegates to the one shared predicate in world_mount; never raises."""
    try:
        from arail.world_mount import is_world_machinery_path
        return is_world_machinery_path(p)
    except Exception:  # noqa: BLE001
        return False


def _iter_pkb_files(root: Path):
    """Yield (path, text) for every searchable file under ``root``."""
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.suffix not in _PKB_TEXT_SUFFIXES:
            continue
        if _is_world_machinery(p):
            continue
        # Conversation memory is raw chat state, never searchable KB content.
        # Its meta.json (user-authored titles) has a .json suffix and would
        # otherwise leak into the ungated /api/pkb/search index. Transcripts are
        # .jsonl (not indexed), but exclude the whole dir to close the sibling
        # meta.json leak and keep chat memory out of the wiki/KB.
        if "conversations" in p.relative_to(root).parts:
            continue
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        yield p, text


def _vector_db_path(root: Path) -> Path:
    return root / ".cache" / "lancedb"


def _source_kind_for_rel(rel: str) -> str:
    """Infer source_kind from the relative path prefix (POSIX style)."""
    rel_posix = rel.replace("\\", "/")
    if rel_posix.startswith("agents/research/"):
        return "agent_research"
    if rel_posix.startswith("agents/experiments/"):
        return "agent_experiment"
    if rel_posix.startswith("agents/synthesis/"):
        return "agent_synthesis"
    if rel_posix.startswith("agents/recommendations/"):
        return "agent_recommendation"
    if rel_posix.startswith("agents/buddy/dreams/"):
        return "agent_buddy_dream"
    if rel_posix.startswith("teacher/"):
        return "teacher_qa"
    return "user"


def _build_docs_rows() -> list[dict[str, Any]]:
    """Build LanceDB rows for every registered doc.

    Reuses docs_registry.all_docs() so the set is always in sync with
    what the Hub renders.  Returns [] if the registry raises or is empty
    (docs ingest must never block PKB ingest — see F8 isolation contract).

    Row schema mirrors the PKB schema so search callers need no changes:
      path        — "docs/<slug>.md" or "root/<slug>.md" (namespace-safe)
      name        — Doc.title (semantic label for the vector)
      vector      — hash_embedding of "<title> <slug> <body[:4096]>")
      mtime       — Doc.mtime
      source_kind — "docs" (new value; existing PKB rows stay "user"/agent/*)
    """
    from arail.vector_index import hash_embedding  # noqa: PLC0415

    try:
        from arail.portal.docs_registry import all_docs  # noqa: PLC0415
        docs = all_docs()
    except Exception as exc:  # pragma: no cover
        import logging
        logging.getLogger(__name__).warning(
            "pkb.index_all: docs_registry.all_docs() failed (%s); "
            "skipping docs ingest — PKB rows will still be indexed.",
            exc,
        )
        return []

    rows: list[dict[str, Any]] = []
    for doc in docs:
        p = Path(doc.path)
        try:
            body = p.read_text(errors="replace") if p.exists() else ""
        except OSError:
            body = ""
        # Cap at 4 KB — same as PKB to keep hash_embedding cheap on large docs.
        snippet = body[:4096]
        # Namespace the path so a future pkb/docs/foo.md cannot collide:
        #   docs/ files  → "docs/<slug>.md"
        #   root/ files  → "root/<slug>.md"
        namespace = doc.source_root if doc.source_root in {"docs", "root"} else "docs"
        row_path = f"{namespace}/{doc.slug}.md"
        rows.append({
            "path": row_path,
            "name": doc.title,
            "vector": hash_embedding(f"{doc.title} {doc.slug} {snippet}"),
            "mtime": doc.mtime,
            "source_kind": "docs",
        })
    return rows


def index_all(pkb_root: Path | None = None, *, include_docs: bool = True) -> dict[str, Any]:
    """Rebuild the LanceDB vector index over every PKB text file.

    Cheap to call (the corpus is small) and idempotent — the index lives
    under ``lab/pkb/.cache/lancedb`` so it doesn't pollute the user's
    notes.

    Args:
        pkb_root:     Override for the PKB root path (defaults to config).
        include_docs: If True (default), append one row per registered doc
                      from docs_registry alongside the PKB rows.  Pass
                      False to index PKB-only (e.g. in tests that assert
                      source_kind != 'docs').

    Returns ``{ok, indexed, indexed_docs, path}`` so callers can surface
    the state in activity logs.  The ``indexed_docs`` key is new in Sprint 3;
    it is 0 when ``include_docs=False`` or when the registry is empty.

    Schema: {path, name, vector, mtime, source_kind}
    """
    from arail.vector_index import VectorIndex, hash_embedding, available

    root = pkb_root or _pkb_root()
    if not root.exists() or not available():
        return {"ok": False, "indexed": 0, "indexed_docs": 0, "path": None}

    rows: list[dict[str, Any]] = []
    for p, text in _iter_pkb_files(root):
        rel = p.relative_to(root).as_posix()
        # Compose the vector input: name + path + first 4 KB of body.
        # Capping keeps the SHA1 token sweep cheap on big files; the
        # snippet preview the API returns is computed separately.
        snippet_for_embedding = text[:4096]
        rows.append({
            "path": rel,
            "name": p.name,
            "vector": hash_embedding(f"{p.name} {rel} {snippet_for_embedding}"),
            "mtime": p.stat().st_mtime,
            "source_kind": _source_kind_for_rel(rel),
        })

    docs_rows: list[dict[str, Any]] = _build_docs_rows() if include_docs else []
    all_rows = rows + docs_rows

    db_path = _vector_db_path(root)
    idx = VectorIndex(name="pkb_pages", db_path=db_path)
    written = idx.replace(all_rows)
    return {
        "ok": True,
        "indexed": written,
        "indexed_docs": len(docs_rows),
        "path": str(db_path),
    }


def _build_snippets(text: str, query: str) -> tuple[int, list[str]]:
    """Return (match_count, snippets) for the regex fallback path."""
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if not matches:
        return 0, []
    lines = text.splitlines()
    snippets: list[str] = []
    seen_lines: set[int] = set()
    for m in matches[:5]:
        line_num = text[:m.start()].count("\n")
        if line_num in seen_lines:
            continue
        seen_lines.add(line_num)
        ctx_start = max(0, line_num - 1)
        ctx_end = min(len(lines), line_num + 2)
        snippets.append("\n".join(lines[ctx_start:ctx_end])[:300])
    return len(matches), snippets


def _semantic_search(
    query: str,
    root: Path,
    *,
    k: int = 12,
    min_score: float = 0.05,
    approved: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Vector-backed search. Returns [] if LanceDB or the index is absent.

    When ``approved`` is a set of pkb-relative paths, results are filtered to
    that set — the Compiled-KB gate (agents build only on approved truth)."""
    from arail.vector_index import VectorIndex, available

    if not available():
        return []
    idx = VectorIndex(name="pkb_pages", db_path=_vector_db_path(root))
    if idx.count() == 0:
        # Lazy first-time indexing — every install ships LanceDB so we
        # build the index on demand instead of failing silently.
        index_all(root)
    # Over-fetch when gating so the approved subset still fills k results.
    hits = idx.search(query, k=(k * 6 if approved is not None else k), min_score=min_score)
    if approved is not None:
        hits = [h for h in hits if h.get("path") in approved][:k]
    if not hits:
        return []

    results: list[dict[str, Any]] = []
    for h in hits:
        rel = h.get("path")
        if not rel:
            continue
        full = root / rel
        snippets: list[str] = []
        if full.exists():
            try:
                text = full.read_text(errors="replace")
            except OSError:
                text = ""
            # Try regex first for an exact-match snippet — falls back
            # to the file's opening lines so the UI always has SOMETHING
            # to show beneath the title.
            _, snippets = _build_snippets(text, query)
            if not snippets and text:
                snippets = ["\n".join(text.splitlines()[:6])[:300]]
        results.append({
            "path": rel,
            "name": h.get("name", Path(rel).name),
            "match_count": max(1, int(round(h.get("score", 0.0) * 100))),
            "score": h.get("score", 0.0),
            "snippets": snippets,
            "source": "semantic",
        })
    return results


def search(query: str, pkb_root: Path | None = None, *,
           approved_only: bool = False) -> list[dict[str, Any]]:
    """Search the PKB. Vector recall first, regex fallback for exact terms.

    The vector path lets fuzzy queries like *"how do I tune AirLLM"* find
    primers titled *"AirLLM layer streaming"* without sharing a single
    keyword. When the vector path returns nothing (cold cache + LanceDB
    unavailable, or genuinely no semantic match) we drop to the original
    regex substring sweep so exact-token queries (URLs, error codes,
    file names) still resolve.

    ``approved_only`` is the Compiled-KB gate: when True, results are scoped
    to paths a human has approved into the Compiled KB — the layer agents
    experiment/develop against, never the raw candidate corpus. Callers pass
    it through ``search_for_agents`` rather than setting it directly.
    """
    root = pkb_root or _pkb_root()
    if not root.exists():
        return []

    approved: set[str] | None = None
    if approved_only:
        from arail.compiled_kb import approved_paths
        approved = approved_paths(root)
        if not approved:
            # Nothing approved yet — the gate honestly returns nothing rather
            # than leaking the raw corpus. Callers surface an "approve some
            # knowledge" empty state.
            return []

    semantic = _semantic_search(query, root, approved=approved)
    if semantic:
        return semantic

    # Regex fallback — preserves the historical exact-match contract.
    results: list[dict[str, Any]] = []
    for p, text in _iter_pkb_files(root):
        rel = p.relative_to(root).as_posix()
        if approved is not None and rel not in approved:
            continue
        match_count, snippets = _build_snippets(text, query)
        if match_count:
            results.append({
                "path": str(p.relative_to(root)),
                "name": p.name,
                "match_count": match_count,
                "snippets": snippets,
                "source": "keyword",
            })
    results.sort(key=lambda r: r["match_count"], reverse=True)
    return results


def retrieve_for_agents(query: str, pkb_root: Path | None = None) -> dict[str, Any]:
    """Retrieval for agents that experiment/develop (Researcher, chat RAG, goal
    drafter). Honors the Compiled-KB gate: when the gate is enabled (default),
    agents build ONLY on approved knowledge. When disabled via
    ``ARAIL_APPROVED_ONLY=off``, falls back to the full raw corpus.

    Returns ``{"hits": [...], "gate": <gate_state(cheap=True)>, "empty_reason":
    None|"gate_empty"|"no_match"|"gate_off_no_match"}`` so a caller can tell
    "the gate is empty, the search never ran" apart from "the search ran and
    found nothing" — both were a silent zero before this. Never raises: an
    internal error fails closed AND loud (``hits=[]``,
    ``empty_reason="gate_empty"``), never silent.
    """
    from arail.compiled_kb import gate_enabled, gate_state, approved_paths

    try:
        enabled = gate_enabled()
        gate = gate_state(pkb_root, cheap=True)
        if enabled and not approved_paths(pkb_root):
            return {"hits": [], "gate": gate, "empty_reason": "gate_empty"}
        hits = search(query, pkb_root, approved_only=enabled)
        if hits:
            return {"hits": hits, "gate": gate, "empty_reason": None}
        reason = "no_match" if enabled else "gate_off_no_match"
        return {"hits": hits, "gate": gate, "empty_reason": reason}
    except Exception:  # noqa: BLE001 — fail closed and loud, never silent
        from arail.compiled_kb import gate_state as _gs
        try:
            gate = _gs(pkb_root, cheap=True)
        except Exception:  # noqa: BLE001
            gate = {"schema": "arail.kb-gate/v1", "enabled": True,
                     "manifest_present": False, "approved_count": 0,
                     "live_count": 0, "pending_count": -1,
                     "state": "unbootstrapped", "hint": ""}
        return {"hits": [], "gate": gate, "empty_reason": "gate_empty"}


def search_for_agents(query: str, pkb_root: Path | None = None) -> list[dict[str, Any]]:
    """Retrieval for agents that experiment/develop (Researcher, chat RAG, goal
    drafter). Honors the Compiled-KB gate: when the gate is enabled (default),
    agents build ONLY on approved knowledge. When disabled via
    ``ARAIL_APPROVED_ONLY=off``, falls back to the full raw corpus.

    Kept as ``retrieve_for_agents(...)["hits"]`` — unchanged shape and gate
    semantics, so existing callers and ``tests/test_pkb_gate.py`` need no
    edit."""
    return retrieve_for_agents(query, pkb_root)["hits"]


# ── Agent Write Helpers ──────────────────────────────────────────────────

def write_agent_research(goal_id: str, content: str,
                         pkb_root: Path | None = None) -> Path:
    """Write a research report to agents/research/."""
    root = pkb_root or _pkb_root()
    dest = root / "agents" / "research"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{_date_prefix()}_{goal_id}_report.md"
    path.write_text(content)
    try:
        from arail.pkb_index import schedule_upsert
        schedule_upsert(path, pkb_root=root)
    except Exception:
        pass  # never break the file write on index failure
    return path


def write_agent_experiment(exp_id: str, content: str,
                           pkb_root: Path | None = None) -> Path:
    """Write an experiment log to agents/experiments/."""
    root = pkb_root or _pkb_root()
    dest = root / "agents" / "experiments"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{_date_prefix()}_{exp_id}.md"
    path.write_text(content)
    try:
        from arail.pkb_index import schedule_upsert
        schedule_upsert(path, pkb_root=root)
    except Exception:
        pass  # never break the file write on index failure
    return path


def write_agent_experiment_rollup(experiments: list[dict[str, Any]],
                                  domain: str = "general",
                                  pkb_root: Path | None = None) -> Path:
    """Write/refresh a compact rollup for recent experiment outcomes."""
    root = pkb_root or _pkb_root()
    dest = root / "agents" / "experiments"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "_rollup.md"

    done = [e for e in experiments if e.get("status") == "completed"]
    positives = sum(1 for e in done if e.get("hypothesis_supported") is True)
    negatives = sum(1 for e in done if e.get("hypothesis_supported") is False)

    lines = [
        "# Experiment Rollup",
        "",
        f"*Updated: {_ts()} UTC*",
        "",
        f"- **Domain:** {domain}",
        f"- **Completed:** {len(done)}",
        f"- **Positive:** {positives}",
        f"- **Negative:** {negatives}",
        "",
        "## Recent experiments",
        "",
    ]

    for e in done[:20]:
        eid = e.get("id", "unknown")
        outcome = "positive" if e.get("hypothesis_supported") else "negative"
        metrics = e.get("results") or {}
        metric_bits = []
        for k in ("improvement_rate", "confidence_score", "data_points"):
            if k in metrics:
                metric_bits.append(f"{k}: {metrics[k]}")
        metric_str = " · ".join(metric_bits) if metric_bits else "no metrics"
        lines.append(f"- `{eid}` **{outcome}** — {e.get('hypothesis', '')[:90]}")
        lines.append(f"  - {metric_str}")
        lines.append(f"  - conclusion: {str(e.get('conclusion', 'n/a'))[:180]}")

    path.write_text("\n".join(lines) + "\n")
    try:
        from arail.pkb_index import schedule_upsert
        schedule_upsert(path, pkb_root=root)
    except Exception:
        pass  # never break the file write on index failure
    return path


def write_agent_synthesis(topic: str, content: str,
                          pkb_root: Path | None = None) -> Path:
    """Write a synthesis document to agents/synthesis/."""
    root = pkb_root or _pkb_root()
    dest = root / "agents" / "synthesis"
    dest.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:60]
    path = dest / f"{_date_prefix()}_{slug}.md"
    path.write_text(content)
    try:
        from arail.pkb_index import schedule_upsert
        schedule_upsert(path, pkb_root=root)
    except Exception:
        pass  # never break the file write on index failure
    return path


def write_agent_recommendation(content: str,
                               pkb_root: Path | None = None) -> Path:
    """Write a recommendation to agents/recommendations/."""
    root = pkb_root or _pkb_root()
    dest = root / "agents" / "recommendations"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{_date_prefix()}_recommendation.md"
    # Append if file exists (multiple recs per day)
    if path.exists():
        with open(path, "a") as f:
            f.write(f"\n---\n\n{content}\n")
    else:
        path.write_text(content)
    try:
        from arail.pkb_index import schedule_upsert
        schedule_upsert(path, pkb_root=root)
    except Exception:
        pass  # never break the file write on index failure
    return path


def write_teacher_qa(question: str, answer: str, model: str,
                     pkb_root: Path | None = None) -> Path:
    """Write one Q&A from the Deep Teacher (/teacher) to teacher/.

    The Teacher routes every question through AeroLLM — these files
    are expensive to produce (multi-minute answers from a frontier
    model), so every one of them is preserved under the PKB where the
    wiki indexer picks them up. One file per consultation so history
    is easy to browse and cite."""
    root = pkb_root or _pkb_root()
    dest = root / "teacher"
    dest.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc)
    path = dest / f"{ts.strftime('%Y-%m-%d_%H-%M-%S')}.md"
    content = (
        f"---\n"
        f"title: Teacher — {ts.strftime('%Y-%m-%d %H:%M')}\n"
        f"section: teacher\n"
        f"tags: [teacher, aerollm]\n"
        f"---\n\n"
        f"**Model:** {model}\n"
        f"**Asked:** {ts.isoformat()}\n\n"
        f"## Question\n\n{question}\n\n"
        f"## Answer\n\n{answer}\n"
    )
    path.write_text(content)
    try:
        from arail.pkb_index import schedule_upsert
        schedule_upsert(path, pkb_root=root)
    except Exception:
        pass  # never break the file write on index failure
    return path


def write_buddy_dream(date_str: str, body: str,
                      pkb_root: Path | None = None) -> Path:
    """Write Buddy's nightly dream/reflection to agents/buddy/dreams/<date>.md.

    This helper is the index-aware replacement for the direct
    ``target.write_text(body)`` call in BuddyAgent.dream. Callers are
    responsible for building ``body`` (including YAML frontmatter) before
    calling this.
    """
    root = pkb_root or _pkb_root()
    dreams_dir = root / "agents" / "buddy" / "dreams"
    dreams_dir.mkdir(parents=True, exist_ok=True)
    path = dreams_dir / f"{date_str}.md"
    path.write_text(body)
    try:
        from arail.pkb_index import schedule_upsert
        schedule_upsert(path, pkb_root=root)
    except Exception:
        pass  # never break the file write on index failure
    return path


# ── Scaffold ─────────────────────────────────────────────────────────────

def scaffold(pkb_root: Path | None = None) -> Path:
    """Create the full PKM folder structure. Idempotent."""
    root = pkb_root or _pkb_root()
    dirs = [
        "inbox",
        "sources/papers", "sources/articles", "sources/datasets", "sources/images",
        # Videos and audio ride beside papers/articles — same treatment
        # (served as raw bytes, renderable when the frontend learns
        # <video>/<audio> inline playback).
        "sources/videos", "sources/audio",
        # Seeds — curated starter packs (one subdir per pack, e.g.
        # sources/seeds/model-building/). Populated by pkb_seed.
        "sources/seeds",
        "agents/research", "agents/experiments", "agents/synthesis",
        "agents/recommendations",
        "notes/scratch",
        # Research contract files: program.md + prepare.py + any
        # human-authored research notes the agent consults.
        "research",
        "compiled/reports", "compiled/summaries", "compiled/exports",
        "inference/prompts", "inference/completions", "inference/chains",
    ]
    for d in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)
    return root
