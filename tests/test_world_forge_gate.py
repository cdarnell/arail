"""Parity tests for the world_forge gate/provenance/loose-JSON ports.

Table-driven against the documented behavior of DaC's src/gate.ts and
src/provenance.ts (the canonical implementations).
"""

from __future__ import annotations

import pytest

from arail.world_forge import (
    assert_closed_sourced_graph,
    compute_provenance_tier,
    first_array,
    loose_json,
    slugify,
    tier_of_source,
)


def _t(slug, category="c1", source="model:test", related=None, **kw):
    return {"slug": slug, "term": slug, "category": category,
            "source": source, "related": related or [], **kw}


# ── gate ────────────────────────────────────────────────────────────────


def test_empty_corpus_vacuously_ok():
    r = assert_closed_sourced_graph([], {"c1"})
    assert r.ok and not r.dangling_edges and not r.unsourced


def test_happy_closed_graph_passes():
    terms = [_t("a", related=["b"]), _t("b", related=["a"])]
    assert assert_closed_sourced_graph(terms, {"c1"}).ok


def test_dangling_edge_fails():
    r = assert_closed_sourced_graph([_t("a", related=["ghost"])], {"c1"})
    assert not r.ok and r.dangling_edges == [("a", "ghost")]


def test_self_edge_resolves_like_any_other():
    r = assert_closed_sourced_graph([_t("a", related=["a"])], {"c1"})
    assert r.ok  # the gate applies no special meaning to self-edges


def test_dict_shaped_edges_resolve():
    r = assert_closed_sourced_graph(
        [_t("a", related=[{"slug": "b", "rel": "part-of"}]), _t("b")], {"c1"})
    assert r.ok


def test_blank_edge_targets_skipped():
    r = assert_closed_sourced_graph([_t("a", related=["", "  ", {"slug": ""}])], {"c1"})
    assert r.ok


def test_unsourced_fails():
    r = assert_closed_sourced_graph([_t("a", source="  ")], {"c1"})
    assert not r.ok and r.unsourced == ["a"]


def test_undeclared_category_fails():
    r = assert_closed_sourced_graph([_t("a", category="mystery")], {"c1"})
    assert not r.ok and r.undeclared_category == [("a", "mystery")]


def test_missing_slug_reported_not_thrown():
    r = assert_closed_sourced_graph([{"term": "x", "category": "c1", "source": "s"}], {"c1"})
    assert not r.ok
    assert ("<missing-slug>", "c1") in r.undeclared_category


# ── provenance ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("src,expected", [
    ("model:llama-ai-eng", "model-asserted"),
    ("model:qwen2.5:7b", "model-asserted"),        # colon-in-body is load-bearing
    ("model:aerollm/llama-70b", "model-asserted"),
    ("MODEL:QWEN2.5/7B", "model-asserted"),        # case-insensitive
    ("QuKaiZen AI Dictionary", "sourced"),
    ("https://example.org/paper", "sourced"),
    ("operator:my-lab", "sourced"),
    ("", "sourced"),                                # gate owns emptiness
    (None, "sourced"),
    ("model:", "sourced"),                          # needs a body
])
def test_tier_of_source(src, expected):
    assert tier_of_source(src) == expected


def test_rollup_tiers():
    tier, counts = compute_provenance_tier(["model:a", "model:b"])
    assert tier == "model-asserted" and counts == {"model": 2, "sourced": 0, "total": 2}
    tier, _ = compute_provenance_tier(["a paper", "another"])
    assert tier == "sourced"
    tier, counts = compute_provenance_tier(["model:a", "a paper"])
    assert tier == "mixed" and counts["model"] == 1
    tier, _ = compute_provenance_tier([])
    assert tier == "sourced"


# ── loose_json / first_array (small-model robustness) ───────────────────


@pytest.mark.parametrize("raw,expected", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('Sure! Here is the JSON:\n[{"term": "x"}]\nHope that helps!', [{"term": "x"}]),
    ('{"a": 1,}', {"a": 1}),                        # trailing comma repaired
    ('[1, 2, 3,]', [1, 2, 3]),
    ("not json at all", None),
    ("", None),
    (None, None),
])
def test_loose_json(raw, expected):
    assert loose_json(raw) == expected


def test_first_array_unwraps_arbitrary_keys():
    assert first_array({"stuff": [1, 2]}) == [1, 2]
    assert first_array([3]) == [3]
    assert first_array({"a": "b"}) == []
    assert first_array(None) == []


def test_slugify():
    assert slugify("Snake Plant!") == "snake-plant"
    assert slugify("  Déjà vu  ") == "d-j-vu"
    assert len(slugify("x" * 100)) == 48
