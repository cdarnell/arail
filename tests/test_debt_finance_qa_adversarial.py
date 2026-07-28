"""QA adversarial pass — World of Debt Finance.

Written by the QA persona after the architect's round-6 WEAK_PASS. These
tests deliberately probe territory *adjacent* to the six BLOCK findings
already closed in REVIEW.md, on the theory (borne out by that review
history) that this feature's bug class is "a guardrail that is correct for
the inputs someone thought to try."

Grouping mirrors this product's QA weighting (arail: 30% setup / 30%
agent-quality / 20% security / 10% happy / 10% regression), with security
and agent-quality weighted highest for this feature.

Failing tests in this file are findings, not scaffolding — see
sprints/2026-07-26-world-of-debt-finance/TEST_REPORT.md.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from arail.agents.debt_finance_compliance import check_guardrail

_GOOD_DISCLAIMER = (
    "# Disclaimer\n\nThese agents are not licensed financial advisors.\n"
)

_TERMS = {
    "version": 1,
    "terms": [
        {"slug": "credit-union", "term": "Credit Union",
         "category": "institutions", "short": "x", "definition": "x",
         "related": [], "source": "https://www.ncua.gov/x"},
        {"slug": "penfed-credit-union", "term": "PenFed Credit Union",
         "category": "institutions", "institution_type": "credit-union",
         "short": "x", "definition": "x", "related": [],
         "source": "https://www.penfed.org/personal-loans",
         "verification_source": "https://mapping.ncua.gov/ResearchCreditUnion",
         "verified_as_of": "2026-07-27"},
    ],
}


class FakeHost:
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
        return ""


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


@pytest.fixture()
def analyzer(monkeypatch, host, world_bundle):
    from arail.agents import _builtin_consolidation_analyzer as mod
    monkeypatch.setattr(mod, "_host", host)
    monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: world_bundle)
    return mod


@pytest.fixture()
def advisor(monkeypatch, host, world_bundle):
    from arail.agents import _builtin_debt_advisor as mod
    monkeypatch.setattr(mod, "_host", host)
    monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: world_bundle)
    return mod


def _stage(data_dir: Path, raw: str) -> Path:
    d = data_dir / "user-import" / "debt-finance"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "balances.json"
    p.write_text(raw, encoding="utf-8")
    return p


# ══════════════════════════════════════════════════════════════════════
#  EDGE CASES — malformed balances.json field *values*
#  ARCHITECTURE.md §6.1: "the tick does not crash ... emits one
#  non-specific activity-stream note ... and skips the tick."
#  _load_balances validates container shapes only, never field types.
# ══════════════════════════════════════════════════════════════════════

_BAD_VALUE_PAYLOADS = {
    "thousands_separator": '{"debts":[{"institution":"X","balance":"1,200.00","apr":19.99}]}',
    "percent_suffix_apr": '{"debts":[{"institution":"X","balance":1200,"apr":"19.99%"}]}',
    "null_balance": '{"debts":[{"institution":"X","balance":null,"apr":19.99}]}',
    "json_nan": ('{"debts":[{"institution":"X","balance":NaN,"apr":19.99}],'
                 '"candidate_scenarios":[{"institution":"Y","rate":5,"fee_pct":3}]}'),
    "json_infinity": ('{"debts":[{"institution":"X","balance":Infinity,"apr":19.99}],'
                      '"candidate_scenarios":[{"institution":"Y","rate":5,"fee_pct":3}]}'),
    "float_overflow": ('{"debts":[{"institution":"X","balance":1e308,"apr":1e308}],'
                       '"candidate_scenarios":[{"institution":"Y","rate":1e308,"fee_pct":1e308}]}'),
}


@pytest.mark.parametrize("name", sorted(_BAD_VALUE_PAYLOADS))
def test_bad_field_value_warns_and_does_not_crash_the_tick(
    analyzer, data_dir, host, name
):
    """A non-numeric / non-finite value in a numeric field must be handled
    like any other malformed input (§6.1), not raise out of tick()."""
    _stage(data_dir, _BAD_VALUE_PAYLOADS[name])
    agent = analyzer.ConsolidationAnalyzerAgent()
    agent.tick()  # must not raise
    warns = [e for e in host.events if e["level"] == "warn"]
    assert warns, f"{name}: no warning emitted for malformed input"
    findings = (data_dir / "user-import" / "debt-finance" / "findings"
                / "consolidation_analyzer.md")
    assert not findings.exists(), f"{name}: partial output written"


@pytest.mark.parametrize("name", sorted(_BAD_VALUE_PAYLOADS))
def test_bad_field_value_never_echoes_content_into_the_activity_stream(
    analyzer, data_dir, host, name
):
    """§6.1: 'no file content or parsed fragment echoed'."""
    _stage(data_dir, _BAD_VALUE_PAYLOADS[name])
    agent = analyzer.ConsolidationAnalyzerAgent()
    try:
        agent.tick()
    except Exception:
        pytest.fail(f"{name}: tick raised instead of warning")
    for e in host.events:
        assert "1,200.00" not in e["message"]
        assert "19.99" not in e["message"]


def test_a_single_malformed_value_does_not_kill_the_agent_loop(
    analyzer, data_dir, host, monkeypatch
):
    """An exception escaping tick() escapes _run()'s while-loop entirely
    (the try only catches CancelledError), permanently stopping the agent
    while .status still reports 'running' and nothing is emitted."""
    _stage(data_dir, _BAD_VALUE_PAYLOADS["null_balance"])
    monkeypatch.setenv("LAB_CONSOLIDATION_ANALYZER_INTERVAL_SEC", "60")

    real_sleep = asyncio.sleep

    async def _immediate(_delay):
        await real_sleep(0)

    monkeypatch.setattr(analyzer.asyncio, "sleep", _immediate)

    async def _drive():
        agent = analyzer.ConsolidationAnalyzerAgent()
        agent.start()
        await real_sleep(0.05)
        return agent

    agent = asyncio.run(_drive())
    assert agent._task is not None
    if agent._task.done() and agent._task.exception() is not None:
        pytest.fail(
            "agent loop died on a malformed balances.json value: "
            f"{agent._task.exception()!r} (status still reports "
            f"{agent.status!r})"
        )


def test_negative_balances_and_aprs_do_not_produce_a_nonsense_finding(
    analyzer, data_dir
):
    """Negative money is not a documented input. Either reject it as
    malformed or clamp — silently emitting a negative-APR comparison as if
    it were a real finding is the worst of the three."""
    _stage(data_dir, json.dumps({
        "debts": [{"institution": "X", "balance": -500, "apr": -19.99}],
        "candidate_scenarios": [
            {"institution": "Y", "rate": -5, "fee_pct": -3,
             "product": "loan", "source": "operator", "as_of": "2026-07-27"}],
    }))
    agent = analyzer.ConsolidationAnalyzerAgent()
    agent.tick()
    findings = (data_dir / "user-import" / "debt-finance" / "findings"
                / "consolidation_analyzer.md")
    if findings.exists():
        text = findings.read_text()
        assert "rate -5.00%" not in text, (
            "negative APR rendered verbatim into a findings document"
        )


# ══════════════════════════════════════════════════════════════════════
#  SECURITY / AGENT QUALITY — guardrail escape and over-block probes
#  Adjacent to BLOCK-1..7. _names_match is unanchored substring
#  containment with NO minimum length and NO word boundary — the exact
#  defect class _MIN_QUOTED_SPAN_LEN was added to close on the *other*
#  branch of the same function.
# ══════════════════════════════════════════════════════════════════════

_SMUGGLE = (
    "- **A** (as you entered it) — PenFed Credit Union member loan "
    "(as entered), rate 5.00%."
)


def test_short_operator_name_does_not_universally_satisfy_the_institutional_branch():
    """A one-character operator-typed institution name is a substring of
    almost every candidate proper noun, so it satisfies the pairing rule
    for institutional-character claims about *other*, unvetted entities
    named elsewhere on the line (here: via the `product` field)."""
    blocked_without = check_guardrail(
        _SMUGGLE, frozenset(), operator_names=frozenset({"mybank"}))
    assert not blocked_without.ok, "control case should block"

    smuggled = check_guardrail(
        _SMUGGLE, frozenset(), operator_names=frozenset({"a"}))
    assert not smuggled.ok, (
        "a 1-char operator institution name defeated the institutional-"
        "character guardrail for an unrelated, unvetted institution"
    )


def test_whitespace_only_operator_name_does_not_satisfy_the_pairing_rule():
    """`institution: " "` is truthy, survives the `if d.get("institution")`
    filter, lowercases to " ", and is a substring of every multi-word
    proper noun."""
    result = check_guardrail(
        _SMUGGLE, frozenset(), operator_names=frozenset({" "}))
    assert not result.ok


def test_allowed_names_match_on_word_boundaries_not_bare_substrings():
    """"Ally" (a real 4-char lender) must not vet "Alliance Credit Union"."""
    text = "- **Alliance Credit Union** — consolidation loan."
    result = check_guardrail(text, frozenset(), operator_names=frozenset({"ally"}))
    assert not result.ok


def test_operator_typed_lowercase_institution_is_not_falsely_blocked(
    analyzer, data_dir, host
):
    """_PROPER_NOUN_RE requires a capitalized initial, but the trigger
    regex is case-insensitive — so an operator who types their own
    institution in lowercase (an extremely ordinary thing to do) gets a
    permanent block, with a hint telling them to pair the claim with a
    name they typed themselves, which they did."""
    _stage(data_dir, json.dumps({
        "debts": [{"institution": "navy federal credit union",
                   "balance": 8000, "apr": 21.5}],
        "candidate_scenarios": [
            {"institution": "navy federal credit union", "product": "loan",
             "rate": 9.5, "fee_pct": 0.0, "source": "operator",
             "as_of": "2026-07-27"}],
    }))
    agent = analyzer.ConsolidationAnalyzerAgent()
    agent.tick()
    findings = (data_dir / "user-import" / "debt-finance" / "findings"
                / "consolidation_analyzer.md")
    assert findings.exists(), (
        "operator's own lowercase institution name was blocked by the "
        "guardrail: "
        + "; ".join(e["message"] for e in host.events if e["level"] == "warn")
    )


def test_operator_typed_name_with_trailing_whitespace_is_not_falsely_blocked():
    """The exemption is documented as whitespace-normalized; the actual
    normalization is `.lower()` only."""
    text = "- **Ecole Populaire Credit Union** — loan."
    result = check_guardrail(
        text, frozenset(),
        operator_names=frozenset({"ecole populaire credit union "}))
    assert result.ok


def test_non_ascii_initial_institution_name_is_not_falsely_blocked():
    """_PROPER_NOUN_RE's `[A-Z]` is ASCII-only, so a name whose first
    letter is accented never becomes a candidate at all."""
    text = "- **Éole Credit Union** — loan."
    result = check_guardrail(
        text, frozenset(), operator_names=frozenset({"éole credit union"}))
    assert result.ok


@pytest.mark.parametrize("sentence", [
    "We recommend this option.",
    "This is the optimal choice for you.",
    "The cheapest path is consolidation.",
    "The smartest move is to transfer the balance.",
    "You'd be better off consolidating.",
    "This one is a no-brainer.",
    "Our advice is to consolidate.",
])
def test_evaluative_regex_covers_ordinary_advice_vocabulary(sentence):
    """_EVALUATIVE_RE lists 7 alternations. §5.4 says ranking a product for
    a specific person is 'a line this product must not cross regardless',
    and §7.2 makes the code check the structural enforcement of that. These
    are the phrasings a small instruct model actually produces."""
    assert not check_guardrail(sentence, frozenset()).ok, (
        f"evaluative language not detected: {sentence!r}"
    )


# ══════════════════════════════════════════════════════════════════════
#  SECURITY — disclaimer precondition edges
# ══════════════════════════════════════════════════════════════════════

def test_empty_disclaimer_file_refuses_to_write(analyzer, data_dir, world_bundle, host):
    (world_bundle / "compliance" / "DISCLAIMER.md").write_text("")
    _stage(data_dir, json.dumps({"debts": [{"institution": "X", "balance": 1, "apr": 1}]}))
    analyzer.ConsolidationAnalyzerAgent().tick()
    assert not (data_dir / "user-import" / "debt-finance" / "findings"
                / "consolidation_analyzer.md").exists()
    assert any(e["level"] == "warn" for e in host.events)


def test_disclaimer_deleted_between_read_and_write_still_writes_the_text_it_read(
    analyzer, data_dir, world_bundle
):
    """TOCTOU: the read content is what gets appended, so deleting the file
    mid-tick must never produce a findings file with no disclaimer."""
    _stage(data_dir, json.dumps({"debts": [{"institution": "X", "balance": 1, "apr": 1}]}))
    orig = analyzer.read_disclaimer

    def _racing(bundle_dir=None):
        text = orig(bundle_dir)
        (world_bundle / "compliance" / "DISCLAIMER.md").unlink()
        return text

    analyzer.read_disclaimer = _racing
    try:
        analyzer.ConsolidationAnalyzerAgent().tick()
    finally:
        analyzer.read_disclaimer = orig
    path = (data_dir / "user-import" / "debt-finance" / "findings"
            / "consolidation_analyzer.md")
    if path.exists():
        assert "not licensed financial advisors" in path.read_text()


# ══════════════════════════════════════════════════════════════════════
#  SECURITY — data isolation, re-verified end-to-end under current code
# ══════════════════════════════════════════════════════════════════════

_REAL_SHAPED = {
    "debts": [
        {"id": "card-1", "kind": "credit-card", "institution": "Chase",
         "balance": 12345.67, "apr": 24.99},
        {"id": "card-2", "kind": "credit-card", "institution": "Citi",
         "balance": 4321.00, "apr": 19.24},
    ],
    "candidate_scenarios": [
        {"institution": "PenFed Credit Union", "product": "balance-transfer",
         "rate": 4.99, "fee_pct": 3.0, "term_months": 18,
         "source": "https://www.penfed.org/personal-loans",
         "as_of": "2026-07-27"},
    ],
}

_SECRETS = ["12345.67", "4321.00", "24.99", "19.24", "Chase", "Citi"]


def test_no_operator_figure_or_institution_reaches_the_pkb_tree(
    analyzer, advisor, data_dir, pkb_root
):
    _stage(data_dir, json.dumps(_REAL_SHAPED))
    analyzer.ConsolidationAnalyzerAgent().tick()
    advisor.DebtAdvisorAgent().tick()
    leaked = []
    for p in pkb_root.rglob("*"):
        if not p.is_file():
            continue
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        for secret in _SECRETS:
            if secret in text:
                leaked.append((str(p.relative_to(pkb_root)), secret))
    assert not leaked, f"operator data found under lab/pkb/: {leaked}"


def test_state_json_holds_only_hash_timestamp_and_count(
    analyzer, advisor, data_dir, pkb_root
):
    _stage(data_dir, json.dumps(_REAL_SHAPED))
    analyzer.ConsolidationAnalyzerAgent().tick()
    advisor.DebtAdvisorAgent().tick()
    allowed = {
        "consolidation_analyzer": {"input_hash", "last_run_at"},
        "debt_advisor": {"terms_hash", "approved_finding_count", "last_run_at"},
    }
    for agent_id, keys in allowed.items():
        p = pkb_root / "agents" / agent_id / "state.json"
        assert p.exists(), f"{agent_id} wrote no state"
        data = json.loads(p.read_text())
        assert set(data) <= keys, f"{agent_id} state has extra keys: {set(data) - keys}"


def test_activity_pointer_does_not_leak_an_absolute_home_path(
    analyzer, data_dir, host
):
    """§6 says the activity stream carries 'a short, non-identifying
    pointer'. The emitted message interpolates the full absolute findings
    path, which on a real install contains the OS username — and
    activity.jsonl renders in the dashboard."""
    _stage(data_dir, json.dumps(_REAL_SHAPED))
    analyzer.ConsolidationAnalyzerAgent().tick()
    for e in host.events:
        assert str(data_dir) not in e["message"], (
            "the absolute filesystem path of the findings file (which on a "
            "real install is rooted under the operator's home directory and "
            "carries their OS username) is interpolated into a "
            f"dashboard-rendered activity message: {e['message']}"
        )


# ══════════════════════════════════════════════════════════════════════
#  AGENT QUALITY — no-op fingerprint completeness
# ══════════════════════════════════════════════════════════════════════

def test_deleting_the_findings_file_causes_it_to_be_regenerated(
    analyzer, data_dir
):
    """The no-op check keys only on the input hash, not on whether the
    output still exists. An operator who deletes findings (the documented
    v1 deletion story, §6.5) never gets them back."""
    _stage(data_dir, json.dumps(_REAL_SHAPED))
    agent = analyzer.ConsolidationAnalyzerAgent()
    agent.tick()
    path = (data_dir / "user-import" / "debt-finance" / "findings"
            / "consolidation_analyzer.md")
    assert path.exists()
    path.unlink()
    agent.tick()
    assert path.exists(), "findings never regenerated after deletion"


def test_findings_refresh_when_the_mounted_world_changes(
    analyzer, data_dir, world_bundle
):
    """The analyzer's fingerprint covers balances.json only. The vetted
    institution set and the disclaimer both come from the mounted World and
    both affect the output, but neither is in the hash."""
    _stage(data_dir, json.dumps(_REAL_SHAPED))
    agent = analyzer.ConsolidationAnalyzerAgent()
    agent.tick()
    path = (data_dir / "user-import" / "debt-finance" / "findings"
            / "consolidation_analyzer.md")
    before = path.read_text()
    (world_bundle / "compliance" / "DISCLAIMER.md").write_text(
        "# Disclaimer\n\nWe are not licensed financial advisors. UPDATED.\n")
    agent.tick()
    assert path.read_text() != before, (
        "disclaimer edit did not propagate to the findings file"
    )


def test_advisor_refreshes_when_the_approved_finding_set_churns(
    advisor, pkb_root, data_dir, monkeypatch
):
    """The advisor's fingerprint is (terms hash, approved *count*). Swapping
    one approved finding for another keeps the count identical, so the
    cited feed/date metadata goes stale silently."""
    calls = {"n": 0}

    def _findings(_root):
        calls["n"] += 1
        feed = "Feed-A" if calls["n"] <= 1 else "Feed-B"
        return [{"path": "sources/scout/debt-finance-1.md", "feed": feed,
                 "checked": "2026-07-01"}]

    monkeypatch.setattr(advisor, "_approved_findings", _findings)
    monkeypatch.setattr(advisor, "_approved_finding_count", lambda _r: 1)
    agent = advisor.DebtAdvisorAgent()
    agent.tick()
    path = data_dir / "user-import" / "debt-finance" / "findings" / "debt_advisor.md"
    assert "Feed-A" in path.read_text()
    agent.tick()
    assert "Feed-B" in path.read_text(), (
        "approved-finding churn at constant count left stale citations"
    )


# ══════════════════════════════════════════════════════════════════════
#  SECURITY — findings file write hygiene
# ══════════════════════════════════════════════════════════════════════

def test_findings_write_does_not_follow_a_pre_placed_symlink(
    analyzer, data_dir, tmp_path
):
    """write_text() follows symlinks. On the shared-machine setup this
    workspace documents, another local user who can create the findings
    path first gets an arbitrary-file-overwrite primitive running as the
    operator."""
    victim = tmp_path / "victim.txt"
    victim.write_text("original\n")
    findings_dir = data_dir / "user-import" / "debt-finance" / "findings"
    findings_dir.mkdir(parents=True)
    (findings_dir / "consolidation_analyzer.md").symlink_to(victim)
    _stage(data_dir, json.dumps(_REAL_SHAPED))
    analyzer.ConsolidationAnalyzerAgent().tick()
    assert victim.read_text() == "original\n", "symlink followed on write"


def test_findings_content_is_never_world_readable_even_transiently(
    analyzer, data_dir
):
    """chmod 0600 happens *after* write_text. A pre-existing 0644 file keeps
    its mode for the duration of the write."""
    findings_dir = data_dir / "user-import" / "debt-finance" / "findings"
    findings_dir.mkdir(parents=True)
    stale = findings_dir / "consolidation_analyzer.md"
    stale.write_text("x")
    os.chmod(stale, 0o644)
    _stage(data_dir, json.dumps(_REAL_SHAPED))
    analyzer.ConsolidationAnalyzerAgent().tick()
    assert oct(os.stat(stale).st_mode & 0o777) == "0o600"
