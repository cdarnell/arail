"""WP5: the mini-experiment engine measures for real and never fabricates.

Covers archetype selection, each archetype's measured/cannot_run paths, the
unmeasured path, and a regression assertion that the old hardcoded constants
(0.15 / 0.72 / data_points 24) never appear in engine output.
"""

from __future__ import annotations

import asyncio

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


def test_provenance_line():
    measured = {"provenance": "measured", "archetype": "model_throughput",
                "model": "llama-ai-eng", "runs": 3}
    assert "measured by" in mx.provenance_line(measured)
    cannot = {"provenance": "cannot_run", "archetype": "x",
              "cannot_run_reason": "no local model available"}
    assert "NOT RUN" in mx.provenance_line(cannot)
