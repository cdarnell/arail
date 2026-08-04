"""WP5: the mini-experiment engine measures for real and never fabricates.

Covers archetype selection, each archetype's measured/cannot_run paths, the
unmeasured path, and a regression assertion that the old hardcoded constants
(0.15 / 0.72 / data_points 24) never appear in engine output.
"""

from __future__ import annotations

import asyncio
import sys
import textwrap

import pytest

from arail.research import mini_experiments as mx


# ── fakes ────────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, text, tokens):
        self.text = text
        self.tokens_used = tokens


class _FakeRouter:
    """Deterministic router. Returns compliant 3-bullet output when the prompt
    asks for bullets, otherwise a couple of sentences."""
    def __init__(self):
        self.calls = 0

    def complete(self, prompt, max_tokens=64, temperature=0.7, system=None):
        self.calls += 1
        if max_tokens == 1:
            return _Resp("o", 1)
        if "bullet points" in prompt:
            return _Resp("- one\n- two\n- three", 12)
        return _Resp("Smaller models have fewer parameters. They decode faster.", 20)


def _exp(archetype, hypothesis="test hypothesis"):
    return {"id": "e1", "hypothesis": hypothesis,
            "variables": {"archetype": archetype}, "observations": []}


def _ctx(**kw):
    return mx.ExperimentContext(time_budget_sec=30.0, **kw)


# ── selection ────────────────────────────────────────────────────────

def test_select_archetype():
    assert mx.select_archetype("improve tokens per second throughput") == "model_throughput"
    assert mx.select_archetype("does prompt phrasing change the format") == "prompt_variant"
    assert mx.select_archetype("how well does retrieval from the KB work") == "retrieval_quality"
    assert mx.select_archetype("will it rain tomorrow in Paris") is None


# ── throughput ───────────────────────────────────────────────────────

def test_throughput_measured():
    r = asyncio.run(mx.run_experiment(_exp("model_throughput"),
                                      _ctx(router=_FakeRouter())))
    assert r.provenance == "measured"
    assert r.success is True
    assert r.metrics["decode_tok_per_sec"] is not None
    assert r.metrics["ttft_ms"] is not None
    assert r.runs >= 1


def test_throughput_no_model_cannot_run():
    r = asyncio.run(mx.run_experiment(_exp("model_throughput"), _ctx(router=None)))
    assert r.provenance == "cannot_run"
    assert r.success is False
    assert r.metrics == {}                      # zero numeric metrics — no fabrication
    assert "no local model" in r.cannot_run_reason


# ── prompt variant ───────────────────────────────────────────────────

def test_prompt_variant_measured():
    r = asyncio.run(mx.run_experiment(_exp("prompt_variant"),
                                      _ctx(router=_FakeRouter())))
    assert r.provenance == "measured"
    assert "best_compliance_rate" in r.metrics
    assert "baseline_compliance_rate" in r.metrics


def test_prompt_variant_no_model_cannot_run():
    r = asyncio.run(mx.run_experiment(_exp("prompt_variant"), _ctx(router=None)))
    assert r.provenance == "cannot_run"
    assert r.metrics == {}


# ── retrieval ────────────────────────────────────────────────────────

def test_retrieval_measured():
    titles = ["airllm-streaming", "kv-cache"]

    def kb_search(q, k=5):
        # a title query self-retrieves; keyword queries also hit
        return [{"name": f"{q}.md", "path": f"{q}.md", "score": 0.9}]

    r = asyncio.run(mx.run_experiment(
        _exp("retrieval_quality", "measure retrieval grounding from the corpus"),
        _ctx(kb_search=kb_search, kb_approved_titles=lambda: titles)))
    assert r.provenance == "measured"
    assert r.metrics["approved_docs_count"] == 2
    assert r.metrics["coverage"] > 0


def test_retrieval_empty_kb_cannot_run():
    r = asyncio.run(mx.run_experiment(
        _exp("retrieval_quality"),
        _ctx(kb_search=lambda q, k=5: [], kb_approved_titles=lambda: [])))
    assert r.provenance == "cannot_run"
    assert "approve documents" in r.cannot_run_reason
    assert r.metrics == {}


# ── unmeasured + honesty ─────────────────────────────────────────────

def test_unmeasured_hypothesis():
    exp = _exp("unmeasured", "will it rain tomorrow")
    r = asyncio.run(mx.run_experiment(exp, _ctx(router=_FakeRouter())))
    assert r.provenance == "unmeasured"
    assert r.success is False
    assert r.metrics == {}


def test_success_never_defaults_true_without_measurement():
    # cannot_run and unmeasured are the only outcomes with no numbers, and both
    # are success=False. Nothing produces success=True without real metrics.
    for r in [
        asyncio.run(mx.run_experiment(_exp("model_throughput"), _ctx(router=None))),
        asyncio.run(mx.run_experiment(_exp("unmeasured"), _ctx())),
        asyncio.run(mx.run_experiment(_exp("game_config_optimization"), _ctx())),
    ]:
        assert r.success is False


def test_no_legacy_fabricated_constants():
    """Regression: the old hardcoded metrics must never appear in engine output."""
    payloads = []
    for arche, ctx in [
        ("model_throughput", _ctx(router=_FakeRouter())),
        ("prompt_variant", _ctx(router=_FakeRouter())),
    ]:
        r = asyncio.run(mx.run_experiment(_exp(arche), ctx))
        payloads.append(str(r.to_results_payload(ctx)))
    blob = " ".join(payloads)
    assert "0.15" not in blob
    assert "0.72" not in blob
    assert "data_points" not in blob


# ── game config optimization ─────────────────────────────────────────

def _bench_script(tmp_path, body: str) -> list[str]:
    """Write a tiny real benchmark script and return its argv prefix — the
    archetype always runs a real subprocess, never a mocked call."""
    path = tmp_path / "bench.py"
    path.write_text(textwrap.dedent(body))
    return [sys.executable, str(path)]


def _bench_exp(cmd, tunables, variable=None, hypothesis="tune graphics settings for fps"):
    variables = {"archetype": "game_config_optimization",
                 "benchmark_command": cmd, "game_tunables": tunables}
    if variable is not None:
        variables["variable"] = variable
    return {"id": "e1", "hypothesis": hypothesis, "variables": variables,
            "observations": []}


_BENCH_IMPROVES = """
    import sys, json
    value = None
    if "--set" in sys.argv:
        value = sys.argv[sys.argv.index("--set") + 1].split("=", 1)[1]
    if value == "high":
        print(json.dumps({"avg_fps": 75.0, "one_percent_low_fps": 50.0}))
    else:
        print(json.dumps({"avg_fps": 60.0, "one_percent_low_fps": 40.0}))
    """

_BENCH_NO_IMPROVEMENT = """
    import sys, json
    value = None
    if "--set" in sys.argv:
        value = sys.argv[sys.argv.index("--set") + 1].split("=", 1)[1]
    if value == "low":
        print(json.dumps({"avg_fps": 45.0, "one_percent_low_fps": 25.0}))
    else:
        print(json.dumps({"avg_fps": 60.0, "one_percent_low_fps": 40.0}))
    """

_BENCH_GARBAGE_BASELINE = """
    print("not json at all")
    """

_BENCH_BASELINE_OK_CANDIDATES_GARBAGE = """
    import sys, json
    if "--set" in sys.argv:
        print("not json at all")
    else:
        print(json.dumps({"avg_fps": 60.0, "one_percent_low_fps": 40.0}))
    """


def test_game_config_measured_success(tmp_path):
    cmd = _bench_script(tmp_path, _BENCH_IMPROVES)
    exp = _bench_exp(cmd, {"shadow_quality": ["high", "low"]})
    r = asyncio.run(mx.run_experiment(exp, _ctx()))
    assert r.provenance == "measured"
    assert r.success is True
    assert r.metrics["best_value"] == "high"
    assert r.metrics["best_avg_fps"] > r.metrics["baseline_avg_fps"]
    assert r.metrics["best_one_percent_low_fps"] >= r.metrics["baseline_one_percent_low_fps"]


def test_game_config_measured_inconclusive(tmp_path):
    cmd = _bench_script(tmp_path, _BENCH_NO_IMPROVEMENT)
    exp = _bench_exp(cmd, {"shadow_quality": ["low"]})
    r = asyncio.run(mx.run_experiment(exp, _ctx()))
    assert r.provenance == "measured"
    assert r.success is False
    assert r.outcome == "inconclusive"


def test_game_config_no_benchmark_command_cannot_run():
    exp = {"id": "e1", "hypothesis": "tune fps",
           "variables": {"archetype": "game_config_optimization",
                         "game_tunables": {"x": ["a"]}},
           "observations": []}
    r = asyncio.run(mx.run_experiment(exp, _ctx()))
    assert r.provenance == "cannot_run"
    assert r.success is False
    assert r.metrics == {}
    assert "no benchmark command" in r.cannot_run_reason


def test_game_config_no_tunables_cannot_run(tmp_path):
    cmd = _bench_script(tmp_path, _BENCH_IMPROVES)
    exp = _bench_exp(cmd, {})
    r = asyncio.run(mx.run_experiment(exp, _ctx()))
    assert r.provenance == "cannot_run"
    assert r.success is False
    assert "tunables" in r.cannot_run_reason


def test_game_config_missing_binary_cannot_run():
    exp = _bench_exp(["/no/such/benchmark-binary"], {"x": ["a"]})
    r = asyncio.run(mx.run_experiment(exp, _ctx()))
    assert r.provenance == "cannot_run"
    assert r.success is False
    assert r.metrics == {}


def test_game_config_garbage_baseline_cannot_run(tmp_path):
    cmd = _bench_script(tmp_path, _BENCH_GARBAGE_BASELINE)
    exp = _bench_exp(cmd, {"x": ["a"]})
    r = asyncio.run(mx.run_experiment(exp, _ctx()))
    assert r.provenance == "cannot_run"
    assert r.success is False
    assert "baseline" in r.cannot_run_reason


def test_game_config_all_candidates_fail_cannot_run(tmp_path):
    cmd = _bench_script(tmp_path, _BENCH_BASELINE_OK_CANDIDATES_GARBAGE)
    exp = _bench_exp(cmd, {"x": ["a", "b"]})
    r = asyncio.run(mx.run_experiment(exp, _ctx()))
    assert r.provenance == "cannot_run"
    assert r.success is False
    assert "did not run for any candidate" in r.cannot_run_reason


def test_game_config_select_archetype():
    assert mx.select_archetype(
        "will lowering shadow quality improve my fps and 1% lows") == \
        "game_config_optimization"


def test_provenance_line():
    measured = {"provenance": "measured", "archetype": "model_throughput",
                "model": "llama-ai-eng", "runs": 3}
    assert "measured by" in mx.provenance_line(measured)
    cannot = {"provenance": "cannot_run", "archetype": "x",
              "cannot_run_reason": "no local model available"}
    assert "NOT RUN" in mx.provenance_line(cannot)


# ── debt scenario optimization ───────────────────────────────────────

def _balances_doc():
    return {
        "debts": [
            {"name": "card A", "balance": 6000.0, "apr": 24.99},
            {"name": "card B", "balance": 2000.0, "apr": 19.99},
        ],
        "candidate_scenarios": [
            # 7.99% on 8000 = 53.27/mo vs current 152.28/mo → saves ~99/mo,
            # 3% fee = 240 → breakeven 3 months.
            {"institution": "CU X", "product": "personal loan",
             "rate": 7.99, "fee_pct": 3.0},
            # 29% never saves anything.
            {"institution": "Bad Corp", "product": "worse loan",
             "rate": 29.0, "fee_pct": 5.0},
        ],
    }


def _debt_exp(tmp_path, doc):
    import json as _json
    f = tmp_path / "balances.json"
    f.write_text(_json.dumps(doc))
    return {"id": "e1", "hypothesis": "consolidating cuts interest",
            "variables": {"archetype": "debt_scenario_optimization",
                          "balances_file": str(f)},
            "observations": []}


def test_debt_select_archetype():
    assert mx.select_archetype(
        "will consolidating my credit card debt at a lower apr cut the "
        "total interest I pay") == "debt_scenario_optimization"
    assert mx.select_archetype(
        "does a balance transfer with a fee break even before the promo "
        "ends") == "debt_scenario_optimization"


def test_debt_scenario_measured_success(tmp_path):
    r = asyncio.run(mx.run_experiment(_debt_exp(tmp_path, _balances_doc()), _ctx()))
    assert r.provenance == "measured"
    assert r.outcome == "supported"
    assert r.success is True
    assert r.metrics["debts_count"] == 2
    assert r.metrics["scenarios_evaluated"] == 2
    assert r.metrics["best_scenario"] == 1
    # Hand-computed: current monthly interest = 6000*.2499/12 + 2000*.1999/12
    assert r.metrics["current_monthly_interest"] == pytest.approx(158.27, abs=0.01)
    assert r.metrics["best_breakeven_months"] == 3
    assert r.metrics["best_monthly_savings"] > 0


def test_debt_scenario_no_viable_scenario_not_supported(tmp_path):
    doc = _balances_doc()
    doc["candidate_scenarios"] = [doc["candidate_scenarios"][1]]  # only the bad one
    r = asyncio.run(mx.run_experiment(_debt_exp(tmp_path, doc), _ctx()))
    assert r.provenance == "measured"
    assert r.outcome == "not_supported"
    assert r.success is False
    assert "best_scenario" not in r.metrics


def test_debt_scenario_no_balances_file_cannot_run(tmp_path):
    exp = {"id": "e1", "hypothesis": "h",
           "variables": {"archetype": "debt_scenario_optimization",
                         "balances_file": str(tmp_path / "missing.json")},
           "observations": []}
    r = asyncio.run(mx.run_experiment(exp, _ctx()))
    assert r.provenance == "cannot_run"
    assert "no balances.json" in r.cannot_run_reason
    assert r.success is False


def test_debt_scenario_malformed_file_cannot_run(tmp_path):
    f = tmp_path / "balances.json"
    f.write_text("{not json")
    exp = {"id": "e1", "hypothesis": "h",
           "variables": {"archetype": "debt_scenario_optimization",
                         "balances_file": str(f)},
           "observations": []}
    r = asyncio.run(mx.run_experiment(exp, _ctx()))
    assert r.provenance == "cannot_run"
    assert r.success is False


def test_debt_scenario_no_scenarios_cannot_run(tmp_path):
    doc = _balances_doc()
    doc["candidate_scenarios"] = []
    r = asyncio.run(mx.run_experiment(_debt_exp(tmp_path, doc), _ctx()))
    assert r.provenance == "cannot_run"
    assert "no candidate_scenarios" in r.cannot_run_reason


def test_debt_scenario_never_leaks_balances_or_names(tmp_path):
    """Privacy: the experiment record identifies scenarios by index and
    reports derived values only — never a raw per-debt balance, an
    institution name, or a debt nickname."""
    ctx = _ctx()
    r = asyncio.run(mx.run_experiment(_debt_exp(tmp_path, _balances_doc()), ctx))
    payload = str(r.to_results_payload(ctx)) + r.conclusion
    assert "6000" not in payload      # raw balance
    assert "card A" not in payload    # debt nickname
    assert "CU X" not in payload      # institution name
    assert "Bad Corp" not in payload
