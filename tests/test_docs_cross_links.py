"""Cross-link audit for the docs/ corpus — docs-hub-sprint-3.

Every internal `[label](target.md[#anchor])` link in a registered doc must
resolve to a file that exists on disk.  Links that point outside the docs/
directory to known repo-root assets are on an explicit allowlist so they do
not generate false positives.

Failure modes covered:
  F3 — cross-link false positive (repo-root asset not in registry but
       legitimately reachable).  Resolved by the ALLOWLIST set.
  F4 — cross-link false negative (broken link hidden inside a fenced code
       block).  Resolved by stripping fences before the regex sweep.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Markdown link pattern: [label](path.md) or [label](path.md#anchor)
# Only catches links whose target ends in .md (with optional #anchor).
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+\.md[^)]*)\)")

# Fenced code block pattern — same as arail.wiki._FENCED_RE so the audit
# reuses the proven strip logic without importing arail.wiki.
_FENCED_RE = re.compile(r"```[\s\S]*?```|`[^`\n]+`", re.MULTILINE)

# Explicit allowlist: relative paths from the repo root that are legitimate
# link targets but live outside docs/ and may not be in the registry.
# This list should stay small.  If you need to add to it, add a comment
# explaining why the target is not in docs/.
_REPO_ROOT_ALLOWLIST: frozenset[str] = frozenset(
    {
        "README.md",
        "AGENTS.md",
        "CLAUDE.md",
        "CONTRIBUTING.md",
        "ROADMAP.md",
        "BLUEPRINTS.md",
        "design.md",          # repo-root design doc (not the renamed docs/ one)
        "scripts/setup.sh",   # shell script, not .md but kept for symmetry
    }
)

# Allowlist pins how many entries are expected at most.  If this assertion
# starts failing it means the allowlist grew unexpectedly — a reviewer should
# check whether the new entry belongs in docs/ instead.
_ALLOWLIST_MAX_SIZE = 10


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    """Replace fenced/inline code runs with spaces (preserves offsets)."""
    return _FENCED_RE.sub(lambda m: " " * len(m.group(0)), text)


def _repo_root() -> Path:
    """Best-effort repo root: parent of tests/."""
    return Path(__file__).parent.parent


def _collect_broken_links() -> list[tuple[str, str, Path]]:
    """Return (slug, raw_target, resolved_path) for every broken internal link
    in the registered docs corpus.

    A link is 'broken' if:
    - The target ends in .md
    - The target is not an external URL (http/https) or anchor-only (#…)
    - The resolved path does not exist on disk
    - The resolved path is not covered by _REPO_ROOT_ALLOWLIST
    """
    import sys
    sys.path.insert(0, str(_repo_root() / "src"))
    from arail.portal.docs_registry import all_docs, _invalidate_cache  # noqa: PLC0415

    _invalidate_cache()
    docs = all_docs()
    root = _repo_root()

    broken: list[tuple[str, str, Path]] = []
    for doc in docs:
        p = Path(doc.path)
        if not p.exists():
            continue
        text = _strip_fences(p.read_text(errors="replace"))
        for m in _MD_LINK_RE.finditer(text):
            raw = m.group(1)
            # Strip fragment
            target_path_str = raw.split("#")[0].strip()
            if not target_path_str:
                continue
            # Skip external URLs
            if target_path_str.startswith(("http://", "https://", "mailto:")):
                continue
            # Must end in .md
            if not target_path_str.lower().endswith(".md"):
                continue
            # Resolve relative to the doc's directory
            resolved = (p.parent / target_path_str).resolve()
            if resolved.exists():
                continue
            # Check allowlist: resolve relative to repo root too
            rel_from_root = target_path_str.lstrip("./")
            if rel_from_root in _REPO_ROOT_ALLOWLIST:
                continue
            # Also check if just the filename is allowlisted
            if Path(target_path_str).name in _REPO_ROOT_ALLOWLIST:
                continue
            broken.append((doc.slug, raw, resolved))
    return broken


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_cross_link_audit_all_internal_links_resolve():
    """Every internal [label](target.md) link in the registered docs corpus
    must resolve to an existing file (F3, F4).

    If this test fails: edit the doc to fix the broken link.  Widening the
    allowlist is only acceptable for links to legitimate repo-root assets
    that are deliberately outside docs/.
    """
    broken = _collect_broken_links()
    if broken:
        lines = ["Broken internal links found in registered docs:"]
        for slug, raw, resolved in broken:
            lines.append(f"  {slug}: [{raw}] → {resolved} (not found)")
        pytest.fail("\n".join(lines))


def test_cross_link_audit_allowlist_is_minimal():
    """Allowlist size is pinned.  If it grows unexpectedly, a reviewer must
    confirm the new entry belongs in repo-root rather than docs/.
    """
    assert len(_REPO_ROOT_ALLOWLIST) <= _ALLOWLIST_MAX_SIZE, (
        f"_REPO_ROOT_ALLOWLIST has {len(_REPO_ROOT_ALLOWLIST)} entries, "
        f"exceeds pinned max of {_ALLOWLIST_MAX_SIZE}.  "
        "Review additions before raising the cap."
    )


def test_cross_link_audit_code_fence_false_negative_is_blocked():
    """A broken link that lives inside a fenced code block must NOT cause the
    audit to fail — the fence-strip logic (F4) prevents false negatives.

    The test creates a synthetic doc text with a broken link inside a fence
    and asserts _strip_fences removes it before the regex sweep.
    """
    doc_with_fenced_broken_link = (
        "# Example\n\n"
        "```\n"
        "[broken link inside fence](./does-not-exist.md)\n"
        "```\n\n"
        "Real content here.\n"
    )
    stripped = _strip_fences(doc_with_fenced_broken_link)
    # After stripping, the markdown link pattern must not match the fenced link.
    matches = list(_MD_LINK_RE.finditer(stripped))
    assert not matches, (
        "The fenced broken link was NOT stripped — fence-stripping is broken (F4). "
        f"Remaining matches: {[m.group(0) for m in matches]}"
    )


def test_cross_link_audit_real_link_outside_fence_is_caught():
    """A broken link outside a code fence IS caught by the regex (positive case)."""
    doc_with_real_broken_link = (
        "# Example\n\n"
        "[broken link](./does-not-exist.md)\n"
    )
    stripped = _strip_fences(doc_with_real_broken_link)
    matches = list(_MD_LINK_RE.finditer(stripped))
    assert len(matches) == 1, (
        "A plain broken link was not caught by the regex — audit logic is broken."
    )


@pytest.mark.perf
def test_cross_link_audit_perf_under_one_second():
    """Full cross-link audit on the live corpus completes in <1s (F10)."""
    t0 = time.perf_counter()
    _collect_broken_links()
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, (
        f"Cross-link audit took {elapsed:.2f}s — exceeds 1.0s budget (F10)"
    )
