"""OGLab PKM — Personal Knowledge Management for your lab.

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


def _pkm_root() -> Path:
    """Resolve PKM root via central config (honors LAB_PKM env)."""
    from oglab.config import PKM_ROOT
    return PKM_ROOT


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
}


def ingest(pkm_root: Path | None = None) -> dict[str, Any]:
    """Process everything in inbox/ → sources/.

    Returns a summary dict of actions taken.
    """
    root = pkm_root or _pkm_root()
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


def compile_index(pkm_root: Path | None = None) -> dict[str, Any]:
    """Build index.md at the PKM root. Returns compile stats."""
    root = pkm_root or _pkm_root()
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

def browse(pkm_root: Path | None = None) -> dict[str, Any]:
    """Return a structured view of the entire PKM for the portal UI."""
    root = pkm_root or _pkm_root()
    if not root.exists():
        return {"exists": False, "root": str(root)}

    sections = {}
    for name in ("inbox", "sources", "agents", "notes", "inference", "compiled"):
        folder = root / name
        if not folder.exists():
            sections[name] = {"count": 0, "items": []}
            continue
        items = []
        for p in sorted(folder.rglob("*")):
            if p.is_file() and not p.name.startswith("."):
                try:
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


def search(query: str, pkm_root: Path | None = None) -> list[dict[str, Any]]:
    """Full-text search across all PKM text files."""
    root = pkm_root or _pkm_root()
    if not root.exists():
        return []

    results: list[dict[str, Any]] = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.suffix not in (".md", ".txt", ".rst", ".csv", ".json", ".html"):
            continue
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        matches = list(pattern.finditer(text))
        if matches:
            # Collect context snippets
            snippets: list[str] = []
            lines = text.splitlines()
            seen_lines: set[int] = set()
            for m in matches[:5]:  # limit to 5 matches per file
                # Find line number
                line_num = text[:m.start()].count("\n")
                if line_num in seen_lines:
                    continue
                seen_lines.add(line_num)
                ctx_start = max(0, line_num - 1)
                ctx_end = min(len(lines), line_num + 2)
                snippet = "\n".join(lines[ctx_start:ctx_end])
                snippets.append(snippet[:300])

            results.append({
                "path": str(p.relative_to(root)),
                "name": p.name,
                "match_count": len(matches),
                "snippets": snippets,
            })

    # Sort by match count descending
    results.sort(key=lambda r: r["match_count"], reverse=True)
    return results


# ── Agent Write Helpers ──────────────────────────────────────────────────

def write_agent_research(goal_id: str, content: str,
                         pkm_root: Path | None = None) -> Path:
    """Write a research report to agents/research/."""
    root = pkm_root or _pkm_root()
    dest = root / "agents" / "research"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{_date_prefix()}_{goal_id}_report.md"
    path.write_text(content)
    return path


def write_agent_experiment(exp_id: str, content: str,
                           pkm_root: Path | None = None) -> Path:
    """Write an experiment log to agents/experiments/."""
    root = pkm_root or _pkm_root()
    dest = root / "agents" / "experiments"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{_date_prefix()}_{exp_id}.md"
    path.write_text(content)
    return path


def write_agent_synthesis(topic: str, content: str,
                          pkm_root: Path | None = None) -> Path:
    """Write a synthesis document to agents/synthesis/."""
    root = pkm_root or _pkm_root()
    dest = root / "agents" / "synthesis"
    dest.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:60]
    path = dest / f"{_date_prefix()}_{slug}.md"
    path.write_text(content)
    return path


def write_agent_recommendation(content: str,
                               pkm_root: Path | None = None) -> Path:
    """Write a recommendation to agents/recommendations/."""
    root = pkm_root or _pkm_root()
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


# ── Scaffold ─────────────────────────────────────────────────────────────

def scaffold(pkm_root: Path | None = None) -> Path:
    """Create the full PKM folder structure. Idempotent."""
    root = pkm_root or _pkm_root()
    dirs = [
        "inbox",
        "sources/papers", "sources/articles", "sources/datasets",
        "agents/research", "agents/experiments", "agents/synthesis",
        "agents/recommendations",
        "notes/scratch",
        "compiled/reports", "compiled/summaries", "compiled/exports",
        "inference/prompts", "inference/completions", "inference/chains",
    ]
    for d in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)
    return root
