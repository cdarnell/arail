"""QA round-3 independent adversarial probes — World of Debt Finance."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from arail.agents.debt_finance_compliance import (
    Provenance, Segment, check_guardrail, is_verification_fresh,
    _INSTITUTIONAL_CHARACTER_RE,
)


# ---------- R3-1: staleness clock, future dates ----------
def test_future_dated_verification_is_treated_as_fresh():
    """Negative timedelta: (today - 2999-01-01).days is very negative,
    and the check is `<= 365`, so a far-future date passes."""
    assert is_verification_fresh("2999-01-01", today=dt.date(2026, 7, 27)) is True


def test_verification_exactly_at_boundary():
    today = dt.date(2026, 7, 27)
    assert is_verification_fresh("2025-07-27", today=today) is True   # 365
    assert is_verification_fresh("2025-07-26", today=today) is False  # 366


# ---------- R3-2/3: degenerate is_name vouchers ----------
@pytest.mark.parametrize("name", ["", "   ", "\n", "-", "0"])
def test_degenerate_name_segment_still_vouches(name):
    segs = [
        Segment.agent("This is a credit union offering "),
        Segment.operator(name, is_name=True),
        Segment.agent(" rates."),
    ]
    r = check_guardrail(segs)
    # Documenting actual behaviour.
    print(f"name={name!r} -> ok={r.ok}")
    assert r.ok is True


# ---------- R3-4: trigger split across a segment boundary ----------
def test_trigger_split_across_two_agent_segments_is_not_detected():
    segs = [Segment.agent("Acme is a credit"), Segment.agent(" union, member-owne"),
            Segment.agent("d and great.")]
    body = "".join(s.text for s in segs)
    assert "credit union" in body
    r = check_guardrail(segs)
    print("split-trigger ok=", r.ok)
    assert r.ok is True  # per-segment finditer misses it


# ---------- R3-5: reachability sweep over the REAL templates ----------
def _capture(monkeypatch, adversarial=False):
    from arail.agents import _builtin_consolidation_analyzer as _ca
    from arail.agents import _builtin_debt_advisor as _da
    from arail.agents.debt_finance_compliance import check_guardrail as real

    captured = []

    def rec(segments):
        captured.append(list(segments))
        return real(segments)

    monkeypatch.setattr(_da, "check_guardrail", rec)
    monkeypatch.setattr(_ca, "check_guardrail", rec)
    monkeypatch.setattr(_da._host, "llm_complete", lambda *a, **k: "")
    monkeypatch.setattr(_ca._host, "llm_complete", lambda *a, **k: "")

    if adversarial:
        da_terms = [{
            "term": "credit union nonprofit member-owned",
            "category": "institutions",
            "institution_type": "credit-union",
            "verification_source": "https://nonprofit.example/credit union member-owned",
            "verified_as_of": "2026-07-01",
        }]
        da_findings = [{"feed": "Best credit union nonprofit feed",
                        "checked": "member-owned", "path": "credit union/x.md"}]
        ca_scenarios = [{
            "institution": "credit union nonprofit",
            "product": "member-owned nonprofit loan",
            "rate": 12.0, "fee_pct": 1.0,
            "source": "https://x/credit union", "as_of": "nonprofit",
        }]
    else:
        da_terms = [{
            "term": "PenFed Credit Union", "category": "institutions",
            "institution_type": "credit-union",
            "verification_source": "https://mapping.ncua.gov/x",
            "verified_as_of": "2026-07-01",
        }]
        da_findings = [{"feed": "Some Feed", "checked": "2026-07-01", "path": "x.md"}]
        ca_scenarios = [{
            "institution": "Acme Consolidation", "product": "Personal Loan",
            "rate": 12.0, "fee_pct": 1.0, "source": "https://x",
            "as_of": "2026-01-01",
        }]

    _da._build_output(Path("/unused"), da_terms, da_findings)
    _ca._build_output([{"balance": 1000, "apr": 20}], ca_scenarios)
    return captured


@pytest.mark.parametrize("adv", [False, True])
def test_residual_shape_2_unreachable_agent_trigger_next_to_name(monkeypatch, adv):
    """Residual shape 2 (ARCHITECTURE §13.10): a real vetted name vouching,
    via adjacency, for an institutional-character claim sitting in an AGENT
    segment about some *other* name. Requires an AGENT segment that both
    contains a trigger AND neighbours an is_name voucher."""
    for segments in _capture(monkeypatch, adv):
        for idx, seg in enumerate(segments):
            if seg.provenance is not Provenance.AGENT:
                continue
            if not _INSTITUTIONAL_CHARACTER_RE.search(seg.text):
                continue
            nb = []
            if idx > 0:
                nb.append(segments[idx - 1])
            if idx + 1 < len(segments):
                nb.append(segments[idx + 1])
            assert not any(
                n.provenance is not Provenance.AGENT and n.is_name for n in nb
            ), f"REACHABLE residual shape 2: {seg.text!r}"


@pytest.mark.parametrize("adv", [False, True])
def test_no_trigger_ever_spans_a_segment_boundary_in_real_templates(monkeypatch, adv):
    """Guards the documented precondition for the per-segment finditer:
    'this codebase never splits a literal trigger phrase across a segment
    boundary'. Compares full-concatenation trigger count to per-segment."""
    for segments in _capture(monkeypatch, adv):
        body = "".join(s.text for s in segments)
        whole = len(_INSTITUTIONAL_CHARACTER_RE.findall(body))
        per_seg = sum(len(_INSTITUTIONAL_CHARACTER_RE.findall(s.text))
                      for s in segments)
        assert whole == per_seg, (
            f"trigger spans a segment boundary: whole={whole} "
            f"per_seg={per_seg}")


def test_no_agent_segment_is_operator_or_world_derived(monkeypatch):
    """Every AGENT segment in the real templates must be a static literal or
    code-computed number — never carry operator/World text. Checks the
    adversarial marker strings never appear in AGENT segments."""
    markers = ["credit union nonprofit", "member-owned nonprofit loan",
               "nonprofit.example"]
    for segments in _capture(monkeypatch, adversarial=True):
        for seg in segments:
            if seg.provenance is not Provenance.AGENT:
                continue
            for m in markers:
                assert m not in seg.text, (
                    f"untrusted text leaked into an AGENT segment: {seg.text!r}")


# ---------- R3-9: evaluative fusion / splitting ----------
def test_evaluative_phrase_split_across_agent_segments_is_not_detected():
    segs = [Segment.agent("you "), Segment.agent("should refinance")]
    body = "".join(s.text for s in segs)
    assert "you should" in body
    print("evaluative split (agent/agent) ok=", check_guardrail(segs).ok)
    # And the case that actually matters: an AGENT/WORLD/AGENT interleave,
    # where the WORLD segment is dropped from the evaluative concatenation.
    segs2 = [Segment.agent("you "), Segment.world("PenFed"),
             Segment.agent("should refinance")]
    body2 = "".join(s.text for s in segs2)
    print("body2=", repr(body2), "ok=", check_guardrail(segs2).ok)


def test_evaluative_join_does_not_manufacture_a_false_positive():
    segs = [Segment.agent("rate is 5%"), Segment.agent("best")]
    assert check_guardrail(segs).ok is False  # 'best' really is there


# ---------- R3-10: unicode / homoglyph names ----------
def test_unicode_homoglyph_name_still_only_vouches_by_tag():
    """A homoglyph name can't fake vetting: provenance is a tag, not text."""
    segs = [
        Segment.agent("PenFed Credit Union is a credit union."),
        Segment.world("PenFed Credit Union", is_name=True),
    ]
    # The AGENT segment carries the trigger; neighbour IS a name voucher.
    assert check_guardrail(segs).ok is True
    segs2 = [Segment.agent("Fake Bank is a credit union."),
             Segment.agent("PenFed Credit Union")]
    assert check_guardrail(segs2).ok is False
