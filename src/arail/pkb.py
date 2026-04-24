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

    Returns a summary dict of actions taken.
    """
    root = pkb_root or _pkb_root()
    inbox = root / "inbox"
    if not inbox.exists():
        return {"moved": 0, "urls_fetched": 0, "errors": []}

    moved = 0
    urls_fetched = 0
    errors: list[str] = []

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
            except OSError as e:
                errors.append(f"{item.name}: {e}")

    return {"moved": moved, "urls_fetched": urls_fetched, "errors": errors}


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
    # Order matters — this is the sidebar tree order on /knowledge.
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
    """Hide stale autogenerated experiment stubs from /knowledge tree."""
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


def _iter_pkb_files(root: Path):
    """Yield (path, text) for every searchable file under ``root``."""
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.suffix not in _PKB_TEXT_SUFFIXES:
            continue
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        yield p, text


def _vector_db_path(root: Path) -> Path:
    return root / ".cache" / "lancedb"


def index_all(pkb_root: Path | None = None) -> dict[str, Any]:
    """Rebuild the LanceDB vector index over every PKB text file.

    Cheap to call (the corpus is small) and idempotent — the index lives
    under ``lab/pkb/.cache/lancedb`` so it doesn't pollute the user's
    notes. Returns ``{ok, indexed, path}`` so callers can surface the
    state in activity logs.
    """
    from arail.vector_index import VectorIndex, hash_embedding, available

    root = pkb_root or _pkb_root()
    if not root.exists() or not available():
        return {"ok": False, "indexed": 0, "path": None}

    rows: list[dict[str, Any]] = []
    for p, text in _iter_pkb_files(root):
        rel = str(p.relative_to(root))
        # Compose the vector input: name + path + first 4 KB of body.
        # Capping keeps the SHA1 token sweep cheap on big files; the
        # snippet preview the API returns is computed separately.
        snippet_for_embedding = text[:4096]
        rows.append({
            "path": rel,
            "name": p.name,
            "vector": hash_embedding(f"{p.name} {rel} {snippet_for_embedding}"),
        })

    db_path = _vector_db_path(root)
    idx = VectorIndex(name="pkb_pages", db_path=db_path)
    written = idx.replace(rows)
    return {"ok": True, "indexed": written, "path": str(db_path)}


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
) -> list[dict[str, Any]]:
    """Vector-backed search. Returns [] if LanceDB or the index is absent."""
    from arail.vector_index import VectorIndex, available

    if not available():
        return []
    idx = VectorIndex(name="pkb_pages", db_path=_vector_db_path(root))
    if idx.count() == 0:
        # Lazy first-time indexing — every install ships LanceDB so we
        # build the index on demand instead of failing silently.
        index_all(root)
    hits = idx.search(query, k=k, min_score=min_score)
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


def search(query: str, pkb_root: Path | None = None) -> list[dict[str, Any]]:
    """Search the PKB. Vector recall first, regex fallback for exact terms.

    The vector path lets fuzzy queries like *"how do I tune AirLLM"* find
    primers titled *"AirLLM layer streaming"* without sharing a single
    keyword. When the vector path returns nothing (cold cache + LanceDB
    unavailable, or genuinely no semantic match) we drop to the original
    regex substring sweep so exact-token queries (URLs, error codes,
    file names) still resolve.
    """
    root = pkb_root or _pkb_root()
    if not root.exists():
        return []

    semantic = _semantic_search(query, root)
    if semantic:
        return semantic

    # Regex fallback — preserves the historical exact-match contract.
    results: list[dict[str, Any]] = []
    for p, text in _iter_pkb_files(root):
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


# ── Agent Write Helpers ──────────────────────────────────────────────────

def write_agent_research(goal_id: str, content: str,
                         pkb_root: Path | None = None) -> Path:
    """Write a research report to agents/research/."""
    root = pkb_root or _pkb_root()
    dest = root / "agents" / "research"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{_date_prefix()}_{goal_id}_report.md"
    path.write_text(content)
    return path


def write_agent_experiment(exp_id: str, content: str,
                           pkb_root: Path | None = None) -> Path:
    """Write an experiment log to agents/experiments/."""
    root = pkb_root or _pkb_root()
    dest = root / "agents" / "experiments"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{_date_prefix()}_{exp_id}.md"
    path.write_text(content)
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
