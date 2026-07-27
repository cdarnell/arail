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
    REASON_EVALUATIVE,
    REASON_INSTITUTIONAL_PREFIX,
    check_guardrail,
    is_verification_fresh,
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


def test_guardrail_reason_constants_match_actual_reasons():
    """REVIEW.md re-review addendum 3, item 3: agents branch a
    failure-message hint on these exact constants, so the constants must
    actually match what check_guardrail returns."""
    result = check_guardrail("Our top pick this year.", frozenset())
    assert result.reason == REASON_EVALUATIVE

    result = check_guardrail("Acme Lending is a credit union.", frozenset())
    assert result.reason.startswith(REASON_INSTITUTIONAL_PREFIX)


# ── check_guardrail — quoted_spans (REVIEW.md re-review addendum 3,
#    BLOCK-6): a scoped, per-span exemption for the evaluative-language
#    branch, distinct from (and narrower than) widening the vocabulary.

def test_quoted_spans_exempts_a_marketing_style_citation_url():
    """Exact repro from REVIEW.md's addendum 3: a NerdWallet-style citation
    URL, quoted verbatim, must not suppress the document."""
    text = (
        "Sourced from https://www.nerdwallet.com/best-balance-transfer-cards "
        "for terms."
    )
    result = check_guardrail(
        text, frozenset(),
        quoted_spans=frozenset({
            "https://www.nerdwallet.com/best-balance-transfer-cards"
        }),
    )
    assert result.ok is True


def test_quoted_spans_default_is_empty_no_exemption_by_default():
    """Callers that do not pass quoted_spans get no exemption — the
    default must not accidentally widen the evaluative check."""
    text = "Sourced from https://www.nerdwallet.com/best-balance-transfer-cards."
    result = check_guardrail(text, frozenset())
    assert result.ok is False
    assert result.reason == REASON_EVALUATIVE


def test_quoted_spans_does_not_exempt_agent_generated_evaluative_prose():
    """The exemption is scoped to the exact literal span supplied, not to
    the vocabulary — agent-generated prose asserting "best" independently
    of any quoted span must still block."""
    text = "This is the best option for you."
    result = check_guardrail(
        text, frozenset(),
        quoted_spans=frozenset({"https://www.nerdwallet.com/rates"}),
    )
    assert result.ok is False
    assert result.reason == REASON_EVALUATIVE


def test_quoted_spans_does_not_exempt_the_institutional_character_branch():
    """quoted_spans only narrows the evaluative check; an institutional-
    character claim inside (or outside) a quoted span still needs a vetted/
    operator name near it."""
    text = "Payday Express is a credit union, best-in-class service."
    result = check_guardrail(
        text, frozenset(),
        quoted_spans=frozenset({"best-in-class service"}),
    )
    assert result.ok is False
    assert result.reason.startswith(REASON_INSTITUTIONAL_PREFIX)


def test_short_quoted_span_does_not_globally_mask_unrelated_evaluative_word():
    """REVIEW.md re-review addendum 4, ASK-C: a short operator-typed value
    (e.g. ``as_of='st'``) must not, via a global string replace, blank the
    substring "st" out of an unrelated word like "best" elsewhere in the
    body — that would degrade the evaluative check open for content that
    has nothing to do with the short value. Below the length floor, the
    span is not masked at all, and the genuinely evaluative "best" is still
    caught."""
    text = "Verified as of st. This is the best option for you."
    result = check_guardrail(
        text, frozenset(),
        quoted_spans=frozenset({"st"}),
    )
    assert result.ok is False
    assert result.reason == REASON_EVALUATIVE


def test_short_quoted_span_below_floor_is_itself_still_fully_checked():
    """A short quoted span that itself happens to be evaluative-sounding is
    not masked (it's below the floor), so it is fully evaluative-checked —
    this is the "degrades closed" side of the ASK-C tradeoff, not a
    regression: it is not exempted, but it also is not being used to
    silently gut the check elsewhere."""
    text = "Rate: best"
    result = check_guardrail(
        text, frozenset(),
        quoted_spans=frozenset({"best"}),
    )
    assert result.ok is False
    assert result.reason == REASON_EVALUATIVE


def test_quoted_span_at_or_above_floor_still_masks_correctly():
    """No regression: a realistic-length quoted span (well above the
    floor) is still masked and does not block."""
    text = "Sourced from https://www.nerdwallet.com/best-balance-transfer-cards."
    result = check_guardrail(
        text, frozenset(),
        quoted_spans=frozenset({
            "https://www.nerdwallet.com/best-balance-transfer-cards"
        }),
    )
    assert result.ok is True


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


# ── check_guardrail — regression: BLOCK-4, the sentence boundary is not a
#    boundary. A rendered list item with no terminal punctuation (e.g.
#    "...)") must not merge with the following line into one "sentence"
#    and let an unvetted institution on the following line ride along on a
#    vetted name written on the line above it. Both cases below must fail
#    against the pre-fix code (3d56c9b).

def test_guardrail_blocks_adjacent_unpunctuated_vetted_line_and_unvetted_line():
    """The exact repro from REVIEW.md's addendum: Debt Advisor's own
    vetted-institution line ends in ')' with no terminal punctuation, so it
    must not merge with an adjacent unvetted institutional-character claim
    into a single "sentence" that the vetted name then satisfies."""
    vetted = frozenset({"penfed credit union"})
    text = (
        "- **PenFed Credit Union** (credit union, verification source: "
        "https://x)\n"
        "- **Payday Express** is a credit union."
    )
    result = check_guardrail(text, vetted)
    assert result.ok is False
    assert "institutional-character" in result.reason


def test_guardrail_checks_every_trigger_occurrence_in_one_chunk_independently():
    """A single sentence/line naming both a vetted and an unvetted
    institution, each with their own trigger phrase, must block on the
    unvetted one — the first (vetted) occurrence must not short-circuit the
    check for the second (unvetted) occurrence in the same chunk."""
    vetted = frozenset({"penfed credit union"})
    text = (
        "PenFed Credit Union is a credit union, and Payday Express is also "
        "a credit union."
    )
    result = check_guardrail(text, vetted)
    assert result.ok is False
    assert "institutional-character" in result.reason


# ── check_guardrail — operator_names exemption (REVIEW.md addendum,
#    question 2): a distinct, narrower provenance than vetted_institutions,
#    sourced only from the operator's own data, matched with the identical
#    strict rule, and never applied to World-sourced or model-generated text.

def test_guardrail_operator_names_exempts_the_operators_own_unvetted_institution():
    text = "Anytown Credit Union is a credit union offering a personal loan."
    result = check_guardrail(
        text, frozenset(), operator_names=frozenset({"anytown credit union"})
    )
    assert result.ok is True


def test_guardrail_operator_names_does_not_exempt_a_name_not_in_the_set():
    """The exemption must be keyed to the specific operator name supplied,
    not act as a blanket relaxation of the check."""
    text = "Payday Express is a credit union offering fast approval."
    result = check_guardrail(
        text, frozenset(), operator_names=frozenset({"anytown credit union"})
    )
    assert result.ok is False


def test_guardrail_operator_names_default_is_empty_no_exemption_by_default():
    """Callers that do not pass operator_names get no exemption at all —
    the default must not accidentally widen the vetted set."""
    text = "Anytown Credit Union is a credit union offering a personal loan."
    result = check_guardrail(text, frozenset())
    assert result.ok is False


# ── is_verification_fresh — REVIEW.md addendum, condition (b): staleness
#    degrades closed (missing/unparseable/stale ⇒ not fresh ⇒ not vetted).

def test_is_verification_fresh_true_for_todays_date():
    import datetime
    today = datetime.date(2026, 7, 27)
    assert is_verification_fresh("2026-07-27", today=today) is True


def test_is_verification_fresh_true_within_one_year():
    import datetime
    today = datetime.date(2026, 7, 27)
    assert is_verification_fresh("2025-08-01", today=today) is True


def test_is_verification_fresh_false_older_than_one_year():
    import datetime
    today = datetime.date(2026, 7, 27)
    assert is_verification_fresh("2025-07-01", today=today) is False


def test_is_verification_fresh_false_when_missing():
    assert is_verification_fresh("") is False
    assert is_verification_fresh(None) is False


def test_is_verification_fresh_false_when_unparseable():
    assert is_verification_fresh("not-a-date") is False
    assert is_verification_fresh("07/27/2026") is False
