#!/usr/bin/env python3
"""Forge the sealed "World of Debt Finance" bundle from its authored inputs.

Authoring inputs live in ``scripts/worlds_src/debt-finance/`` and are the
reviewable source of truth; the sealed bundle is written to
``examples/worlds/debt-finance/`` — an **example** bundle (like horticulture,
physics, art-history), not a catalog default. A fresh lab does not mount this
World automatically; the operator imports it from the Worlds page (or
``POST /api/worlds/import``) when they want it. That is a deliberate choice
for a personal-finance domain — see
``sprints/2026-07-26-world-of-debt-finance/ARCHITECTURE.md`` and
``BUILD_LOG.md`` for why.

Run it from the repo root::

    PYTHONPATH=src python scripts/forge_debt_finance_world.py

The run is deterministic: with unchanged inputs it reproduces byte-identical
output, so a second run leaves the working tree clean.

Two checks beyond the standard ``video-games`` template
(``scripts/forge_video_games_world.py``), both closing findings from the
architecture's Technical-Feasibility review:

1. **Evaluative-language scan** — every term's short/definition/example is
   scanned for the same evaluative/imperative vocabulary the runtime
   guardrail (``arail.agents.debt_finance_compliance``) blocks, so an
   evaluative phrase never even reaches sealed content.
2. **Agenda ordering assertion** — after sealing, ``agenda.json.watches[]``
   is checked against the exact set of feed URLs this World intends to be
   live (the first three ``url``-kind ``knowledge_sources[]`` entries) —
   catching a misordering at authoring time, not as "scouting has nothing to
   do and nobody knows why" later.

The seal-exempt ``compliance/DISCLAIMER.md`` sibling is merged in after
sealing, the same tier as ``SKILL.md``/``capabilities.json``.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from arail import world_forge as wf
from arail import world_mount as wm
from arail.world_theme import parse_world_theme

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts" / "worlds_src" / "debt-finance"
OUT = ROOT / "examples" / "worlds" / "debt-finance"

# Pinned so re-runs are byte-identical; the sealer would otherwise stamp now().
CREATED_AT = "2026-07-26T00:00:00.000Z"

# The same heuristic vocabulary the runtime guardrail blocks
# (arail.agents.debt_finance_compliance.EVALUATIVE_RE) — kept as an
# independently-maintained copy here rather than importing arail.agents at
# authoring time, so a change to one is a deliberate edit to both, not a
# silent shared dependency.
_EVALUATIVE_RE = re.compile(
    r"\b(best|guaranteed|top[- ]pick|lowest|you should|you must|top choice)\b",
    re.I,
)


def _load(name: str) -> object:
    return json.loads((SRC / name).read_text(encoding="utf-8"))


def preflight(spec: dict, terms: list[dict], face: dict) -> list[str]:
    """Every check that can refuse the bundle, reported in one pass."""
    problems: list[str] = []

    declared = [str(c.get("id", "")) for c in spec.get("categories", [])]
    gate = wf.assert_closed_sourced_graph(terms, declared)
    if not gate.ok:
        problems.extend(f"gate: unsourced {v}" for v in gate.unsourced)
        problems.extend(f"gate: undeclared_category {v}" for v in gate.undeclared_category)
        problems.extend(f"gate: dangling_edge {v}" for v in gate.dangling_edges)

    theme_spec, reason = parse_world_theme(face.get("theme"), spec.get("slug", "?"))
    if theme_spec is None:
        problems.append(f"theme: {reason}")

    try:
        wf.validate_bundle_content(face, spec, terms)
    except wf.ContentInvalid as exc:
        problems.append(f"content: {exc}")

    if len(terms) > wf.MAX_TERMS_SOFT:
        problems.append(f"budget: {len(terms)} terms exceeds {wf.MAX_TERMS_SOFT}")
    budgets = (("short", wf.MAX_SHORT), ("definition", wf.MAX_DEFINITION),
               ("example", wf.MAX_EXAMPLE))
    for t in terms:
        slug = t.get("slug", "?")
        for field, limit in budgets:
            if len(str(t.get(field, ""))) > limit:
                problems.append(
                    f"budget: {slug}.{field} is {len(str(t[field]))} chars (max {limit})")
        if len(t.get("related", [])) > wf.MAX_RELATED_PER_TERM:
            problems.append(
                f"budget: {slug} has {len(t['related'])} related "
                f"(max {wf.MAX_RELATED_PER_TERM})")

    tier, counts = wf.compute_provenance_tier([str(t.get("source", "")) for t in terms])
    if tier != "sourced" or counts.get("model"):
        problems.append(f"provenance: expected a fully sourced World, got {tier} {counts}")

    # New: evaluative/imperative language must never reach sealed content —
    # this is the authoring-time half of the runtime guardrail.
    for t in terms:
        slug = t.get("term", "?")
        for field in ("short", "definition", "example"):
            value = str(t.get(field, ""))
            if _EVALUATIVE_RE.search(value):
                problems.append(
                    f"language: {slug}.{field} contains evaluative/imperative "
                    f"language — descriptive only, per §7.2's guardrail")

    return problems


def merge_compliance_disclaimer() -> None:
    """Copy the seal-exempt compliance/DISCLAIMER.md sibling into the bundle.

    Not part of the six sealed files (terms/spec/roster/face/agenda/
    drift-report) — same tier as SKILL.md/capabilities.json/arail-plugin.json.
    Both agents' precondition check (debt_finance_compliance.read_disclaimer)
    reads this file fresh from the mounted World every time, never cached.
    """
    src = SRC / "compliance" / "DISCLAIMER.md"
    dest_dir = OUT / "compliance"
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / "DISCLAIMER.md")


def assert_agenda_ordering(spec: dict) -> list[str]:
    """Confirm agenda.json.watches[] contains exactly the intended feed URLs.

    dac_world/seal.py derives watches from the first 3 knowledge_sources[]
    entries by raw array position, regardless of kind (verified against
    source — see ARCHITECTURE.md §2.8). This asserts the ordering rule
    (URL-kind sources first) actually produced the intended live watches,
    catching a misordering here rather than as "scouting has nothing to do."
    """
    problems: list[str] = []
    intended = [
        str(s.get("ref"))
        for s in (spec.get("knowledge_sources") or [])[:3]
        if isinstance(s, dict) and str(s.get("kind")) == "url"
    ]
    agenda = json.loads((OUT / "agenda.json").read_text(encoding="utf-8"))
    got = sorted(
        feed
        for watch in agenda.get("watches", [])
        for feed in watch.get("feeds", [])
    )
    if sorted(intended) != got:
        problems.append(
            f"agenda: expected watches {sorted(intended)!r}, got {got!r} — "
            f"a knowledge_sources[] ordering change silently dropped a feed")
    return problems


def main() -> int:
    spec = _load("spec.json")
    terms = _load("terms.json")["terms"]
    face = _load("face.json")

    problems = preflight(spec, terms, face)
    if problems:
        print(f"refusing to forge — {len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    wf.write_bundle(OUT, spec, terms,
                    face_overrides=face,
                    theme_validator=parse_world_theme,
                    created_at=CREATED_AT)
    merge_compliance_disclaimer()

    bundle = wm.load_bundle(OUT)
    seal = wm.verify_seal(bundle)
    if not seal.ok:
        print(f"sealed bundle failed verification: {seal.reason}", file=sys.stderr)
        return 1
    wm.check_compat(bundle)
    wm.check_categories(bundle)

    agenda_problems = assert_agenda_ordering(spec)
    if agenda_problems:
        for p in agenda_problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    if not (OUT / "compliance" / "DISCLAIMER.md").exists():
        print("compliance/DISCLAIMER.md missing after merge", file=sys.stderr)
        return 1

    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    print(f"forged {manifest['world']} — {len(terms)} terms, "
          f"{manifest['provenance_tier']} ({manifest['provenance_counts']})")
    print(f"  world_sha256 {manifest['world_sha256']}")
    print(f"  -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
