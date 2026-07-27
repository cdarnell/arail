"""Unit tests for arail.agents.debt_finance_compliance.

Per ARCHITECTURE.md §7.1/§7.2 — the single highest-value file for the
security tier: the disclaimer precondition check and the language-safety /
institutional-labeling guardrail both agents share.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arail.agents.debt_finance_compliance import (
    CANONICAL_PHRASE,
    check_guardrail,
    read_disclaimer,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEALED_TERMS_PATH = _REPO_ROOT / "examples" / "worlds" / "debt-finance" / "terms.json"


def _real_sealed_terms() -> list[dict]:
    doc = json.loads(_SEALED_TERMS_PATH.read_text(encoding="utf-8"))
    return list(doc.get("terms") or [])


def _real_vetted_institution_names() -> frozenset[str]:
    """Mirrors the production filter in _builtin_debt_advisor /
    _builtin_consolidation_analyzer: category == "institutions" AND an
    institution_type AND a verification_source — never the bare presence of
    "institutions" category (that also holds generic glossary concepts)."""
    names = set()
    for t in _real_sealed_terms():
        if (t.get("category") == "institutions" and t.get("institution_type")
                and t.get("verification_source")):
            names.add(str(t.get("term") or t.get("slug") or "").lower())
    return frozenset(names)

_GOOD_DISCLAIMER = (
    "# Disclaimer\n\n"
    "The Debt Advisor and Consolidation Analyzer agents are "
    "not licensed financial advisors and provide educational "
    "information only.\n"
)


def _bundle_with_disclaimer(tmp_path: Path, text: str | None) -> Path:
    bundle = tmp_path / "bundle"
    (bundle / "compliance").mkdir(parents=True)
    if text is not None:
        (bundle / "compliance" / "DISCLAIMER.md").write_text(text)
    return bundle


# ── read_disclaimer ──────────────────────────────────────────────────

def test_read_disclaimer_returns_text_when_phrase_present(tmp_path):
    bundle = _bundle_with_disclaimer(tmp_path, _GOOD_DISCLAIMER)
    result = read_disclaimer(bundle)
    assert result is not None
    assert CANONICAL_PHRASE in result


def test_read_disclaimer_none_when_file_missing(tmp_path):
    bundle = _bundle_with_disclaimer(tmp_path, None)
    assert read_disclaimer(bundle) is None


def test_read_disclaimer_none_when_phrase_altered(tmp_path):
    altered = _GOOD_DISCLAIMER.replace(CANONICAL_PHRASE, "totally legit advisors")
    bundle = _bundle_with_disclaimer(tmp_path, altered)
    assert read_disclaimer(bundle) is None


def test_read_disclaimer_none_when_no_bundle():
    assert read_disclaimer(None) is None


def test_read_disclaimer_reads_fresh_not_cached(tmp_path):
    bundle = _bundle_with_disclaimer(tmp_path, _GOOD_DISCLAIMER)
    assert read_disclaimer(bundle) is not None
    (bundle / "compliance" / "DISCLAIMER.md").unlink()
    assert read_disclaimer(bundle) is None


# ── check_guardrail — evaluative/imperative language ─────────────────

@pytest.mark.parametrize("phrase", [
    "This is the best option available.",
    "This lender has the guaranteed lowest rate.",
    "You should refinance with this lender.",
    "You must act now.",
    "Our top pick this year.",
])
def test_guardrail_blocks_evaluative_and_imperative_language(phrase):
    result = check_guardrail(phrase, frozenset())
    assert result.ok is False
    assert "evaluative" in result.reason or "imperative" in result.reason


def test_guardrail_allows_descriptive_sourced_language():
    text = (
        "PenFed advertised a personal-loan rate as of 2026-07-01, "
        "source: https://www.penfed.org/personal-loans."
    )
    result = check_guardrail(text, frozenset())
    assert result.ok is True


# ── check_guardrail — institutional-character labeling ────────────────

def test_guardrail_blocks_unvetted_institution_credit_union_label():
    text = "Acme Lending is a credit union offering low rates."
    result = check_guardrail(text, frozenset())
    assert result.ok is False
    assert "institutional-character" in result.reason


def test_guardrail_allows_vetted_institution_credit_union_label():
    text = "PenFed Credit Union is a credit union, NCUA-insured."
    result = check_guardrail(text, frozenset({"penfed credit union"}))
    assert result.ok is True


def test_guardrail_blocks_nonprofit_label_for_unvetted_institution():
    text = "Acme Lending is a nonprofit, member-owned lender."
    result = check_guardrail(text, frozenset({"penfed credit union"}))
    assert result.ok is False


# ── check_guardrail — regression: the terms.json category tautology ────
# (BLOCK-1) a vetted set built from mere "institutions"-category presence
# contains the generic concept term "Credit Union" — whose own name IS the
# trigger phrase — making the check pass for any institution, vetted or
# not. This must never happen again, from any vetted set the real code
# could plausibly build.

def test_guardrail_is_not_a_tautology_when_generic_concept_term_is_vetted():
    """If a vetted set naively includes the bare word "credit union" (the
    bug's exact shape), an unvetted, fictional lender must still be
    blocked — the presence of the trigger phrase itself must never satisfy
    its own check."""
    text = "Payday Express is a credit union offering fast approval."
    result = check_guardrail(text, frozenset({"credit union"}))
    assert result.ok is False
    assert "institutional-character" in result.reason


def test_guardrail_blocks_fictional_institution_even_with_real_vetted_credit_unions_present():
    """The adversarial case BLOCK-1 should have caught originally: an
    unvetted/fictional institution paired with institutional-character
    language must be blocked even while real vetted credit unions exist
    elsewhere in the vetted set."""
    text = "Payday Express is a credit union offering fast approval."
    vetted = frozenset({"penfed credit union", "greenpath financial wellness"})
    result = check_guardrail(text, vetted)
    assert result.ok is False
    assert "institutional-character" in result.reason


def test_guardrail_passes_a_vetted_institution_whose_own_name_contains_the_trigger_words():
    """The failure-mode swing the reviewer flagged: naively tightening the
    check must not turn into a permanent block for the single most likely
    real case — a vetted institution whose own name contains "Credit
    Union". A correctly vetted claim about it must still pass."""
    text = "PenFed Credit Union is a credit union, NCUA-insured."
    result = check_guardrail(text, frozenset({"penfed credit union"}))
    assert result.ok is True


def test_guardrail_blocks_unvetted_name_even_when_a_similarly_named_institution_is_vetted():
    """A near-miss name (not an exact/substring match of the vetted name)
    must not ride along on a vetted institution's credibility."""
    text = "PenFed Lending Group is a credit union offering fast approval."
    result = check_guardrail(text, frozenset({"penfed credit union"}))
    assert result.ok is False


# ── check_guardrail / vetted-set construction — against the real sealed
#    bundle, not a synthetic fixture (BLOCK-3: the synthetic fixture used
#    in tests/test_debt_finance_agents.py masked both BLOCK-1 and BLOCK-2).

def test_real_sealed_bundle_generic_concept_terms_are_never_vetted():
    vetted = _real_vetted_institution_names()
    assert "credit union" not in vetted
    assert "credit counseling agency" not in vetted


def test_real_sealed_bundle_has_at_least_one_named_vetted_institution():
    vetted = _real_vetted_institution_names()
    assert "penfed credit union" in vetted


def test_real_sealed_bundle_guardrail_blocks_fictional_lender():
    vetted = _real_vetted_institution_names()
    text = "Payday Express is a credit union offering fast approval."
    result = check_guardrail(text, vetted)
    assert result.ok is False


def test_real_sealed_bundle_guardrail_allows_its_own_vetted_institution():
    vetted = _real_vetted_institution_names()
    text = "PenFed Credit Union is a credit union, NCUA-insured."
    result = check_guardrail(text, vetted)
    assert result.ok is True
