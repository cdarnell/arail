"""Parse ``lab/pkb/research/program.md`` into a structured recipe.

The autoresearch loop (``arail.experiments.autoresearch``) calls
:func:`parse_program` to discover whether the user (or the drafter)
has overridden the hardcoded candidate list. When the file is missing
or has no ``## Knobs`` block, every field is None / [] and the loop
keeps its existing behavior.

This is intentionally tolerant: a half-edited program.md should
still parse — missing sections degrade gracefully.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


Candidate = tuple[str, dict[str, Any]]


@dataclass
class ProgramRecipe:
    """Structured view of program.md.

    All fields are optional — consumers should default to their own
    fallbacks when a field is empty. ``knobs`` is the list autoresearch
    iterates over instead of its hardcoded ``CANDIDATES``.
    """

    goal: str = ""
    intent: str = ""
    drafted_at: str = ""
    auto_drafted: bool = False
    fetched_external: bool = False
    hypotheses: list[str] = field(default_factory=list)
    success_metrics: dict[str, Any] = field(default_factory=dict)
    knobs: list[Candidate] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FENCED_YAML_RE = re.compile(r"```ya?ml\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def parse_program(path: Path | str) -> ProgramRecipe | None:
    """Read ``program.md`` and return a :class:`ProgramRecipe`.

    Returns ``None`` if the file doesn't exist. Returns a recipe with
    only the fields it could parse on partial success — never raises
    for malformed sections.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        text = p.read_text()
    except OSError:
        return None

    recipe = ProgramRecipe()

    # ── Frontmatter ──
    fm_match = _FRONTMATTER_RE.match(text)
    if fm_match:
        try:
            fm = yaml.safe_load(fm_match.group(1)) or {}
            if isinstance(fm, dict):
                recipe.goal = str(fm.get("goal", ""))
                recipe.intent = str(fm.get("intent", ""))
                recipe.drafted_at = str(fm.get("drafted_at", ""))
                recipe.auto_drafted = bool(fm.get("auto_drafted", False))
                recipe.fetched_external = bool(fm.get("fetched_external", False))
        except yaml.YAMLError:
            pass
        body = text[fm_match.end():]
    else:
        body = text

    # ── Sections (split on h2) ──
    sections = _split_sections(body)

    if "Hypotheses worth testing" in sections:
        recipe.hypotheses = _parse_numbered_or_bulleted(sections["Hypotheses worth testing"])
    elif "Hypotheses" in sections:
        recipe.hypotheses = _parse_numbered_or_bulleted(sections["Hypotheses"])

    if "Success criteria" in sections:
        recipe.success_metrics = _parse_bullet_kvs(sections["Success criteria"])

    if "Knobs" in sections:
        recipe.knobs = _parse_knobs_block(sections["Knobs"])

    if "Sources" in sections:
        recipe.sources = _parse_sources(sections["Sources"])

    return recipe


# -- internals ------------------------------------------------------------

def _split_sections(body: str) -> dict[str, str]:
    """Map h2 heading title → body text (until next h2)."""
    out: dict[str, str] = {}
    matches = list(_HEADING_RE.finditer(body))
    h2s = [m for m in matches if len(m.group(1)) == 2]
    for i, m in enumerate(h2s):
        title = m.group(2).strip()
        start = m.end()
        end = h2s[i + 1].start() if i + 1 < len(h2s) else len(body)
        out[title] = body[start:end].strip()
    return out


def _parse_numbered_or_bulleted(section: str) -> list[str]:
    """Pull list items out of a section. Strips bold markers + numbers."""
    out: list[str] = []
    for raw in section.splitlines():
        line = raw.strip()
        if not line:
            continue
        # "1. **text** — context" or "- item"
        m = re.match(r"^(?:\d+\.|[-*])\s+(.+)$", line)
        if not m:
            continue
        item = m.group(1).strip()
        # Strip leading bold (**...**) and an em-dash continuation.
        bold = re.match(r"^\*\*(.+?)\*\*\s*(?:[—-]\s*.*)?$", item)
        if bold:
            item = bold.group(1).strip()
        out.append(item)
    return out


def _parse_bullet_kvs(section: str) -> dict[str, Any]:
    """Pull ``- **key** — value`` pairs out of a bulleted section."""
    out: dict[str, Any] = {}
    for raw in section.splitlines():
        line = raw.strip()
        m = re.match(r"^[-*]\s+\*\*(.+?)\*\*\s*[—-]\s*(.+)$", line)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def _parse_knobs_block(section: str) -> list[Candidate]:
    """Find the first ```yaml fenced block and parse it as candidates.

    Each candidate is ``{label: str, knobs: dict}``. We tolerate
    user-edited blocks that drop the wrapping list, that omit the
    ``label`` key, or that put bare ``key: value`` pairs (treated as
    a single un-labeled candidate).
    """
    fence = _FENCED_YAML_RE.search(section)
    if not fence:
        return []
    try:
        data = yaml.safe_load(fence.group(1))
    except yaml.YAMLError:
        return []
    if data is None:
        return []

    out: list[Candidate] = []
    if isinstance(data, list):
        for entry in data:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or f"variant-{len(out) + 1}")
            knobs = entry.get("knobs")
            if isinstance(knobs, dict) and knobs:
                out.append((label, knobs))
            else:
                # Allow {label, key1: val, key2: val} flat form.
                bare = {k: v for k, v in entry.items() if k != "label"}
                if bare:
                    out.append((label, bare))
    elif isinstance(data, dict):
        # Single bare dict → one candidate with no label.
        out.append(("variant-1", data))
    return out


def _parse_sources(section: str) -> list[dict[str, str]]:
    """Pull ``- [title](url)`` markdown links into structured dicts."""
    out: list[dict[str, str]] = []
    link_re = re.compile(r"^[-*]\s+\[(?P<title>.+?)\]\((?P<url>.+?)\)(?:\s+[—-]\s+(?P<why>.+))?\s*$")
    for raw in section.splitlines():
        m = link_re.match(raw.strip())
        if m:
            out.append({
                "title": m.group("title").strip(),
                "url": m.group("url").strip(),
                "why": (m.group("why") or "").strip(),
            })
    return out
