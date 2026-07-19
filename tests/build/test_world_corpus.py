"""arail.build.world_corpus: field mapping, category/approval filtering,
mount-swap survival, chunking, tagging, and the full orchestration against a
fake NucleusClient.
"""

from __future__ import annotations

import json

import pytest

from arail.build import world_corpus as wc


# ── term_to_kice_example / _infer_layer ──────────────────────────────

def test_term_to_kice_example_field_mapping():
    term = {
        "slug": "depth-of-field", "term": "Depth of Field",
        "category": "exposure",
        "short": "The range of distance in a photo that appears sharp.",
        "definition": "Controlled primarily by aperture.",
        "example": "Stopping down to f/11 for a product shot.",
        "related": ["aperture", "bokeh"],
        "source": "Bryan Peterson, Understanding Exposure",
    }
    ex = wc.term_to_kice_example(term)
    assert ex["id"] == "world-depth-of-field"
    assert ex["subdomain"] == "exposure"
    assert ex["source_type"] == "world_term"
    assert ex["title"] == "Depth of Field"
    assert "Controlled primarily by aperture." in ex["content"]
    assert "Stopping down to f/11" in ex["content"]
    assert "Bryan Peterson" in ex["content"]
    assert ex["reasoning_prompt"].startswith("Explain Depth of Field")
    assert ex["quality_score"] == 0.7          # has a source


def test_quality_score_lower_without_source():
    term = {"slug": "x", "term": "X", "category": "gear", "definition": "d"}
    assert wc.term_to_kice_example(term)["quality_score"] == 0.5


def test_infer_layer_default_is_1():
    term = {"definition": "A plain factual statement.", "example": ""}
    assert wc._infer_layer(term) == 1


def test_infer_layer_6_ambiguity_cues():
    term = {"definition": "The correct exposure it depends on the scene.",
           "example": "Varies by lighting condition."}
    assert wc._infer_layer(term) == 6


def test_infer_layer_5_reasoning_cues():
    term = {"definition": ("Wider apertures blur backgrounds because the "
                          "circle of confusion grows; however, diffraction "
                          "sets a practical limit."),
           "example": ""}
    assert wc._infer_layer(term) == 5


def test_infer_layer_4_from_related_breadth():
    term = {"definition": "plain", "example": "",
           "related": ["a", "b", "c", "d"]}
    assert wc._infer_layer(term) == 4


# ── chunk / tag_source ────────────────────────────────────────────────

def test_chunk_sizing():
    items = list(range(37))
    chunks = wc.chunk(items, size=15)
    assert len(chunks) == 3
    assert [len(c) for c in chunks] == [15, 15, 7]


def test_tag_source_mutates_and_returns():
    records = [{"messages": []}, {"messages": []}]
    out = wc.tag_source(records, "tier2")
    assert out is records
    assert all(r["source"] == "tier2" for r in records)


# ── pull_approved_terms (synthetic World + approval fixtures) ─────────

@pytest.fixture
def synthetic_world(tmp_path):
    """A tiny 2-craft-category + 1-business-category World, mirroring the
    real photography bundle's on-disk shape closely enough to exercise
    pull_approved_terms end to end."""
    worlds_dir = tmp_path / "worlds"
    slug = "testworld"
    bundle_dir = worlds_dir / slug
    bundle_dir.mkdir(parents=True)
    terms = [
        {"slug": "wide-aperture", "term": "Wide Aperture", "category": "exposure",
         "definition": "d1", "source": "s1"},
        {"slug": "golden-hour", "term": "Golden Hour", "category": "light",
         "definition": "d2", "source": "s2"},
        {"slug": "not-approved-yet", "term": "Not Approved", "category": "exposure",
         "definition": "d3", "source": "s3"},
        {"slug": "wix-thing", "term": "Wix Thing", "category": "web-platform",
         "definition": "d4", "source": "s4"},
    ]
    (bundle_dir / "terms.json").write_text(json.dumps({"terms": terms}))
    (bundle_dir / "spec.json").write_text(json.dumps({"categories": [
        {"id": "exposure", "label": "Exposure"},
        {"id": "light", "label": "Light"},
        {"id": "web-platform", "label": "Web Platform"},
        {"id": "empty-cat", "label": "Empty Category"}]}))

    pkb_root = tmp_path / "pkb"
    kb_dir = pkb_root / "compiled" / "kb"
    kb_dir.mkdir(parents=True)
    # Approve everything except "not-approved-yet".
    approved = [
        {"path": f"sources/world-{slug}/terms/wide-aperture.md"},
        {"path": f"sources/world-{slug}/terms/golden-hour.md"},
        {"path": f"sources/world-{slug}/terms/wix-thing.md"},
    ]
    (kb_dir / "approved.json").write_text(json.dumps(approved))
    return {"worlds_dir": worlds_dir, "pkb_root": pkb_root, "slug": slug}


def test_pull_approved_terms_category_and_approval_filter(synthetic_world):
    terms = wc.pull_approved_terms(
        synthetic_world["slug"], categories=("exposure", "light"),
        worlds_dir=synthetic_world["worlds_dir"],
        pkb_root=synthetic_world["pkb_root"])
    slugs = [t["slug"] for t in terms]
    assert slugs == ["wide-aperture", "golden-hour"]   # sorted by spec order
    # not-approved-yet excluded despite matching category (correction: the
    # approval gate governs retrieval eligibility, independent of DaC's
    # own curation confidence).
    assert "not-approved-yet" not in slugs
    # wix-thing excluded by category filter even though it IS approved.
    assert "wix-thing" not in slugs


def test_pull_approved_terms_business_category_when_requested(synthetic_world):
    terms = wc.pull_approved_terms(
        synthetic_world["slug"], categories=("web-platform",),
        worlds_dir=synthetic_world["worlds_dir"],
        pkb_root=synthetic_world["pkb_root"])
    assert [t["slug"] for t in terms] == ["wix-thing"]


def test_pull_survives_simulated_remount_sweep(synthetic_world, monkeypatch):
    """Regression for the mount-swap correction: world_mount._sweep_other_worlds
    deletes STAGED markdown (sources/world-<slug>/) when a different World is
    mounted, but the catalog copy (WORLDS_DIR/<slug>/) and approved.json are
    untouched — pull_approved_terms must keep working after that sweep."""
    staged = synthetic_world["pkb_root"] / "sources" / f"world-{synthetic_world['slug']}"
    staged.mkdir(parents=True)
    (staged / "terms").mkdir()
    (staged / "terms" / "wide-aperture.md").write_text("---\ntitle: x\n---\n")
    assert staged.exists()

    import shutil
    shutil.rmtree(staged)   # simulate _sweep_other_worlds
    assert not staged.exists()

    terms = wc.pull_approved_terms(
        synthetic_world["slug"], categories=("exposure",),
        worlds_dir=synthetic_world["worlds_dir"],
        pkb_root=synthetic_world["pkb_root"])
    assert [t["slug"] for t in terms] == ["wide-aperture"]


def test_resolve_world_bundle_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        wc.resolve_world_bundle("nope", worlds_dir=tmp_path)


# ── build_world_corpus orchestration (fake client + job store) ────────

class _FakeJobStore:
    def __init__(self):
        self.updates = []

    def update(self, run_id, **fields):
        self.updates.append((run_id, fields))


class _FakeClient:
    def __init__(self):
        self.synthesize_calls = []
        self.train_calls = []

    def synthesize(self, examples, corpus_version=0, timeout=600.0):
        self.synthesize_calls.append(examples)
        records = [{"messages": [{"role": "user", "content": ex["title"]}]}
                   for ex in examples]
        return {"dataset_size": len(records), "training_records": records}

    def train_direct(self, dataset, *, run_id="", config_overrides=None, timeout=30.0):
        self.train_calls.append((run_id, dataset))
        return {"status": "started", "run_id": run_id}


def test_build_world_corpus_end_to_end(synthetic_world):
    client = _FakeClient()
    store = _FakeJobStore()
    result = wc.build_world_corpus(
        synthetic_world["slug"], "run-1",
        categories=("exposure", "light"),
        client=client, job_store=store, batch_size=10,
        worlds_dir=synthetic_world["worlds_dir"],
        pkb_root=synthetic_world["pkb_root"])

    assert result["term_count"] == 2
    assert result["record_count"] == 2
    assert len(client.synthesize_calls) == 1        # one batch, no tier2
    assert len(client.train_calls) == 1
    run_id, dataset = client.train_calls[0]
    assert run_id == "run-1"
    assert all(r["source"] == "tier1" for r in dataset)

    phases = [f["phase"] for _, f in store.updates if "phase" in f]
    # "synthesize_tier1" fires once before the batch loop plus once per
    # batch's on_progress callback (one batch here) — assert the invariant
    # (pull first, train/training last, synthesize_tier1 present) rather
    # than an exact count that would be brittle to batch_size changes.
    assert phases[0] == "pull"
    assert phases[-2:] == ["train", "training"]
    assert "synthesize_tier1" in phases


def test_build_world_corpus_tier2_split(synthetic_world):
    client = _FakeClient()
    store = _FakeJobStore()
    result = wc.build_world_corpus(
        synthetic_world["slug"], "run-2",
        categories=("exposure",), tier2_categories=("light",),
        client=client, job_store=store, batch_size=10,
        worlds_dir=synthetic_world["worlds_dir"],
        pkb_root=synthetic_world["pkb_root"])

    assert result["term_count"] == 2                 # exposure + light
    assert len(client.synthesize_calls) == 2          # tier1 pass + tier2 pass
    run_id, dataset = client.train_calls[0]
    tier1 = [r for r in dataset if r["source"] == "tier1"]
    tier2 = [r for r in dataset if r["source"] == "tier2"]
    assert len(tier1) == 1 and len(tier2) == 1


# ── all_categories / category_breakdown ────────────────────────────────

def test_all_categories_returns_spec_order(synthetic_world):
    cats = wc.all_categories(
        synthetic_world["slug"], worlds_dir=synthetic_world["worlds_dir"])
    assert cats == ["exposure", "light", "web-platform", "empty-cat"]


def test_category_breakdown_counts_and_labels(synthetic_world):
    breakdown = wc.category_breakdown(
        synthetic_world["slug"],
        worlds_dir=synthetic_world["worlds_dir"],
        pkb_root=synthetic_world["pkb_root"])
    by_id = {row["id"]: row for row in breakdown}

    assert by_id["exposure"]["label"] == "Exposure"
    assert by_id["exposure"]["term_count"] == 2      # wide-aperture + not-approved-yet
    assert by_id["exposure"]["approved_count"] == 1  # only wide-aperture approved

    assert by_id["light"]["term_count"] == 1
    assert by_id["light"]["approved_count"] == 1

    assert by_id["web-platform"]["term_count"] == 1
    assert by_id["web-platform"]["approved_count"] == 1

    # zero-approved-count / disabled-row case: declared in spec.json but no
    # terms.json entries and nothing approved.
    assert by_id["empty-cat"]["label"] == "Empty Category"
    assert by_id["empty-cat"]["term_count"] == 0
    assert by_id["empty-cat"]["approved_count"] == 0

    assert [row["id"] for row in breakdown] == \
        ["exposure", "light", "web-platform", "empty-cat"]


def test_category_breakdown_missing_world_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        wc.category_breakdown("nonexistent", worlds_dir=tmp_path / "worlds")


def test_build_world_corpus_raises_when_nothing_approved(tmp_path):
    worlds_dir = tmp_path / "worlds"
    (worlds_dir / "empty").mkdir(parents=True)
    (worlds_dir / "empty" / "terms.json").write_text(json.dumps({"terms": []}))
    (worlds_dir / "empty" / "spec.json").write_text(json.dumps({"categories": []}))
    with pytest.raises(ValueError, match="no approved terms"):
        wc.build_world_corpus(
            "empty", "run-3", categories=("exposure",),
            client=_FakeClient(), job_store=_FakeJobStore(),
            student_model="m", worlds_dir=worlds_dir,
            pkb_root=tmp_path / "pkb")
