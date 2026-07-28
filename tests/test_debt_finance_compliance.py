"""Unit tests for arail.agents.debt_finance_compliance.

Per ARCHITECTURE.md §7.1/§7.2/§13.11 — the single highest-value file for the
security tier: the disclaimer precondition check and the segment-based
language-safety / institutional-labeling guardrail both agents share.

``check_guardrail`` takes an ordered list of ``Segment(text, provenance)``
pieces, not a flat string plus name-matching sets. Provenance is asserted by
the test itself (mirroring how each agent's ``_build_output`` tags its own
segments) rather than re-derived — that is the entire point of the refactor
(see debt_finance_compliance.py's module docstring and BUILD_LOG.md's
"Structural refactor: segment-based provenance" entry).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arail.agents.debt_finance_compliance import (
    CANONICAL_PHRASE,
    REASON_EVALUATIVE,
    REASON_INSTITUTIONAL_PREFIX,
    Provenance,
    Segment,
    check_guardrail,
    is_verification_fresh,
    read_disclaimer,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEALED_TERMS_PATH = _REPO_ROOT / "examples" / "worlds" / "debt-finance" / "terms.json"


def A(text: str) -> Segment:
    return Segment.agent(text)


def W(text: str) -> Segment:
    return Segment.world(text)


def O(text: str) -> Segment:
    return Segment.operator(text)


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
# Runs only over AGENT-provenance segments.

@pytest.mark.parametrize("phrase", [
    "This is the best option available.",
    "This lender has the guaranteed lowest rate.",
    "You should refinance with this lender.",
    "You must act now.",
    "Our top pick this year.",
])
def test_guardrail_blocks_evaluative_and_imperative_language(phrase):
    result = check_guardrail([A(phrase)])
    assert result.ok is False
    assert "evaluative" in result.reason or "imperative" in result.reason


def test_guardrail_reason_constants_match_actual_reasons():
    """Agents branch a failure-message hint on these exact constants, so
    the constants must actually match what check_guardrail returns."""
    result = check_guardrail([A("Our top pick this year.")])
    assert result.reason == REASON_EVALUATIVE

    result = check_guardrail([A("Acme Lending is a credit union.")])
    assert result.reason.startswith(REASON_INSTITUTIONAL_PREFIX)


# ── check_guardrail — provenance-tagged text is never evaluative-checked
#    (the structural replacement for the old quoted_spans masking
#    mechanism — REVIEW.md re-review addendum 3/4/5, ARCHITECTURE.md §13.11)

def test_world_segment_exempts_a_marketing_style_citation_url():
    """A NerdWallet-style citation URL, tagged WORLD (it is a World-sealed
    verification_source field), must never be evaluative-checked no matter
    what words it contains."""
    result = check_guardrail([
        A("Sourced from "),
        W("https://www.nerdwallet.com/best-balance-transfer-cards"),
        A(" for terms."),
    ])
    assert result.ok is True


def test_agent_segment_with_the_same_text_still_blocks():
    """The provenance TAG decides, not the text — an AGENT segment
    containing the exact same string a WORLD segment could legitimately
    carry must still be evaluative-checked and blocked."""
    result = check_guardrail([
        A("Sourced from https://www.nerdwallet.com/best-balance-transfer-cards for terms."),
    ])
    assert result.ok is False
    assert result.reason == REASON_EVALUATIVE


def test_operator_segment_also_exempt_from_evaluative_check():
    result = check_guardrail([
        A("Source: "),
        O("https://example.invalid/best-rates-ever"),
        A(" (as entered)."),
    ])
    assert result.ok is True


def test_guardrail_does_not_exempt_agent_generated_evaluative_prose():
    """Agent-generated prose asserting "best" must still block even when a
    WORLD segment sits elsewhere in the same document."""
    result = check_guardrail([
        A("This is the best option for you."),
        W("https://www.nerdwallet.com/rates"),
    ])
    assert result.ok is False
    assert result.reason == REASON_EVALUATIVE


def test_guardrail_allows_descriptive_sourced_language():
    result = check_guardrail([
        A("PenFed advertised a personal-loan rate as of "),
        W("2026-07-01"),
        A(", source: "),
        W("https://www.penfed.org/personal-loans"),
        A("."),
    ])
    assert result.ok is True


# ── check_guardrail — institutional-character labeling ────────────────
# Legitimacy is judged by the provenance of the trigger's own segment and
# its immediate neighbours — never by matching text against a name set.

def test_guardrail_blocks_unvetted_institution_credit_union_label():
    result = check_guardrail([
        A("Acme Lending is a credit union offering low rates."),
    ])
    assert result.ok is False
    assert "institutional-character" in result.reason


def test_guardrail_allows_vetted_institution_credit_union_label():
    result = check_guardrail([
        W("PenFed Credit Union"),
        A(" is a credit union, NCUA-insured."),
    ])
    assert result.ok is True


def test_guardrail_blocks_nonprofit_label_for_unvetted_institution():
    result = check_guardrail([
        A("Acme Lending is a nonprofit, member-owned lender."),
    ])
    assert result.ok is False


def test_guardrail_allows_trigger_word_inside_its_own_world_segment():
    """The self-vet case: a vetted term's own institution_type field
    literally IS "credit union" (rendered verbatim from terms.json) — the
    trigger's own segment carries WORLD provenance directly, no neighbour
    needed. This is legitimate because only an already-vetted institution's
    institution_type ever reaches this render path (see
    _builtin_debt_advisor._vetted_institutions's filter) — it is not a
    tautology, it is the actual verified claim."""
    result = check_guardrail([
        A("- **"),
        W("PenFed Credit Union"),
        A("** ("),
        W("credit union"),
        A(", verification source: "),
        W("https://mapping.ncua.gov/ResearchCreditUnion"),
        A(")"),
    ])
    assert result.ok is True


def test_guardrail_blocks_fictional_institution_even_with_real_vetted_credit_unions_present():
    """A separate, unrelated vetted institution rendered elsewhere in the
    document must not let a distinct, unvetted claim ride along on it —
    the two are in different segments with no shared neighbour, so the
    unvetted claim's own AGENT-only neighbourhood still blocks."""
    result = check_guardrail([
        A("- **"), W("PenFed Credit Union"), A("** (credit union, verified.)\n"),
        A("Payday Express is a credit union offering fast approval."),
    ])
    assert result.ok is False
    assert "institutional-character" in result.reason


def test_guardrail_operator_segment_exempts_the_operators_own_unvetted_institution():
    result = check_guardrail([
        O("Anytown Credit Union"),
        A(" is a credit union offering a personal loan."),
    ])
    assert result.ok is True


def test_guardrail_agent_named_institution_never_exempted():
    """An institution name that exists only inside AGENT-provenance text —
    invented or altered by the model — can never be treated as vetted or
    operator-stated. There is no string it could be phrased as that would
    change this, because legitimacy is decided by the segment's provenance
    tag, not by matching its text."""
    result = check_guardrail([
        A("Anytown Credit Union is a credit union offering a personal loan."),
    ])
    assert result.ok is False


def test_guardrail_checks_every_trigger_occurrence_in_one_segment_independently():
    """A single AGENT segment naming both a vetted (preceding WORLD
    segment) and an unvetted institution must still block on the unvetted
    one — the first occurrence's legitimate neighbour must not
    short-circuit the check for a second, unrelated occurrence."""
    result = check_guardrail([
        W("PenFed Credit Union"),
        A(" is a credit union, and "),
        A("Payday Express"),
        A(" is also a credit union."),
    ])
    assert result.ok is False
    assert "institutional-character" in result.reason


def test_guardrail_next_segment_can_also_legitimize():
    """The name need not precede the trigger — a WORLD/OPERATOR segment
    immediately *following* the trigger's segment is an equally legitimate
    neighbour (e.g. "this is a credit union: PenFed Credit Union")."""
    result = check_guardrail([
        A("This is a credit union: "),
        W("PenFed Credit Union"),
        A("."),
    ])
    assert result.ok is True


def test_guardrail_blocks_adjacent_unpunctuated_vetted_line_and_unvetted_line():
    """BLOCK-4's original repro, now expressed structurally: Debt Advisor's
    own vetted-institution line (WORLD name, then AGENT closing text) must
    not let an adjacent bullet's unvetted institutional-character claim
    (all-AGENT segments) ride along on it — segment adjacency, not sentence
    splitting, is what scopes this correctly now."""
    result = check_guardrail([
        A("- **"), W("PenFed Credit Union"),
        A("** (credit union, verification source: https://x)\n- **"),
        A("Payday Express"),
        A("** is a credit union."),
    ])
    assert result.ok is False
    assert "institutional-character" in result.reason


# ── check_guardrail / vetted-set construction — against the real sealed
#    bundle (BLOCK-3 regression), confirming the real terms.json filter
#    never treats a generic concept term as a named institution.

def test_real_sealed_bundle_generic_concept_terms_are_never_vetted():
    vetted = _real_vetted_institution_names()
    assert "credit union" not in vetted
    assert "credit counseling agency" not in vetted


def test_real_sealed_bundle_has_at_least_one_named_vetted_institution():
    vetted = _real_vetted_institution_names()
    assert "penfed credit union" in vetted


def test_real_sealed_bundle_guardrail_blocks_fictional_lender():
    result = check_guardrail([
        A("Payday Express is a credit union offering fast approval."),
    ])
    assert result.ok is False


def test_real_sealed_bundle_guardrail_allows_its_own_vetted_institution():
    result = check_guardrail([
        W("PenFed Credit Union"),
        A(" is a credit union, NCUA-insured."),
    ])
    assert result.ok is True


# ── is_verification_fresh — staleness degrades closed (missing/
#    unparseable/stale ⇒ not fresh ⇒ not vetted).

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


# ── Segment / Provenance — basic contract ──────────────────────────────

def test_segment_factories_tag_the_expected_provenance():
    assert Segment.agent("x").provenance is Provenance.AGENT
    assert Segment.world("x").provenance is Provenance.WORLD
    assert Segment.operator("x").provenance is Provenance.OPERATOR


def test_empty_segment_list_passes():
    assert check_guardrail([]).ok is True
