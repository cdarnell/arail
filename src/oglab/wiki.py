"""OGLab Wiki — the documentation-as-code compiler.

Scans a PKM tree, parses frontmatter and wikilinks, resolves backlinks,
builds a knowledge graph, and caches the result to disk so the portal
can serve wiki pages fast.

Design:
- Pure functions, no async, no portal coupling — unit-testable.
- Extends ``oglab.pkm`` rather than replacing it; ``pkm.compile_index``
  still produces the flat index for users who don't want a wiki.
- Frontmatter is optional on user pages, required on auto-generated
  pages from :mod:`oglab.docgen`.
- Wikilinks follow Obsidian syntax: ``[[target]]``, ``[[target|alias]]``,
  ``[[target#heading]]``.

Exposes a CLI entry point: ``python -m oglab.wiki build``.
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_log = logging.getLogger(__name__)

_WIKILINK_RE = re.compile(r"\[\[([^\[\]\n]+?)\]\]")
_HASHTAG_RE = re.compile(r"(?<!\w)#(\w[\w-]*)")
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


# ── Data shapes ──────────────────────────────────────────────────────────

@dataclass
class WikiRef:
    """A parsed ``[[target]]`` reference from page body."""
    target: str           # raw target text before resolution
    alias: Optional[str]  # text to display; None means use title
    anchor: Optional[str] # heading anchor after #
    span: tuple[int, int] # (start, end) offsets in original text


@dataclass
class Page:
    """One page in the wiki, after parsing."""
    slug: str                    # url-safe: "agents/research/2026-04-13-report"
    title: str                   # frontmatter title, first H1, or filename
    path: Path                   # absolute path on disk
    section: str                 # sources | agents | notes | compiled | docs
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    outgoing: list[str] = field(default_factory=list)   # slugs this page links to
    backlinks: list[str] = field(default_factory=list)  # slugs that link here
    source_ref: Optional[str] = None  # for auto-gen pages
    body_md: str = ""
    modified: float = 0.0             # unix mtime for sorting / caching

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["path"] = str(self.path)
        return d


@dataclass
class WikiGraph:
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class WikiBuildResult:
    page_count: int
    link_count: int
    tag_count: int
    elapsed_ms: int
    manifest_path: Path


# ── Slug + title helpers ─────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convert a title or path-fragment into a url-safe slug.

    Lowercases, strips unicode accents, replaces non-word chars with
    hyphens, collapses repeats, trims.
    """
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9/]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    # Preserve path separators so "agents/research/foo" stays nested.
    text = re.sub(r"/-+", "/", text)
    text = re.sub(r"-+/", "/", text)
    return text


def _slug_from_path(pkm_root: Path, path: Path) -> str:
    """Compute a slug from a file path relative to the PKM root."""
    rel = path.relative_to(pkm_root).with_suffix("")
    return slugify(str(rel))


def _first_h1(body: str) -> Optional[str]:
    m = _H1_RE.search(body)
    return m.group(1).strip() if m else None


# ── Frontmatter parsing ──────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a ``---YAML---\\n`` block from the body.

    Tolerant — any parse failure yields ``({}, text)`` and logs a warning.
    Only a tiny subset of YAML is supported (top-level key: value, and
    list values expressed as ``[a, b, c]``). That keeps us off a heavy
    YAML dependency while covering everything our frontmatter contract
    actually uses (title, section, tags, aliases, source, generated).
    """
    if not text.startswith("---"):
        return {}, text
    # Find the closing ``---`` on its own line.
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        return {}, text
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, text

    raw = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1:])

    meta: dict[str, Any] = {}
    for ln in raw.splitlines():
        ln = ln.rstrip()
        if not ln or ln.lstrip().startswith("#"):
            continue
        if ":" not in ln:
            continue
        key, _, val = ln.partition(":")
        key = key.strip()
        val = val.strip()
        meta[key] = _coerce_value(val)
    return meta, body


def _coerce_value(val: str) -> Any:
    """Minimal YAML-ish value coercion."""
    if not val:
        return ""
    # Strip quotes if present.
    if (val.startswith('"') and val.endswith('"')) or \
       (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    # List literal.
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [_coerce_value(part.strip()) for part in inner.split(",")]
    # Bool.
    if val.lower() in ("true", "false"):
        return val.lower() == "true"
    # Int.
    try:
        return int(val)
    except ValueError:
        pass
    return val


# ── Wikilink parsing ─────────────────────────────────────────────────────

def parse_wikilinks(body: str) -> list[WikiRef]:
    """Extract every ``[[target]]`` reference from a body.

    Handles the three forms:
      - ``[[target]]``
      - ``[[target|alias]]``
      - ``[[target#heading]]`` (anchor also combines with alias)
    """
    refs: list[WikiRef] = []
    for m in _WIKILINK_RE.finditer(body):
        inner = m.group(1)
        alias: Optional[str] = None
        anchor: Optional[str] = None
        if "|" in inner:
            target, alias = (s.strip() for s in inner.split("|", 1))
        else:
            target = inner.strip()
        if "#" in target:
            target, anchor = (s.strip() for s in target.split("#", 1))
        refs.append(WikiRef(
            target=target,
            alias=alias or None,
            anchor=anchor or None,
            span=(m.start(), m.end()),
        ))
    return refs


def _collect_hashtags(body: str) -> list[str]:
    return sorted(set(m.group(1) for m in _HASHTAG_RE.finditer(body)))


# ── Page index + backlink resolution ─────────────────────────────────────

def build_page_index(pkm_root: Path) -> dict[str, Page]:
    """Walk the PKM tree, parse every ``*.md`` file, return slug→Page.

    Hidden files, the ``.wiki-cache`` directory, and the ``inbox/`` are
    excluded.
    """
    pages: dict[str, Page] = {}
    if not pkm_root.exists():
        return pages

    skip_dirs = {".wiki-cache", "inbox"}

    for md in sorted(pkm_root.rglob("*.md")):
        if any(part in skip_dirs or part.startswith(".") for part in md.parts):
            continue
        try:
            text = md.read_text()
        except OSError as e:
            _log.warning("wiki: cannot read %s: %s", md, e)
            continue

        meta, body = parse_frontmatter(text)
        section = md.relative_to(pkm_root).parts[0] if md != pkm_root else "root"

        slug = str(meta.get("slug") or _slug_from_path(pkm_root, md))

        title = str(
            meta.get("title")
            or _first_h1(body)
            or md.stem.replace("_", " ").replace("-", " ").title()
        )

        tags: list[str] = []
        if isinstance(meta.get("tags"), list):
            tags.extend(str(t) for t in meta["tags"])
        elif isinstance(meta.get("tags"), str):
            tags.extend(t.strip() for t in meta["tags"].split(",") if t.strip())
        tags.extend(_collect_hashtags(body))
        tags = sorted(set(t.lstrip("#") for t in tags))

        aliases_raw = meta.get("aliases") or []
        if isinstance(aliases_raw, str):
            aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]
        elif isinstance(aliases_raw, list):
            aliases = [str(a) for a in aliases_raw]
        else:
            aliases = []

        refs = parse_wikilinks(body)
        outgoing_raw = [r.target for r in refs]

        source_ref = meta.get("source") if isinstance(meta.get("source"), str) else None

        page = Page(
            slug=slug,
            title=title,
            path=md,
            section=str(meta.get("section") or section),
            tags=tags,
            aliases=aliases,
            outgoing=outgoing_raw,
            source_ref=source_ref,
            body_md=body,
            modified=md.stat().st_mtime,
        )
        pages[slug] = page

    return pages


def resolve_links(pages: dict[str, Page]) -> None:
    """Resolve outgoing wikilink targets to slugs and invert into backlinks.

    Mutates pages in place. Runs in O(pages * links) which is fine for
    the scale we care about (~1k pages).
    """
    # Build an alias → slug lookup. Titles and aliases win over filename slugs.
    lookup: dict[str, str] = {}
    for slug, page in pages.items():
        lookup.setdefault(slugify(page.title), slug)
        lookup.setdefault(slug, slug)
        for alias in page.aliases:
            lookup.setdefault(slugify(alias), slug)

    # Resolve + build backlinks.
    for slug, page in pages.items():
        resolved: list[str] = []
        for raw_target in page.outgoing:
            target_slug = lookup.get(slugify(raw_target))
            if target_slug and target_slug != slug:
                resolved.append(target_slug)
        # Dedupe while preserving order.
        seen: set[str] = set()
        deduped: list[str] = []
        for t in resolved:
            if t not in seen:
                seen.add(t)
                deduped.append(t)
        page.outgoing = deduped

    for slug, page in pages.items():
        for tgt in page.outgoing:
            pages[tgt].backlinks.append(slug)
    for page in pages.values():
        # Dedupe backlinks.
        page.backlinks = sorted(set(page.backlinks))


# ── Graph builder ────────────────────────────────────────────────────────

def build_link_graph(pages: dict[str, Page]) -> WikiGraph:
    """Build the knowledge graph from resolved pages.

    Node shape matches ``/api/system/graph`` so the existing Canvas
    renderer can draw it with no changes.
    """
    graph = WikiGraph()
    for slug, page in pages.items():
        graph.nodes.append({
            "id": slug,
            "label": page.title,
            "group": page.section,
            "type": "doc" if page.source_ref else "note",
            "size": 8 + min(len(page.backlinks), 12),
            "tags": page.tags,
            "desc": (page.body_md[:160].replace("\n", " ").strip() + "…") if page.body_md else "",
            "status": "active",
        })
    seen_edges: set[tuple[str, str]] = set()
    for slug, page in pages.items():
        for target in page.outgoing:
            key = (slug, target)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            graph.edges.append({
                "source": slug,
                "target": target,
                "type": "link",
                "label": "",
            })
    return graph


# ── Markdown → HTML rendering ────────────────────────────────────────────

_WIKI_HREF_MARKER = "/wiki/"
_WIKI_MISSING_MARKER = "/wiki/new?title="


def _render_body_to_html(body: str, pages: dict[str, Page]) -> str:
    """Render markdown body to HTML, resolving wikilinks to anchors.

    Uses markdown-it-py when available, falls back to a minimal regex
    renderer so the wiki module imports cleanly even if the extra is
    not installed.

    Wikilinks are rewritten to standard markdown ``[text](url)`` syntax
    BEFORE handing to the markdown renderer (so html:false stays safe),
    then post-processed to attach the ``wikilink`` CSS class.
    """
    def _replace(match: re.Match[str]) -> str:
        inner = match.group(1)
        alias: Optional[str] = None
        if "|" in inner:
            target, alias = (s.strip() for s in inner.split("|", 1))
        else:
            target = inner.strip()
        anchor = ""
        if "#" in target:
            target, anchor_part = (s.strip() for s in target.split("#", 1))
            anchor = "#" + slugify(anchor_part)
        target_slug = slugify(target)
        resolved = None
        for slug, page in pages.items():
            if slug == target_slug or slugify(page.title) == target_slug \
               or target_slug in (slugify(a) for a in page.aliases):
                resolved = slug
                break
        text = alias or target
        if resolved:
            return f"[{text}]({_WIKI_HREF_MARKER}{resolved}{anchor})"
        return f"[{text}]({_WIKI_MISSING_MARKER}{target})"

    body = _WIKILINK_RE.sub(_replace, body)

    try:
        from markdown_it import MarkdownIt  # type: ignore
        md = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
        md.enable("table")
        html = md.render(body)
    except ImportError:
        html = _fallback_render(body)

    # Post-process: attach the wikilink class to any <a> whose href we injected.
    html = html.replace(
        f'<a href="{_WIKI_MISSING_MARKER}',
        f'<a class="wikilink missing" href="{_WIKI_MISSING_MARKER}',
    )
    html = html.replace(
        f'<a href="{_WIKI_HREF_MARKER}',
        f'<a class="wikilink" href="{_WIKI_HREF_MARKER}',
    )
    return html


def _fallback_render(body: str) -> str:
    """Regex-only fallback. Not pretty but keeps imports working."""
    html = body
    html = re.sub(r"^#### (.+)$", r"<h4>\1</h4>", html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"```([\s\S]*?)```", r"<pre><code>\1</code></pre>", html)
    html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)
    html = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", html)
    html = html.replace("\n\n", "</p><p>")
    return "<p>" + html + "</p>"


def render_page(page: Page, pages: dict[str, Page]) -> str:
    """Public wrapper — render a page's body to HTML."""
    return _render_body_to_html(page.body_md, pages)


# ── Compile + cache ──────────────────────────────────────────────────────

def compile_wiki(pkm_root: Optional[Path] = None,
                 repo_root: Optional[Path] = None) -> WikiBuildResult:
    """Top-level compile: parse, resolve, graph, optionally generate from
    source, and write the cache manifest.

    ``repo_root`` enables the docgen pass. When omitted, only user content
    under ``pkm_root`` is compiled.
    """
    start = time.monotonic()
    root = pkm_root or _pkm_root_default()
    cache_dir = root / ".wiki-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if repo_root is not None:
        try:
            # importlib avoids a static import cycle with oglab.docgen
            # (which arrives in Phase 3 and itself imports from this module).
            import importlib
            docgen = importlib.import_module("oglab.docgen")
            docgen.generate_all(repo_root, root)
        except Exception as e:  # noqa: BLE001
            _log.warning("wiki: docgen failed: %s", e)

    pages = build_page_index(root)
    resolve_links(pages)
    graph = build_link_graph(pages)

    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "pkm_root": str(root),
        "pages": {slug: p.to_dict() for slug, p in pages.items()},
        "graph": {"nodes": graph.nodes, "edges": graph.edges},
    }
    manifest_path = cache_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))

    elapsed = int((time.monotonic() - start) * 1000)
    link_count = sum(len(p.outgoing) for p in pages.values())
    tag_count = len({t for p in pages.values() for t in p.tags})

    return WikiBuildResult(
        page_count=len(pages),
        link_count=link_count,
        tag_count=tag_count,
        elapsed_ms=elapsed,
        manifest_path=manifest_path,
    )


def load_manifest(pkm_root: Optional[Path] = None) -> dict[str, Any]:
    """Load the cached manifest, rebuilding once if absent."""
    root = pkm_root or _pkm_root_default()
    path = root / ".wiki-cache" / "manifest.json"
    if not path.exists():
        compile_wiki(root)
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        _log.warning("wiki: manifest load failed (%s); rebuilding", e)
        compile_wiki(root)
        return json.loads(path.read_text())


def _pkm_root_default() -> Path:
    from oglab.config import PKM_ROOT
    return PKM_ROOT


# ── CLI entry point ──────────────────────────────────────────────────────

def _cli() -> None:
    import argparse
    parser = argparse.ArgumentParser(prog="python -m oglab.wiki")
    sub = parser.add_subparsers(dest="cmd")

    build = sub.add_parser("build", help="Compile the wiki manifest.")
    build.add_argument("--pkm-root", type=Path, default=None)
    build.add_argument("--repo-root", type=Path, default=None,
                       help="Enable docgen: scan this repo root for source files.")

    info = sub.add_parser("info", help="Show the cached manifest summary.")
    info.add_argument("--pkm-root", type=Path, default=None)

    args = parser.parse_args()
    if args.cmd == "build":
        result = compile_wiki(args.pkm_root, args.repo_root)
        print(f"wiki built: {result.page_count} pages, "
              f"{result.link_count} links, "
              f"{result.tag_count} tags "
              f"({result.elapsed_ms} ms)")
        print(f"manifest: {result.manifest_path}")
    elif args.cmd == "info":
        m = load_manifest(args.pkm_root)
        print(f"built_at: {m.get('built_at')}")
        print(f"pages:    {len(m.get('pages', {}))}")
        print(f"nodes:    {len(m.get('graph', {}).get('nodes', []))}")
        print(f"edges:    {len(m.get('graph', {}).get('edges', []))}")
    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
