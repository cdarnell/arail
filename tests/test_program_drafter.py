"""Tests for the goal → research recipe pipeline.

Covers the auto-drafter, the program loader, and the autoresearch
wiring that lets a `## Knobs` block in program.md override the
hardcoded CANDIDATES list.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ── Drafter ────────────────────────────────────────────────────────────────

def _example_goal_record() -> dict:
    return {
        "goal_text": "Improve AirLLM throughput on my MacBook",
        "parsed": {
            "goal": "Improve AirLLM throughput on my MacBook",
            "domain": "inference",
            "primary_objective": "Increase tokens-per-minute on a 70B model running from disk",
            "sub_objectives": [
                "Tune KV-cache quantization bits",
                "Sweep prefill chunk size",
                "Measure prefetch lookahead impact",
            ],
            "success_metrics": {"tokens_per_minute": "+50% over baseline"},
        },
    }


def test_draft_program_writes_all_sections(tmp_path: Path):
    from arail.research.program_drafter import draft_program

    res = draft_program(
        goal_record=_example_goal_record(),
        kb_hits=[],
        research_dir=tmp_path,
    )
    assert res.wrote is True
    assert res.program_path.exists()
    assert res.train_path.exists()

    body = res.program_path.read_text()
    # Frontmatter
    assert body.startswith("---\n")
    assert "auto_drafted: true" in body
    assert "intent: inference" in body
    # Required sections
    for header in (
        "# Research program",
        "## Goal",
        "## Hypotheses worth testing",
        "## Success criteria",
        "## Knobs",
        "## Sources",
        "## Constraints",
    ):
        assert header in body, f"missing section: {header}"
    # Sub-objectives surface as hypotheses
    assert "Tune KV-cache quantization bits" in body
    assert "Sweep prefill chunk size" in body
    # Success metric surfaces
    assert "tokens_per_minute" in body
    # Curated default sources are pinned
    assert "AirLLM" in body
    assert "GGUF" in body


def test_draft_program_refuses_overwrite_unless_forced(tmp_path: Path):
    from arail.research.program_drafter import draft_program

    res1 = draft_program(goal_record=_example_goal_record(), research_dir=tmp_path)
    assert res1.wrote is True
    res2 = draft_program(goal_record=_example_goal_record(), research_dir=tmp_path)
    assert res2.wrote is False
    assert "exists" in res2.reason

    # Force overwrites and bumps the timestamp.
    res3 = draft_program(goal_record=_example_goal_record(), research_dir=tmp_path, force=True)
    assert res3.wrote is True


def test_draft_program_writes_train_stub_with_apply_revert(tmp_path: Path):
    from arail.research.program_drafter import draft_program

    res = draft_program(goal_record=_example_goal_record(), research_dir=tmp_path)
    train_body = res.train_path.read_text()
    assert "def apply_variant" in train_body
    assert "def revert_variant" in train_body
    assert "no-op" in train_body.lower()


def test_default_sources_yaml_loads_and_has_required_fields():
    """The shipped default_sources.yaml must parse and every entry
    must have the fields the drafter pulls."""
    from arail.research.program_drafter import load_default_sources

    sources = load_default_sources()
    assert len(sources) >= 3, "expected at least a few curated defaults"
    for entry in sources:
        assert "title" in entry and entry["title"]
        assert "url" in entry and entry["url"]
        assert entry["url"].startswith(("http://", "https://"))


def test_draft_program_overwrites_static_seed_template(tmp_path: Path):
    """The lab's startup auto-seeder bakes in a generic AeroLLM
    program.md before the user sets a goal. Once a real goal is set,
    the static template is stale by definition — the drafter MUST
    transparently replace it (without needing force=True). The seeder
    writes ``auto_goal:`` in the frontmatter; this drafter writes
    ``auto_drafted: true`` — that's how we distinguish."""
    from arail.research.program_drafter import draft_program, _is_static_seed_template

    # Mimic what arail.agents.builtin_seed writes at startup.
    seed = (
        "---\n"
        "title: SSD-hosted model inference — lab research program\n"
        "lab_theme: Making SSD-hosted model inference faster\n"
        "auto_goal: Optimize AeroLLM's tokens-per-minute\n"
        "---\n"
        "\n# (generic seed body)\n"
    )
    (tmp_path / "program.md").write_text(seed)
    assert _is_static_seed_template(tmp_path / "program.md") is True

    # Drafter should overwrite even with force=False.
    res = draft_program(
        goal_record=_example_goal_record(),
        research_dir=tmp_path,
        force=False,
    )
    assert res.wrote is True
    body = res.program_path.read_text()
    assert "auto_drafted: true" in body
    assert "AirLLM throughput on my MacBook" in body
    assert _is_static_seed_template(res.program_path) is False

    # But once a real draft is in place, force=False protects it.
    res2 = draft_program(
        goal_record=_example_goal_record(),
        research_dir=tmp_path,
        force=False,
    )
    assert res2.wrote is False
    assert "exists" in res2.reason


def test_drafter_skips_external_fetch_in_airgapped_mode(monkeypatch, tmp_path):
    """fetch_external=True should still be a no-op when LAB_MODE
    isn't hybrid — airgapped is the secure default."""
    from arail.research.program_drafter import draft_program

    monkeypatch.delenv("LAB_MODE", raising=False)
    monkeypatch.delenv("ARAIL_MODE", raising=False)

    res = draft_program(
        goal_record=_example_goal_record(),
        research_dir=tmp_path,
        fetch_external=True,
    )
    assert res.wrote is True
    assert res.fetched_external is False


# ── Loader ─────────────────────────────────────────────────────────────────

def test_program_loader_parses_drafted_output(tmp_path: Path):
    """Full drafter→loader round-trip on the same content."""
    from arail.research.program_drafter import draft_program
    from arail.research.program_loader import parse_program

    res = draft_program(goal_record=_example_goal_record(), research_dir=tmp_path)
    recipe = parse_program(res.program_path)
    assert recipe is not None
    assert recipe.goal == "Improve AirLLM throughput on my MacBook"
    assert recipe.intent == "inference"
    assert recipe.auto_drafted is True
    # Hypotheses pulled out of "## Hypotheses worth testing"
    assert "Tune KV-cache quantization bits" in recipe.hypotheses
    assert "Sweep prefill chunk size" in recipe.hypotheses
    # Success metric pulled out of "## Success criteria"
    assert recipe.success_metrics.get("tokens_per_minute", "").startswith("+50%")


def test_program_loader_parses_user_added_knobs_block(tmp_path: Path):
    """A user-edited program.md with a ## Knobs YAML block becomes
    a list of (label, dict) candidates."""
    from arail.research.program_loader import parse_program

    p = tmp_path / "program.md"
    p.write_text("""---
title: test
goal: testing
intent: inference
---

## Knobs

```yaml
- label: kv-4bit
  knobs:
    kv_bits: 4
- label: prefetch-2
  knobs:
    prefetch_lookahead: 2
```
""")
    recipe = parse_program(p)
    assert recipe is not None
    assert len(recipe.knobs) == 2
    labels = [label for label, _ in recipe.knobs]
    assert "kv-4bit" in labels
    assert "prefetch-2" in labels
    knob_dicts = dict(recipe.knobs)
    assert knob_dicts["kv-4bit"] == {"kv_bits": 4}


def test_program_loader_returns_none_for_missing_file(tmp_path: Path):
    from arail.research.program_loader import parse_program
    assert parse_program(tmp_path / "nope.md") is None


def test_program_loader_tolerates_missing_sections(tmp_path: Path):
    """Half-edited program.md should still parse — missing sections
    degrade to empty fields, never raise."""
    from arail.research.program_loader import parse_program

    p = tmp_path / "program.md"
    p.write_text("# just a heading, nothing structured\n")
    recipe = parse_program(p)
    assert recipe is not None
    assert recipe.knobs == []
    assert recipe.hypotheses == []


# ── Autoresearch wiring ────────────────────────────────────────────────────

def test_autoresearch_picks_up_program_candidates(tmp_path: Path):
    """The smallest test of the bridge: when program.md has knobs,
    _candidates_from_program returns them. The full run_autoresearch
    requires a clean git tree + env flag, so we test the helper."""
    from arail.experiments.autoresearch import _candidates_from_program

    p = tmp_path / "program.md"
    p.write_text("""---
title: test
---

## Knobs

```yaml
- label: my-variant
  knobs:
    foo: bar
```
""")
    cands = _candidates_from_program(p)
    assert len(cands) == 1
    label, knobs = cands[0]
    assert label == "my-variant"
    assert knobs == {"foo": "bar"}


def test_autoresearch_program_fallback_to_empty_when_no_knobs(tmp_path: Path):
    """A program.md without a Knobs block returns no candidates — the
    loop falls back to its hardcoded list."""
    from arail.experiments.autoresearch import _candidates_from_program

    p = tmp_path / "program.md"
    p.write_text("# just a doc\n\n## Goal\n\ntest\n")
    assert _candidates_from_program(p) == []


# ── Reset endpoint ─────────────────────────────────────────────────────────

def test_reset_endpoint_wipes_program_keeps_prepare(monkeypatch, tmp_path):
    """POST /api/research/program/reset removes program.md + train.py
    but never touches prepare.py."""
    from fastapi.testclient import TestClient
    import arail.portal.app as app_mod

    research_dir = tmp_path / "lab" / "pkb" / "research"
    research_dir.mkdir(parents=True)
    (research_dir / "program.md").write_text("# fake program\n")
    (research_dir / "train.py").write_text("# fake train\n")
    (research_dir / "prepare.py").write_text("# the contract — must survive\n")

    monkeypatch.chdir(tmp_path)
    # Patch the drafter's default research dir so the endpoint targets tmp_path.
    monkeypatch.setattr(
        "arail.research.program_drafter._DEFAULT_RESEARCH_DIR",
        research_dir,
    )

    client = TestClient(app_mod.app)
    r = client.post("/api/research/program/reset")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True

    assert not (research_dir / "program.md").exists()
    assert not (research_dir / "train.py").exists()
    assert (research_dir / "prepare.py").exists()  # sticky
    assert (research_dir / "prepare.py").read_text() == "# the contract — must survive\n"
