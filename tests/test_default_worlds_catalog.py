"""WK-6 + WK-7: the shipped default World catalog.

Defaults (in lab/worlds/, scanned into the catalog): the `ai` World and the
`qukaizen` product World. The three demo Worlds (art-history, horticulture,
physics) are demoted to examples/worlds/ — not offered as defaults, but still
sealed and importable by path.
"""

from __future__ import annotations

import json
from pathlib import Path

from arail import world_mount as wm

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "lab" / "worlds"
EXAMPLES = REPO / "examples" / "worlds"

DEFAULTS = {"ai", "qukaizen"}
DEMOTED = {"art-history", "horticulture", "physics"}


def _bundle_dirs(root: Path) -> set[str]:
    return {d.name for d in root.iterdir()
            if d.is_dir() and (d / "manifest.json").exists()}


def test_catalog_holds_exactly_the_two_defaults():
    assert _bundle_dirs(CATALOG) == DEFAULTS


def test_demoted_worlds_moved_to_examples():
    present = _bundle_dirs(EXAMPLES)
    assert DEMOTED <= present
    # and they are NOT in the shipped catalog anymore
    assert not (DEMOTED & _bundle_dirs(CATALOG))


def test_qukaizen_world_seals_and_is_sourced():
    b = wm.load_bundle(CATALOG / "qukaizen")
    assert wm.verify_seal(b).ok
    man = json.loads((CATALOG / "qukaizen" / "manifest.json").read_text())
    assert man["provenance_tier"] == "sourced"          # human-authored from docs
    assert man["provenance_counts"]["model"] == 0        # never model-asserted


def test_qukaizen_graph_is_closed_and_connected():
    terms = json.loads((CATALOG / "qukaizen" / "terms.json").read_text())["terms"]
    slugs = {t["slug"] for t in terms}
    for t in terms:
        for r in t.get("related", []):
            assert r in slugs, f"{t['slug']} links dangling {r}"
        assert t.get("source"), f"{t['slug']} missing provenance"
    # the product story is represented across all four categories
    cats = {t["category"] for t in terms}
    assert cats == {"arail", "dac", "nucleus", "aerollm"}


def test_ai_world_seals():
    # The other shipped default — vendored qukaizen-dac export, seal intact.
    assert wm.verify_seal(wm.load_bundle(CATALOG / "ai")).ok


def test_shipped_worlds_have_story_taglines():
    """The welcome picker renders face.json taglines — both defaults need one."""
    for slug in DEFAULTS:
        face = json.loads((CATALOG / slug / "face.json").read_text())
        assert str(face.get("tagline", "")).strip(), f"{slug} missing tagline"


def test_demoted_examples_still_seal_valid():
    # examples remain importable — a broken seal would make import fail
    for slug in DEMOTED:
        assert wm.verify_seal(wm.load_bundle(EXAMPLES / slug)).ok, slug
