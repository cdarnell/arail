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


_GOOD_DISCLAIMER = (
    "# Disclaimer\n\n"
    "These agents are not licensed financial advisors.\n"
)

_TERMS = {
    "version": 1,
    "terms": [
        {"slug": "penfed-credit-union", "term": "PenFed Credit Union",
         "category": "institutions", "short": "x", "definition": "x",
         "related": [], "source": "https://www.penfed.org/personal-loans"},
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
        assert "https://www.penfed.org/personal-loans" in text

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


class TestDebtAdvisorGuardrail:
    def test_guardrail_block_prevents_write_and_flags(self, monkeypatch, host, world_bundle):
        from arail.agents import _builtin_debt_advisor as mod
        from arail.agents.debt_finance_compliance import GuardrailResult
        monkeypatch.setattr(mod, "_host", host)
        monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: world_bundle)
        monkeypatch.setattr(
            mod, "check_guardrail",
            lambda text, vetted: GuardrailResult(ok=False, reason="forced block for test"),
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
