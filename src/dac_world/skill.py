"""SKILL.md renderer -- port of DaC's ``src/arail-export/skill.ts``.

Moved verbatim from qukaizen-arail's ``src/arail/world_forge.py`` as part of
the ``dac_world`` migration — see
``sprints/2026-07-19-dac-generates-arail-worlds/ARCHITECTURE.md`` (qukaizen-dac).
"""

from __future__ import annotations

import re
from typing import Optional

# skills_loader body cap is 56K chars; warn with margin (~300 chars/term).
SKILL_CHAR_BUDGET = 48_000
SKILL_CHARS_PER_TERM = 300

_BODY_CONTROL_RE = re.compile(r"^([#\->`])")


def estimate_skill_chars(n_terms: int) -> int:
    return n_terms * SKILL_CHARS_PER_TERM + 1200


def sanitize_frontmatter_scalar(s: str) -> str:
    """F1: collapse CR/LF, trim, double-quote with internal escapes."""
    flat = re.sub(r"[\r\n]+", " ", str(s)).strip()
    return '"' + flat.replace("\\", "\\\\").replace('"', '\\"') + '"'


def sanitize_body_field(s: str) -> str:
    """F2: collapse CR/LF to a space; ZWNJ-neutralize a leading control token."""
    flat = re.sub(r"[\r\n]+", " ", str(s)).strip()
    return _BODY_CONTROL_RE.sub("‌\\1", flat)


def _cmp_key(s: str) -> str:
    return s.casefold()


def _skill_terms_capped(terms: list[dict]) -> tuple[list[dict], Optional[str]]:
    """Pick which terms SKILL.md carries. skills_loader caps the body at ~56K
    chars, so a big World (e.g. 512 fetched terms) can't render every term into
    the agent prompt. Keep the most CONNECTED terms (highest related-degree —
    the concepts the World hangs off of) up to the char budget, and return an
    honest note so agents know the full glossary lives in the Knowledge Base.
    Small Worlds render whole (note=None)."""
    if estimate_skill_chars(len(terms)) <= SKILL_CHAR_BUDGET:
        return terms, None
    # degree = inbound+outbound related edges
    indeg: dict[str, int] = {}
    for t in terms:
        for r in (t.get("related") or []):
            rs = str(r).strip()
            if rs:
                indeg[rs] = indeg.get(rs, 0) + 1

    def _degree(t: dict) -> int:
        return len(t.get("related") or []) + indeg.get(str(t.get("slug", "")), 0)

    # how many terms fit the budget (estimate_skill_chars is ~linear per term)
    per_term = max(1, estimate_skill_chars(100) // 100)
    n = max(1, min(len(terms), SKILL_CHAR_BUDGET // per_term))
    ranked = sorted(terms, key=lambda t: (-_degree(t), str(t.get("slug", ""))))
    kept = ranked[:n]
    note = (f"This World has {len(terms)} terms; the {len(kept)} most connected "
            "are shown here. The full glossary lives in the Knowledge Base.")
    return kept, note


def render_world_skill(spec: dict, face: dict, terms: list[dict], world_sha: str,
                       *, extra_note: Optional[str] = None) -> str:
    """SKILL.md in the exact shape skills_loader parses. Pure projection of
    gated fields (slug/term/short/source) — the honesty rail."""
    slug = str(spec.get("slug", ""))
    display_raw = str(spec.get("display_name", slug))
    display_fm = sanitize_frontmatter_scalar(display_raw)
    display_body = sanitize_body_field(display_raw)
    prov_tier = str(face.get("provenance_tier", ""))

    cat_label = {str(c.get("id", "")): str(c.get("label") or c.get("id", ""))
                 for c in spec.get("categories", []) if isinstance(c, dict)}

    by_cat: dict[str, list[dict]] = {}
    for t in terms:
        by_cat.setdefault(str(t.get("category", "")), []).append(t)
    sorted_cats = sorted(by_cat, key=_cmp_key)
    for cat in sorted_cats:
        by_cat[cat].sort(key=lambda t: _cmp_key(str(t.get("slug", ""))))

    frontmatter = "\n".join([
        "---",
        f"title: {display_fm}",
        f"id: world-{slug}",
        f"name: {display_fm}",
        f"domain: {slug}",
        'version: "1.0.0"',
        f"tags: [world, knowledge, {slug}]",
        "when_to_use:",
        f"  - When the user asks about {display_body} or its declared categories",
        "  - When grounding a claim that falls inside this World's domain",
        "when_not_to_use:",
        "  - When the question is outside this World's declared categories",
        "  - When a claim cannot be tied to one of this World's sourced terms (say so; don't invent)",
        "---",
    ])

    prov_line = (
        "Every term in this World is grounded in a cited source."
        if prov_tier == "sourced"
        else "Some terms are model-asserted (unverified); cite a source when promoting them."
        if prov_tier == "mixed"
        else "This World was DREAMED by a model — terms are model-asserted and UNVERIFIED."
    )
    rail_line = ("Answer only from the terms below. Every term lists its source. "
                 "If a question cannot be answered from these terms, say the World "
                 "does not cover it — do not invent.")

    sections: list[str] = []
    for cat in sorted_cats:
        lines: list[str] = []
        for t in by_cat[cat]:
            term_safe = sanitize_body_field(str(t.get("term", "")))
            slug_safe = sanitize_body_field(str(t.get("slug", "")))
            short_safe = sanitize_body_field(str(t.get("short", "")))
            source_safe = sanitize_body_field(str(t.get("source", "")))
            lines.append(f"- **{term_safe}** (`{slug_safe}`) — {short_safe}")
            lines.append(f"  - Source: {source_safe}")
        label = sanitize_body_field(cat_label.get(cat, cat))
        sections.append(f"### {label}\n\n" + "\n".join(lines))

    body_parts = [
        sanitize_body_field(str(face.get("domain_framing", ""))),
        "",
        prov_line,
    ]
    if extra_note:
        body_parts += ["", f"_{sanitize_body_field(extra_note)}_"]
    body_parts += [
        "",
        f"_{rail_line}_",
        "",
        "\n\n".join(sections),
        "",
        f"<!-- dac:world_sha256 {world_sha} -->",
    ]
    body = "\n".join(body_parts)
    return frontmatter + "\n" + body + "\n"
