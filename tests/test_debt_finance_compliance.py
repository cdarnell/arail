"""Unit tests for arail.agents.debt_finance_compliance.

Per ARCHITECTURE.md §7.1/§7.2 — the single highest-value file for the
security tier: the disclaimer precondition check and the language-safety /
institutional-labeling guardrail both agents share.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arail.agents.debt_finance_compliance import (
    CANONICAL_PHRASE,
    check_guardrail,
    read_disclaimer,
)

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
