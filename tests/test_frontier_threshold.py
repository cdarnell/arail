"""Frontier (70B) threshold — distinct from the 30B OOM floor.

The 30B floor (`must_stream`) is a hardware fact: what fits in GPU. The 70B
"frontier" line (`is_frontier`) is the product framing that drives the chat
comparison view's "2nd inference" branding + auto-default. A 32B model
must_stream but is NOT frontier.
"""
from __future__ import annotations

from arail import model_specs as ms


def test_constants_unchanged_and_distinct():
    assert ms.HARDWARE_FLOOR_TOTAL_B == 30.0
    assert ms.FRONTIER_HEADLINE_B == 70.0


def test_frontier_true():
    for name in [
        "Llama-3.1-70B",
        "Qwen2.5-72B-Instruct-4bit",
        "Qwen3-235B-A22B",
        "Llama-3.1-405B",
    ]:
        assert ms.is_frontier(name) is True, name


def test_frontier_false():
    for name in ["deepseek-r1:32b", "Qwen2.5-7B", "phi4:14b", "gemma2:9b", "", "no-params-here"]:
        assert ms.is_frontier(name) is False, name


def test_floor_still_catches_32b_but_not_frontier():
    # 32B is over the OOM floor (must stream) but is not a frontier model.
    assert ms.must_stream("deepseek-r1:32b") is True
    assert ms.is_frontier("deepseek-r1:32b") is False


def test_moe_override_counts_total_params_for_frontier():
    # Llama-4 Maverick = 400B total via MODEL_METADATA_OVERRIDES (name says 17B).
    assert ms.is_frontier("Llama-4-Maverick-17B-128E-Instruct") is True
    assert ms.must_stream("Llama-4-Maverick-17B-128E-Instruct") is True
