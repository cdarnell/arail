"""End-to-end tick tests for Debt Advisor and Consolidation Analyzer.

Security tier (20%, highest priority per ARCHITECTURE.md §11): confirms
findings never land under lab/pkb/, state.json never carries a raw figure,
and both agents refuse to write without a valid disclaimer.

Agent-quality tier (30%): output substitution correctness (every number/
institution in a finding matches its structured source, never LLM-retyped),
malformed-input handling, tick no-op detection, guardrail-block behavior.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REAL_BUNDLE = _REPO_ROOT / "examples" / "worlds" / "debt-finance"


_GOOD_DISCLAIMER = (
    "# Disclaimer\n\n"
    "These agents are not licensed financial advisors.\n"
)

_TERMS = {
    "version": 1,
    "terms": [
        {"slug": "credit-union", "term": "Credit Union",
         "category": "institutions", "short": "x", "definition": "x",
         "related": [], "source": "https://www.ncua.gov/consumers/consumer-resources"},
        {"slug": "penfed-credit-union", "term": "PenFed Credit Union",
         "category": "institutions", "institution_type": "credit-union",
         "short": "x", "definition": "x", "related": [],
         "source": "https://www.penfed.org/personal-loans",
         "verification_source": "https://mapping.ncua.gov/ResearchCreditUnion",
         "verified_as_of": "2026-07-27"},
        {"slug": "balance-transfer", "term": "Balance Transfer",
         "category": "strategies", "short": "x", "definition": "x",
         "related": [], "source": "https://example.gov/balance-transfer"},
    ],
}


class FakeHost:
    """Minimal host stub — no LLM, no real activity log, in-memory events."""

    def __init__(self, pkb_root: Path, data_dir: Path):
        self._pkb_root = pkb_root
        self._data_dir = data_dir
        self.events: List[Dict[str, Any]] = []

    def emit(self, source, message, level="info", data=None):
        self.events.append({"source": source, "message": message,
                             "level": level, "data": data})

    def get_pkb_root(self) -> Optional[Path]:
        return self._pkb_root

    def get_data_dir(self) -> Optional[Path]:
        return self._data_dir

    def llm_complete(self, prompt, max_tokens=120, temperature=0.4) -> str:
        return ""  # forces the deterministic fallback framing sentence


@pytest.fixture()
def world_bundle(tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "compliance").mkdir(parents=True)
    (bundle / "compliance" / "DISCLAIMER.md").write_text(_GOOD_DISCLAIMER)
    (bundle / "terms.json").write_text(json.dumps(_TERMS))
    return bundle


@pytest.fixture()
def pkb_root(tmp_path):
    root = tmp_path / "pkb"
    root.mkdir()
    return root


@pytest.fixture()
def data_dir(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    return root


@pytest.fixture()
def host(pkb_root, data_dir):
    return FakeHost(pkb_root, data_dir)


# ── Debt Advisor ──────────────────────────────────────────────────────

@pytest.fixture()
def debt_advisor_module(monkeypatch, host, world_bundle):
    from arail.agents import _builtin_debt_advisor as mod
    monkeypatch.setattr(mod, "_host", host)
    monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: world_bundle)
    return mod


class TestDebtAdvisorHappyPath:
    def test_tick_writes_findings_outside_pkb(self, debt_advisor_module, data_dir, pkb_root):
        agent = debt_advisor_module.DebtAdvisorAgent()
        agent.tick()
        findings = data_dir / "user-import" / "debt-finance" / "findings" / "debt_advisor.md"
        assert findings.exists()
        # Never anywhere under lab/pkb/.
        for p in pkb_root.rglob("*"):
            assert p.name != "debt_advisor.md"

    def test_institution_and_source_are_verbatim_from_terms(self, debt_advisor_module, data_dir):
        agent = debt_advisor_module.DebtAdvisorAgent()
        agent.tick()
        text = (data_dir / "user-import" / "debt-finance" / "findings"
                / "debt_advisor.md").read_text()
        assert "PenFed Credit Union" in text
        # The verification source is the structured field actually printed
        # (a third-party check, distinct from the institution's own site) —
        # not "source", which is only used for citing rate/product pages.
        assert "https://mapping.ncua.gov/ResearchCreditUnion" in text
        # The character label is the term's own institution_type, not a
        # hardcoded "credit union" string (BLOCK-2).
        assert "**PenFed Credit Union** (credit union, verification source:" in text
        # The generic "Credit Union" glossary concept must never be printed
        # here as if it were a named, vetted institution (BLOCK-1's root
        # cause) — it carries no institution_type and is excluded.
        assert "**Credit Union**" not in text

    def test_roster_heading_is_not_a_shortlist(self, debt_advisor_module, data_dir):
        """REVIEW.md addendum, condition (a): the heading must describe the
        verification mechanism, not read as "vetted institutions" (a
        shortlist), and a code-inserted not-exhaustive/not-a-recommendation
        line must sit immediately under it."""
        agent = debt_advisor_module.DebtAdvisorAgent()
        agent.tick()
        text = (data_dir / "user-import" / "debt-finance" / "findings"
                / "debt_advisor.md").read_text()
        assert "## Institutions whose character claims this World verified" in text
        assert "## Vetted institutions" not in text
        assert "not exhaustive" in text
        assert "not a recommendation" in text

    def test_verified_as_of_date_rendered_near_citation(self, debt_advisor_module, data_dir):
        """REVIEW.md addendum, condition (b): the verification date must be
        visible on the document's face, not just internal bookkeeping."""
        agent = debt_advisor_module.DebtAdvisorAgent()
        agent.tick()
        text = (data_dir / "user-import" / "debt-finance" / "findings"
                / "debt_advisor.md").read_text()
        assert (
            "**PenFed Credit Union** (credit union, verification source: "
            "https://mapping.ncua.gov/ResearchCreditUnion, verified as of "
            "2026-07-27)"
        ) in text

    def test_disclaimer_appended(self, debt_advisor_module, data_dir):
        agent = debt_advisor_module.DebtAdvisorAgent()
        agent.tick()
        text = (data_dir / "user-import" / "debt-finance" / "findings"
                / "debt_advisor.md").read_text()
        assert "not licensed financial advisors" in text

    def test_findings_file_is_chmod_0600(self, debt_advisor_module, data_dir):
        agent = debt_advisor_module.DebtAdvisorAgent()
        agent.tick()
        path = data_dir / "user-import" / "debt-finance" / "findings" / "debt_advisor.md"
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600

    def test_activity_pointer_never_contains_institution_or_url(self, debt_advisor_module, host):
        agent = debt_advisor_module.DebtAdvisorAgent()
        agent.tick()
        pointer_events = [e for e in host.events if e["source"] == "debt_advisor"]
        assert pointer_events
        for e in pointer_events:
            assert "PenFed" not in e["message"]
            assert "penfed.org" not in e["message"]


class TestDebtAdvisorNoOp:
    def test_second_tick_with_no_change_is_a_true_noop(self, debt_advisor_module, host):
        agent = debt_advisor_module.DebtAdvisorAgent()
        agent.tick()
        host.events.clear()
        agent.tick()
        assert host.events == []


class TestDebtAdvisorCompliance:
    def test_no_disclaimer_refuses_to_write(self, monkeypatch, host, tmp_path):
        from arail.agents import _builtin_debt_advisor as mod
        bare_bundle = tmp_path / "bare-bundle"
        (bare_bundle / "compliance").mkdir(parents=True)
        (bare_bundle / "terms.json").write_text(json.dumps(_TERMS))
        # no DISCLAIMER.md at all
        monkeypatch.setattr(mod, "_host", host)
        monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: bare_bundle)

        agent = mod.DebtAdvisorAgent()
        agent.tick()

        findings = host._data_dir / "user-import" / "debt-finance" / "findings" / "debt_advisor.md"
        assert not findings.exists()
        assert any("refusing to write" in e["message"] for e in host.events)

    def test_altered_disclaimer_refuses_to_write(self, monkeypatch, host, tmp_path):
        from arail.agents import _builtin_debt_advisor as mod
        bundle = tmp_path / "altered-bundle"
        (bundle / "compliance").mkdir(parents=True)
        (bundle / "compliance" / "DISCLAIMER.md").write_text("Totally fine, trust us.")
        (bundle / "terms.json").write_text(json.dumps(_TERMS))
        monkeypatch.setattr(mod, "_host", host)
        monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: bundle)

        agent = mod.DebtAdvisorAgent()
        agent.tick()

        findings = host._data_dir / "user-import" / "debt-finance" / "findings" / "debt_advisor.md"
        assert not findings.exists()

    def test_no_mounted_world_is_a_silent_noop(self, monkeypatch, host):
        from arail.agents import _builtin_debt_advisor as mod
        monkeypatch.setattr(mod, "_host", host)
        monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: None)
        agent = mod.DebtAdvisorAgent()
        agent.tick()
        assert host.events == []


class TestDebtAdvisorStateFile:
    def test_state_json_has_no_numeric_or_institution_content(self, debt_advisor_module, pkb_root):
        agent = debt_advisor_module.DebtAdvisorAgent()
        agent.tick()
        state = json.loads((pkb_root / "agents" / "debt_advisor" / "state.json").read_text())
        assert set(state.keys()) == {"terms_hash", "approved_finding_count", "last_run_at"}
        blob = json.dumps(state)
        assert "PenFed" not in blob
        assert "penfed.org" not in blob


class TestDebtAdvisorVerifiedAsOfGate:
    """REVIEW.md addendum, condition (b): verified_as_of is REQUIRED for an
    institution to enter the vetted set at all. Missing or stale ⇒
    excluded ⇒ any character claim about it is blocked, not passed."""

    def _terms_with_penfed_verified_as_of(self, value):
        terms = json.loads(json.dumps(_TERMS))
        for t in terms["terms"]:
            if t["slug"] == "penfed-credit-union":
                if value is None:
                    t.pop("verified_as_of", None)
                else:
                    t["verified_as_of"] = value
        return terms

    def test_missing_verified_as_of_excludes_institution_from_vetted_set(
        self, monkeypatch, host, tmp_path
    ):
        from arail.agents import _builtin_debt_advisor as mod
        bundle = tmp_path / "bundle-missing-date"
        (bundle / "compliance").mkdir(parents=True)
        (bundle / "compliance" / "DISCLAIMER.md").write_text(_GOOD_DISCLAIMER)
        (bundle / "terms.json").write_text(
            json.dumps(self._terms_with_penfed_verified_as_of(None))
        )
        monkeypatch.setattr(mod, "_host", host)
        monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: bundle)

        agent = mod.DebtAdvisorAgent()
        agent.tick()

        findings = host._data_dir / "user-import" / "debt-finance" / "findings" / "debt_advisor.md"
        # Excluded from vetted set, but the institution's category term
        # never appears in prose either, so the write should still
        # succeed — it's the *vetted-institution roster* that must now be
        # empty for PenFed, never printed as verified.
        if findings.exists():
            text = findings.read_text()
            assert "PenFed Credit Union" not in text

    def test_stale_verified_as_of_excludes_institution_from_vetted_set(
        self, monkeypatch, host, tmp_path
    ):
        from arail.agents import _builtin_debt_advisor as mod
        bundle = tmp_path / "bundle-stale-date"
        (bundle / "compliance").mkdir(parents=True)
        (bundle / "compliance" / "DISCLAIMER.md").write_text(_GOOD_DISCLAIMER)
        (bundle / "terms.json").write_text(
            json.dumps(self._terms_with_penfed_verified_as_of("2020-01-01"))
        )
        monkeypatch.setattr(mod, "_host", host)
        monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: bundle)

        agent = mod.DebtAdvisorAgent()
        agent.tick()

        findings = host._data_dir / "user-import" / "debt-finance" / "findings" / "debt_advisor.md"
        if findings.exists():
            text = findings.read_text()
            assert "PenFed Credit Union" not in text


class TestDebtAdvisorGuardrail:
    def test_guardrail_block_prevents_write_and_flags(self, monkeypatch, host, world_bundle):
        from arail.agents import _builtin_debt_advisor as mod
        from arail.agents.debt_finance_compliance import GuardrailResult
        monkeypatch.setattr(mod, "_host", host)
        monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: world_bundle)
        monkeypatch.setattr(
            mod, "check_guardrail",
            lambda text, vetted, operator_names=frozenset(): GuardrailResult(
                ok=False, reason="forced block for test"),
        )
        agent = mod.DebtAdvisorAgent()
        agent.tick()
        findings = host._data_dir / "user-import" / "debt-finance" / "findings" / "debt_advisor.md"
        assert not findings.exists()
        assert any("failed the language-safety check" in e["message"] for e in host.events)


# ── Consolidation Analyzer ────────────────────────────────────────────

@pytest.fixture()
def consolidation_module(monkeypatch, host, world_bundle):
    from arail.agents import _builtin_consolidation_analyzer as mod
    monkeypatch.setattr(mod, "_host", host)
    monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: world_bundle)
    return mod


def _write_balances(data_dir: Path, payload: dict) -> None:
    d = data_dir / "user-import" / "debt-finance"
    d.mkdir(parents=True, exist_ok=True)
    (d / "balances.json").write_text(json.dumps(payload))


_BALANCES = {
    "debts": [
        {"id": "card-1", "kind": "credit-card", "balance": 1000.0, "apr": 20.0},
        {"id": "card-2", "kind": "credit-card", "balance": 3000.0, "apr": 10.0},
    ],
    "candidate_scenarios": [
        {"institution": "PenFed Credit Union", "product": "balance-transfer",
         "rate": 5.0, "fee_pct": 3.0, "term_months": 24,
         "source": "https://www.penfed.org/personal-loans", "as_of": "2026-07-01"},
    ],
}


class TestConsolidationAnalyzerInputHandling:
    def test_absent_file_is_a_silent_noop(self, consolidation_module, host):
        agent = consolidation_module.ConsolidationAnalyzerAgent()
        agent.tick()
        assert host.events == []
        findings = host._data_dir / "user-import" / "debt-finance" / "findings" / "consolidation_analyzer.md"
        assert not findings.exists()

    def test_malformed_json_warns_once_no_crash_no_echo(self, consolidation_module, host, data_dir):
        d = data_dir / "user-import" / "debt-finance"
        d.mkdir(parents=True, exist_ok=True)
        (d / "balances.json").write_text("{not valid json, secret-balance-99999")

        agent = consolidation_module.ConsolidationAnalyzerAgent()
        agent.tick()  # must not raise

        assert len(host.events) == 1
        msg = host.events[0]["message"]
        assert "could not read" in msg
        assert "99999" not in msg  # never echoes raw content
        findings = data_dir / "user-import" / "debt-finance" / "findings" / "consolidation_analyzer.md"
        assert not findings.exists()

    def test_valid_input_produces_normal_tick(self, consolidation_module, data_dir):
        _write_balances(data_dir, _BALANCES)
        agent = consolidation_module.ConsolidationAnalyzerAgent()
        agent.tick()
        findings = data_dir / "user-import" / "debt-finance" / "findings" / "consolidation_analyzer.md"
        assert findings.exists()


class TestConsolidationAnalyzerArithmeticSubstitution:
    def test_output_numbers_match_hand_computed_values(self, consolidation_module, data_dir):
        _write_balances(data_dir, _BALANCES)
        agent = consolidation_module.ConsolidationAnalyzerAgent()
        agent.tick()
        text = (data_dir / "user-import" / "debt-finance" / "findings"
                / "consolidation_analyzer.md").read_text()

        # blended APR = (1000*20 + 3000*10) / 4000 = 12.5
        assert "12.50%" in text
        # fee = 4000 * 3% = 120.00
        assert "$120.00" in text
        # institution/rate/source verbatim from the staged scenario
        assert "PenFed Credit Union" in text
        assert "5.00%" in text
        assert "https://www.penfed.org/personal-loans" in text
        assert "2026-07-01" in text

    def test_findings_never_under_pkb(self, consolidation_module, data_dir, pkb_root):
        _write_balances(data_dir, _BALANCES)
        agent = consolidation_module.ConsolidationAnalyzerAgent()
        agent.tick()
        for p in pkb_root.rglob("*"):
            assert p.name != "consolidation_analyzer.md"

    def test_findings_file_chmod_0600(self, consolidation_module, data_dir):
        _write_balances(data_dir, _BALANCES)
        agent = consolidation_module.ConsolidationAnalyzerAgent()
        agent.tick()
        path = data_dir / "user-import" / "debt-finance" / "findings" / "consolidation_analyzer.md"
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


class TestConsolidationAnalyzerOperatorNamesExemption:
    """REVIEW.md addendum, question 2, and re-review addendum 2 [BLOCK-5]:
    a correctly-functioning guardrail must not permanently block the
    operator's own real institution name typed into their own
    balances.json — in EITHER field. The exemption is keyed to provenance
    (did the operator type this name into their own file?), not to
    offer-vs-debt semantics, and is marked "(as you entered it)" in
    output."""

    def test_operator_own_institution_name_passes_and_is_marked(
        self, consolidation_module, data_dir
    ):
        _write_balances(data_dir, {
            "debts": [
                {"id": "card-1", "kind": "credit-card", "balance": 1000.0,
                 "apr": 20.0, "institution": "Anytown Credit Union"},
            ],
            "candidate_scenarios": [
                {"institution": "Anytown Credit Union",
                 "product": "balance-transfer", "rate": 5.0, "fee_pct": 3.0,
                 "term_months": 24, "source": "https://example.invalid/rates",
                 "as_of": "2026-07-01"},
            ],
        })
        agent = consolidation_module.ConsolidationAnalyzerAgent()
        agent.tick()

        findings = (data_dir / "user-import" / "debt-finance" / "findings"
                    / "consolidation_analyzer.md")
        assert findings.exists()
        text = findings.read_text()
        assert "**Anytown Credit Union** (as you entered it) —" in text

    def test_operator_scenario_only_institution_passes_and_is_marked(
        self, consolidation_module, data_dir
    ):
        """[BLOCK-5] exact repro from REVIEW.md re-review addendum 2: the
        operator's existing debt is with a DIFFERENT institution than the
        candidate scenario's institution — the modal real-world input to
        this agent (comparing an existing card against a credit union's
        consolidation offer). Before the BLOCK-5 fix, ``operator_names``
        was built from ``debts`` only, so "Anytown Credit Union" (which
        appears only in the scenario) was never exempted and the guardrail
        raised ``_GuardrailBlocked`` on the *entire* document — this test
        must fail against the pre-fix code."""
        _write_balances(data_dir, {
            "debts": [
                {"id": "card-1", "kind": "credit-card", "balance": 1000.0,
                 "apr": 20.0, "institution": "Chase"},
            ],
            "candidate_scenarios": [
                {"institution": "Anytown Credit Union",
                 "product": "balance-transfer", "rate": 5.0, "fee_pct": 3.0,
                 "term_months": 24, "source": "https://example.invalid/rates",
                 "as_of": "2026-07-01"},
            ],
        })
        agent = consolidation_module.ConsolidationAnalyzerAgent()
        agent.tick()

        findings = (data_dir / "user-import" / "debt-finance" / "findings"
                    / "consolidation_analyzer.md")
        assert findings.exists()
        text = findings.read_text()
        assert "**Anytown Credit Union** (as you entered it) —" in text

    def test_debts_only_institution_still_exempted_no_regression(
        self, consolidation_module, data_dir
    ):
        """[BLOCK-5] regression assertion 2: a debts-only institution must
        still be exempted exactly as before the widening — the fix must be
        additive, not a replacement of the debts-sourced half of the set."""
        debts = [
            {"id": "card-1", "kind": "credit-card", "balance": 1000.0,
             "apr": 20.0, "institution": "Anytown Credit Union"},
        ]
        scenarios: List[Dict[str, Any]] = []
        names = consolidation_module._operator_institution_names(debts, scenarios)
        assert "anytown credit union" in names

    def test_institution_in_neither_field_still_blocks(self, consolidation_module):
        """[BLOCK-5] regression assertion 3: an institution that is
        genuinely NOT operator-stated (absent from both ``debts`` and
        ``candidate_scenarios``) gets no exemption at all and still blocks
        on institutional-character language — confirming the widening did
        not make the guardrail permissive for arbitrary names. Exercised
        directly against ``check_guardrail`` because, by design, the only
        institution names the analyzer ever renders come from ``debts``/
        ``candidate_scenarios`` themselves (see ``_operator_institution_
        names`` docstring) — there is no end-to-end path left by which a
        genuinely third-party institution name reaches this agent's output
        at all, which is itself the point of the fix."""
        from arail.agents.debt_finance_compliance import check_guardrail

        debts = [{"institution": "Chase"}]
        scenarios = [{"institution": "Anytown Credit Union"}]
        operator_names = consolidation_module._operator_institution_names(
            debts, scenarios
        )
        assert operator_names == frozenset({"chase", "anytown credit union"})

        result = check_guardrail(
            "Payday Express is a credit union.",
            frozenset(),
            operator_names=operator_names,
        )
        assert result.ok is False


class TestConsolidationAnalyzerNoOp:
    def test_unchanged_input_is_a_true_noop_on_second_tick(self, consolidation_module, data_dir, host):
        _write_balances(data_dir, _BALANCES)
        agent = consolidation_module.ConsolidationAnalyzerAgent()
        agent.tick()
        host.events.clear()
        agent.tick()
        assert host.events == []


class TestConsolidationAnalyzerStateFile:
    def test_state_json_never_contains_a_balance_or_rate(self, consolidation_module, data_dir, pkb_root):
        _write_balances(data_dir, _BALANCES)
        agent = consolidation_module.ConsolidationAnalyzerAgent()
        agent.tick()
        state = json.loads(
            (pkb_root / "agents" / "consolidation_analyzer" / "state.json").read_text()
        )
        assert set(state.keys()) == {"input_hash", "last_run_at"}
        blob = json.dumps(state)
        for forbidden in ("1000", "3000", "20.0", "10.0", "PenFed"):
            assert forbidden not in blob


# ── Real sealed bundle end-to-end (BLOCK-3 regression) ─────────────────
#
# Everything above this point runs against the synthetic `_TERMS`/`world_
# bundle` fixture, which is what let BLOCK-1 and BLOCK-2 reach "67 passed"
# undetected (REVIEW.md). These tests mount `examples/worlds/debt-finance/`
# itself — the bundle this product actually ships — and must fail against
# the pre-fix code (a hardcoded "(credit union, ...)" label and a tautological
# vetted-institutions set built from mere `category == "institutions"`).

@pytest.mark.skipif(not _REAL_BUNDLE.exists(),
                     reason="sealed debt-finance bundle not forged")
class TestRealSealedBundle:
    def test_debt_advisor_never_mislabels_the_credit_counseling_agency(
        self, monkeypatch, host, data_dir
    ):
        from arail.agents import _builtin_debt_advisor as mod
        monkeypatch.setattr(mod, "_host", host)
        monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: _REAL_BUNDLE)

        agent = mod.DebtAdvisorAgent()
        agent.tick()

        text = (data_dir / "user-import" / "debt-finance" / "findings"
                / "debt_advisor.md").read_text()

        # The two named, verified institutions this World ships are printed
        # with their own institution_type — never a hardcoded "credit
        # union" applied to every institutions-category term (BLOCK-2).
        assert "**PenFed Credit Union** (credit union, verification source:" in text
        assert ("**GreenPath Financial Wellness** "
                "(nonprofit credit counseling agency, verification source:") in text
        # The exact mislabel REVIEW.md quoted must never appear.
        assert "Credit Counseling Agency** (credit union" not in text
        # The generic glossary concepts are never printed as if they were
        # named, vetted institutions (BLOCK-1's root cause).
        assert "**Credit Union**" not in text
        assert "**Credit Counseling Agency**" not in text

    def test_consolidation_analyzer_allows_operator_typed_fictional_institution_as_quotation(
        self, monkeypatch, host, data_dir
    ):
        """[BLOCK-5] Against the REAL sealed bundle: "Payday Express Credit
        Union" is not a World-vetted institution, but the operator typed it
        themselves into their own ``candidate_scenarios`` — so it is a
        quotation, not an agent-verified claim, and must produce a document
        with the "(as you entered it)" marker rather than being blocked.

        Before REVIEW.md's re-review addendum 2 (BLOCK-5), the guardrail
        blocked this exact input — the single most likely real one for this
        agent — because ``operator_names`` was scoped to ``debts`` only and
        never saw ``candidate_scenarios``. This test replaces
        ``test_consolidation_analyzer_blocks_a_fictional_unvetted_institution``,
        whose premise (that an operator-typed scenario institution should be
        blocked like a World-sourced claim) was the defect BLOCK-5 fixed."""
        from arail.agents import _builtin_consolidation_analyzer as mod
        monkeypatch.setattr(mod, "_host", host)
        monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: _REAL_BUNDLE)

        _write_balances(data_dir, {
            "debts": [{"id": "card-1", "kind": "credit-card",
                       "balance": 1000.0, "apr": 20.0}],
            "candidate_scenarios": [
                {"institution": "Payday Express Credit Union",
                 "product": "balance-transfer", "rate": 5.0, "fee_pct": 3.0,
                 "term_months": 24, "source": "https://example.invalid/rates",
                 "as_of": "2026-07-01"},
            ],
        })

        agent = mod.ConsolidationAnalyzerAgent()
        agent.tick()

        findings = (data_dir / "user-import" / "debt-finance" / "findings"
                    / "consolidation_analyzer.md")
        assert findings.exists()
        text = findings.read_text()
        assert "**Payday Express Credit Union** (as you entered it) —" in text

    def test_consolidation_analyzer_allows_its_real_vetted_institution(
        self, monkeypatch, host, data_dir
    ):
        from arail.agents import _builtin_consolidation_analyzer as mod
        monkeypatch.setattr(mod, "_host", host)
        monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: _REAL_BUNDLE)

        _write_balances(data_dir, {
            "debts": [{"id": "card-1", "kind": "credit-card",
                       "balance": 1000.0, "apr": 20.0}],
            "candidate_scenarios": [
                {"institution": "PenFed Credit Union",
                 "product": "balance-transfer", "rate": 5.0, "fee_pct": 3.0,
                 "term_months": 24, "source": "https://www.penfed.org/personal-loans",
                 "as_of": "2026-07-01"},
            ],
        })

        agent = mod.ConsolidationAnalyzerAgent()
        agent.tick()

        findings = (data_dir / "user-import" / "debt-finance" / "findings"
                    / "consolidation_analyzer.md")
        assert findings.exists()
        assert "PenFed Credit Union" in findings.read_text()


class TestConsolidationAnalyzerCompliance:
    def test_no_disclaimer_refuses_to_write(self, monkeypatch, host, tmp_path, data_dir):
        from arail.agents import _builtin_consolidation_analyzer as mod
        bare_bundle = tmp_path / "bare-bundle"
        (bare_bundle / "compliance").mkdir(parents=True)
        (bare_bundle / "terms.json").write_text(json.dumps(_TERMS))
        monkeypatch.setattr(mod, "_host", host)
        monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: bare_bundle)
        _write_balances(data_dir, _BALANCES)

        agent = mod.ConsolidationAnalyzerAgent()
        agent.tick()

        findings = data_dir / "user-import" / "debt-finance" / "findings" / "consolidation_analyzer.md"
        assert not findings.exists()
        assert any("refusing to write" in e["message"] for e in host.events)
