"""docs_registry — frontmatter-driven registry for user-facing lab docs.

Sprint 1 (2026-05-16-docs-hub-sprint-1): builds the catalog, exposes five
accessors, caches in-process keyed by directory mtime. No caller in Sprint 1
— only tests import this module. Sprint 2 wires it into the Hub landing.

Security properties:
  - Only walks two curated roots (docs/ and repo root). No arbitrary paths.
  - Every resolved path is checked against the curated root via is_relative_to()
    after symlink resolution; symlink escapes are skipped with a WARNING.
  - related() resolves slugs only via the internal _docs dict — it never opens
    a file path derived from frontmatter values. Path traversal is structurally
    impossible.
  - slug collision raises RuntimeError loudly (developer error, not user error).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# python-frontmatter import — graceful degradation if missing
# ---------------------------------------------------------------------------

try:
    import frontmatter as _fm  # python-frontmatter>=1.1.0

    _FRONTMATTER_AVAILABLE = True
except ImportError:  # pragma: no cover
    _log.warning(
        "docs_registry: python-frontmatter is not installed. "
        "All docs_registry accessors will return empty results. "
        "Run `pip install python-frontmatter` or `pip install -e .[dev]`."
    )
    _fm = None  # type: ignore[assignment]
    _FRONTMATTER_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CATEGORIES: tuple[str, ...] = (
    "Getting Started",
    "Concepts",
    "Operating",
    "Reference",
    "Design",
)

_CATEGORY_ORDER: dict[str, int] = {cat: i for i, cat in enumerate(CATEGORIES)}

_VALID_AUDIENCES = frozenset({"beginner", "operator", "architect"})

# Files excluded from the registry by name (case-sensitive basename match).
_DOCS_DENYLIST: frozenset[str] = frozenset(
    {
        "BLUEPRINT_PROMPT.md",
        "DEBUG_QWEN25_7B_CASE_STUDY.md",
        "maximus.plan.md",
        "chat-studio.spec.md",
        "standards-compliance.md",
        "INDEX.md",  # legacy hub placeholder; Sprint 2 will replace
        # design.md was renamed to portal-design.md in Sprint 2 to resolve slug
        # collision with root design.md.  Entry removed from denylist at the same
        # time (F11 atomic commit: rename + denylist removal in one shot).
    }
)

# Files excluded from the repo-root curated allowlist.
_ROOT_DENYLIST: frozenset[str] = frozenset(
    {
        "CLAUDE.md",
        "AGENTS.md",
        "README.md",
        "CODE_OF_CONDUCT.md",
    }
)

# Curated allowlist for repo-root docs (only these are included from root).
_ROOT_ALLOWLIST: frozenset[str] = frozenset(
    {
        "design.md",
        "BLUEPRINTS.md",
        "ROADMAP.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
    }
)


# ---------------------------------------------------------------------------
# Doc dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Doc:
    slug: str
    path: Path
    title: str
    description: str = ""
    category: str = "Reference"
    order: int = 100
    tags: tuple[str, ...] = ()
    read_minutes: int = 1
    audience: str = "beginner"
    related: tuple[str, ...] = ()
    buddy_prompt: str = ""
    source_root: str = "docs"
    mtime: float = 0.0


# ---------------------------------------------------------------------------
# In-process cache
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_cache_key: object = None
_cache_data: tuple[Doc, ...] | None = None

# Exposed for monkeypatching in tests.
_BUILD_CALLS = 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    """Return the repository root (three levels up from this file's package)."""
    return Path(__file__).resolve().parent.parent.parent.parent


def _compute_cache_key(docs_dir: Path, root_dir: Path) -> object:
    """Cache key = tuple of (path, mtime) for all .md files in both roots.

    This handles both directory-level mtime changes (file added/removed/renamed)
    and in-place file edits (per-file mtime).
    """
    entries: list[tuple[str, float]] = []
    for base in (docs_dir, root_dir):
        if not base.exists():
            continue
        for p in sorted(base.iterdir()):
            if p.suffix == ".md":
                try:
                    entries.append((str(p), p.stat().st_mtime))
                except OSError:
                    pass
    return tuple(entries)


def _parse_tags(raw: object) -> tuple[str, ...]:
    """Normalise tags: accept list or comma-string, lowercase, dedupe."""
    if isinstance(raw, list):
        items = [str(t) for t in raw]
    elif isinstance(raw, str):
        items = [t for t in raw.split(",")]
    else:
        return ()
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        norm = item.strip().lower()
        if norm and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return tuple(result)


def _parse_related(raw: object, self_slug: str) -> tuple[str, ...]:
    """Normalise related slugs: strip trailing .md, dedupe, drop self."""
    if not isinstance(raw, list):
        if isinstance(raw, str):
            raw = [raw]
        else:
            return ()
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        s = str(item).strip()
        if s.lower().endswith(".md"):
            s = s[:-3]
        if s and s != self_slug and s not in seen:
            seen.add(s)
            result.append(s)
    return tuple(result)


def _title_from_body(body: str, stem: str) -> str:
    """Extract first H1 from body or fall back to title-cased stem."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            candidate = stripped[2:].strip()
            if candidate:
                return candidate
    return stem.replace("-", " ").replace("_", " ").title()


def _read_minutes(body: str) -> int:
    words = len(body.split())
    return max(1, round(words / 200))


def _parse_doc(path: Path, source_root: str) -> Doc:
    """Parse a single markdown file into a Doc. Never raises."""
    slug = path.stem
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        _log.warning("docs_registry: cannot read %s: %s", path, exc)
        raw = ""

    meta: dict = {}
    body: str = raw

    if _FRONTMATTER_AVAILABLE:
        try:
            post = _fm.loads(raw)
            meta = dict(post.metadata)
            body = post.content
        except Exception as exc:  # yaml.YAMLError or any parse error
            _log.warning(
                "docs_registry: malformed frontmatter in %s (%s) — using defaults",
                path,
                exc,
            )
            meta = {}
            body = raw

    # title
    raw_title = meta.get("title", "")
    title = str(raw_title).strip() if raw_title else ""
    if not title:
        title = _title_from_body(body, slug)

    # description
    description = str(meta.get("description", "")).strip()

    # category
    raw_cat = str(meta.get("category", "Reference")).strip()
    if raw_cat not in CATEGORIES:
        _log.warning(
            "docs_registry: unknown category %r in %s — coercing to 'Reference'",
            raw_cat,
            path,
        )
        raw_cat = "Reference"
    category = raw_cat

    # order
    try:
        order = int(meta.get("order", 100))
    except (TypeError, ValueError):
        _log.warning("docs_registry: non-int order in %s — using 100", path)
        order = 100

    # tags
    tags = _parse_tags(meta.get("tags", []))

    # read_minutes
    try:
        rm = int(meta.get("read_minutes", 0))
        read_minutes = max(1, rm) if rm > 0 else _read_minutes(body)
    except (TypeError, ValueError):
        read_minutes = _read_minutes(body)

    # audience
    raw_aud = str(meta.get("audience", "beginner")).strip()
    if raw_aud not in _VALID_AUDIENCES:
        _log.warning(
            "docs_registry: unknown audience %r in %s — coercing to 'beginner'",
            raw_aud,
            path,
        )
        raw_aud = "beginner"
    audience = raw_aud

    # related
    related = _parse_related(meta.get("related", []), slug)

    # buddy_prompt
    buddy_prompt = str(meta.get("buddy_prompt", "")).strip()

    # mtime
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0

    return Doc(
        slug=slug,
        path=path,
        title=title,
        description=description,
        category=category,
        order=order,
        tags=tags,
        read_minutes=read_minutes,
        audience=audience,
        related=related,
        buddy_prompt=buddy_prompt,
        source_root=source_root,
        mtime=mtime,
    )


def _build(docs_dir: Path, root_dir: Path) -> tuple[Doc, ...]:
    """Walk both roots and build the full sorted catalog. Raises on collision."""
    global _BUILD_CALLS
    _BUILD_CALLS += 1

    docs_by_slug: dict[str, tuple[Doc, Path]] = {}  # slug → (doc, first_seen_path)

    def _register(path: Path, source_root: str) -> None:
        # Resolve symlinks and verify the file is inside the curated root.
        try:
            resolved = path.resolve()
        except OSError:
            _log.warning("docs_registry: cannot resolve %s — skipping", path)
            return
        root = docs_dir if source_root == "docs" else root_dir
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            _log.warning(
                "docs_registry: %s resolves outside curated root %s — skipping (symlink escape?)",
                path,
                root,
            )
            return

        doc = _parse_doc(resolved, source_root)
        slug = doc.slug
        if slug in docs_by_slug:
            existing_path = docs_by_slug[slug][1]
            raise RuntimeError(
                f"docs_registry: slug collision: '{slug}' from {existing_path} and {resolved}"
            )
        docs_by_slug[slug] = (doc, resolved)

    # Walk docs/
    if docs_dir.exists():
        for p in docs_dir.iterdir():
            if p.suffix != ".md":
                continue
            if p.name in _DOCS_DENYLIST:
                continue
            _register(p, "docs")

    # Walk repo root (curated allowlist only)
    for name in _ROOT_ALLOWLIST:
        p = root_dir / name
        if not p.exists():
            continue
        _register(p, "root")

    # Sort: (category_order, order, slug)
    all_docs_list = [doc for doc, _ in docs_by_slug.values()]
    all_docs_list.sort(
        key=lambda d: (_CATEGORY_ORDER.get(d.category, 99), d.order, d.slug)
    )
    return tuple(all_docs_list)


def _load() -> tuple[Doc, ...]:
    """Return the cached catalog, rebuilding if mtime has changed."""
    global _cache_key, _cache_data

    if not _FRONTMATTER_AVAILABLE:
        return ()

    root = _repo_root()
    docs_dir = root / "docs"

    current_key = _compute_cache_key(docs_dir, root)

    # Fast path — no lock needed for the read (GIL protects the check).
    if current_key == _cache_key and _cache_data is not None:
        return _cache_data

    with _cache_lock:
        # Re-check inside the lock (another thread may have rebuilt).
        if current_key == _cache_key and _cache_data is not None:
            return _cache_data
        try:
            data = _build(docs_dir, root)
        except RuntimeError:
            raise
        except Exception as exc:
            _log.warning("docs_registry: build failed: %s", exc)
            data = ()
        _cache_key = current_key
        _cache_data = data
        return data


def _invalidate_cache() -> None:
    """Force cache invalidation. Used by tests."""
    global _cache_key, _cache_data
    with _cache_lock:
        _cache_key = None
        _cache_data = None


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------


def all_docs() -> tuple[Doc, ...]:
    """All registered docs, sorted by (category, order, slug). Never raises."""
    try:
        return _load()
    except Exception as exc:
        _log.warning("docs_registry.all_docs: unexpected error: %s", exc)
        return ()


def by_category() -> dict[str, tuple[Doc, ...]]:
    """Mapping of category → ordered docs. Empty categories omitted."""
    result: dict[str, list[Doc]] = {}
    for doc in all_docs():
        result.setdefault(doc.category, []).append(doc)
    return {cat: tuple(docs) for cat, docs in result.items()}


def get(slug: str) -> Doc | None:
    """Return the Doc for slug, or None. Case-sensitive."""
    for doc in all_docs():
        if doc.slug == slug:
            return doc
    return None


def siblings(slug: str) -> tuple[Doc | None, Doc | None]:
    """Return (prev, next) within the same category. (None, None) if unknown."""
    doc = get(slug)
    if doc is None:
        return (None, None)
    peers = [d for d in all_docs() if d.category == doc.category]
    try:
        idx = next(i for i, d in enumerate(peers) if d.slug == slug)
    except StopIteration:
        return (None, None)
    prev = peers[idx - 1] if idx > 0 else None
    nxt = peers[idx + 1] if idx < len(peers) - 1 else None
    return (prev, nxt)


def related(slug: str, limit: int = 3) -> tuple[Doc, ...]:
    """Up to `limit` related docs for slug.

    Resolution order:
    1. Explicit related: slugs from frontmatter (skipping unknown).
    2. Tag-overlap candidates in the same category, scored by shared-tag count.
    Never includes the doc itself.
    """
    if limit <= 0:
        return ()
    doc = get(slug)
    if doc is None:
        return ()

    all_ = all_docs()
    other = {d.slug: d for d in all_ if d.slug != slug}

    collected: list[Doc] = []

    # 1. Explicit related slugs.
    for raw_slug in doc.related:
        # Normalise: strip trailing .md if author included it
        s = raw_slug[:-3] if raw_slug.lower().endswith(".md") else raw_slug
        if s in other and len(collected) < limit:
            collected.append(other[s])
        elif s not in other:
            _log.debug(
                "docs_registry.related: slug %r in %r.related not found — skipping",
                s,
                slug,
            )

    if len(collected) >= limit:
        return tuple(collected[:limit])

    # 2. Tag-overlap fallback within same category.
    doc_tags = set(doc.tags)
    if doc_tags:
        candidates = [
            d for d in all_
            if d.slug != slug and d.category == doc.category and d not in collected
        ]
        scored = []
        for candidate in candidates:
            shared = len(doc_tags & set(candidate.tags))
            if shared > 0:
                scored.append((candidate, shared))
        scored.sort(key=lambda t: (-t[1], t[0].order, t[0].slug))
        for candidate, _ in scored:
            if len(collected) >= limit:
                break
            collected.append(candidate)

    return tuple(collected[:limit])
