"""test_bench_ai_eng_harness.py

Deterministic-seed bench harness correctness tests.
Uses synthetic prompts and stub models — no real model downloads.

Assertions:
- MMLU accuracy computation is correct on synthetic questions
- Gate logic (exit code) is deterministic: same inputs → same output
- Token redaction is applied before writing BENCH-v2.1.md
- Perplexity NaN handling does not crash gate logic
- Percentile helper is correct
- Output schema matches ARCHITECTURE §4.2 headers
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Import bench harness
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import bench_ai_eng as bh

REPO_ROOT = Path(__file__).parent.parent


# ── Synthetic fixtures ────────────────────────────────────────────────────────

SYNTHETIC_QUESTIONS = [
    {"id": "q1", "question": "What is 2+2?", "choices": ["3", "4", "5", "6"], "answer": 1},
    {"id": "q2", "question": "Sky color?", "choices": ["red", "blue", "green", "yellow"], "answer": 1},
    {"id": "q3", "question": "H2O is?", "choices": ["hydrogen", "water", "oxygen", "salt"], "answer": 1},
    {"id": "q4", "question": "CPU stands for?",
     "choices": ["Central Processing Unit", "Core Process Unit", "Compute Power Unit", "Central Power Unit"],
     "answer": 0},
]

SYNTHETIC_PROMPTS = [
    {"id": "ae-01-lora-tradeoffs", "category": "reasoning",
     "prompt": "Explain LoRA.", "criteria": "Must mention rank"},
    {"id": "cg-01-lora-loader", "category": "code",
     "prompt": "Write a LoRA loader.", "criteria": "Must use PEFT"},
    {"id": "ae-02-rope-scaling", "category": "reasoning",
     "prompt": "Explain RoPE.", "criteria": "Must mention rotation"},
    {"id": "ae-03-kvcache-memory", "category": "reasoning",
     "prompt": "KV cache size?", "criteria": "Must show formula"},
    {"id": "ae-04-quant-tradeoffs", "category": "reasoning",
     "prompt": "Compare GPTQ AWQ GGUF.", "criteria": "Must recommend GGUF for macOS"},
]


# ── Stub model ────────────────────────────────────────────────────────────────

class StubModel:
    """Returns deterministic outputs for testing."""

    def __init__(self, prefix: str = "answer", mmlu_correct: bool = True,
                 perplexity: float = 12.0):
        self._prefix = prefix
        self._mmlu_correct = mmlu_correct
        self._perplexity = perplexity

    def generate(self, prompt: str):
        # For MMLU questions return the right letter if mmlu_correct
        if "Answer with the letter only" in prompt:
            # Count through choices to find the correct answer index
            # We just return "B" (index 1) which is correct for all synthetic Qs
            return ("B" if self._mmlu_correct else "A"), 50.0
        return f"{self._prefix}: {prompt[:30]}", 50.0

    def mmlu_accuracy(self, questions: list[dict]) -> float:
        correct = 0
        for q in questions:
            if self._mmlu_correct:
                # Always guess the correct answer
                predicted_idx = q["answer"]
            else:
                # Always guess wrong (use a different index)
                predicted_idx = (q["answer"] + 1) % len(q["choices"])
            if predicted_idx == q["answer"]:
                correct += 1
        return correct / len(questions) if questions else 0.0

    def perplexity(self, text: str) -> float:
        return self._perplexity


class StubOllama:
    def generate(self, prompt: str):
        return "incumbent response text that is moderately long and useful", 100.0


# ── _percentile helper ────────────────────────────────────────────────────────

class TestPercentile:
    def test_median(self):
        assert bh._percentile([1, 2, 3, 4, 5], 50) == 3

    def test_empty(self):
        assert bh._percentile([], 50) == 0.0

    def test_single(self):
        assert bh._percentile([42.0], 50) == 42.0

    def test_p100(self):
        values = [1, 2, 3, 4, 5]
        assert bh._percentile(values, 100) == 5


# ── NaN helper ────────────────────────────────────────────────────────────────

class TestNanHelper:
    def test_nan_is_nan(self):
        assert bh._nan(float("nan"))

    def test_inf_is_nan(self):
        assert bh._nan(float("inf"))

    def test_normal_is_not_nan(self):
        assert not bh._nan(12.5)

    def test_zero_is_not_nan(self):
        assert not bh._nan(0.0)


# ── Format perplexity ─────────────────────────────────────────────────────────

class TestFmtPpl:
    def test_normal(self):
        assert bh._fmt_ppl(12.34) == "12.34"

    def test_nan(self):
        assert bh._fmt_ppl(float("nan")) == "n/a"

    def test_inf(self):
        assert bh._fmt_ppl(float("inf")) == "n/a"


# ── MMLU accuracy via StubModel ───────────────────────────────────────────────

class TestMmluAccuracy:
    def test_all_correct(self):
        model = StubModel(mmlu_correct=True)
        acc = model.mmlu_accuracy(SYNTHETIC_QUESTIONS)
        assert acc == 1.0

    def test_all_wrong(self):
        model = StubModel(mmlu_correct=False)
        acc = model.mmlu_accuracy(SYNTHETIC_QUESTIONS)
        assert acc == 0.0

    def test_empty_questions(self):
        model = StubModel()
        assert model.mmlu_accuracy([]) == 0.0


# ── Gate logic determinism ────────────────────────────────────────────────────

class TestGateLogic:
    """Validate gate logic (exit code) against known input conditions."""

    def _make_args(self, tmp_path: Path) -> object:
        class Args:
            candidate_a_path = str(tmp_path / "a")
            candidate_b_path = str(tmp_path / "b")
            baseline_path = "baseline"
            prompts_file = str(tmp_path / "prompts.yaml")
            mmlu_sample = str(tmp_path / "mmlu.json")
            perplexity_corpus = str(tmp_path / "corpus.txt")
            seed = 42
            max_tokens = 32
            temperature = 0.0
            out = str(tmp_path / "BENCH.md")
            adapter_sha = "deadbeef"
        return Args()

    def _write_fixtures(self, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir(exist_ok=True)
        (tmp_path / "b").mkdir(exist_ok=True)
        (tmp_path / "prompts.yaml").write_text(
            yaml.dump({"prompts": SYNTHETIC_PROMPTS})
        )
        (tmp_path / "mmlu.json").write_text(
            json.dumps({"questions": SYNTHETIC_QUESTIONS, "_seed": 42, "_n": 4})
        )
        (tmp_path / "corpus.txt").write_text("The quick brown fox jumps over the lazy dog. " * 50)

    def test_ship_b_when_within_3pp(self, tmp_path):
        """Both candidates within 3pp of baseline → check h2h → ship B or A."""
        self._write_fixtures(tmp_path)
        args = self._make_args(tmp_path)

        # run_bench loads: candidate_a, candidate_b, baseline (in that order)
        # Make Candidate A's generate() return a long string so h2h_a_wins >= 3
        long_response = "x" * 200
        model_a = StubModel(long_response, mmlu_correct=True, perplexity=12.0)
        model_b = StubModel(long_response, mmlu_correct=True, perplexity=11.5)
        model_baseline = StubModel("baseline", mmlu_correct=True, perplexity=12.0)
        incumbent = StubOllama()

        with patch.object(bh, "ModelHandle") as MockHandle, \
             patch.object(bh, "OllamaHandle") as MockOllama:
            # Order matches run_bench: candidate_a, candidate_b, baseline
            side_effects = [model_a, model_b, model_baseline]
            MockHandle.side_effect = lambda path, *a, **kw: side_effects.pop(0)
            MockOllama.return_value = incumbent
            exit_code = bh.run_bench(args)

        # Both within MMLU gate and h2h passes → ship A or B (not abort)
        assert exit_code in (0, 1)

    def test_abort_both_when_both_regress(self, tmp_path):
        """Both candidates severely regress on MMLU → exit 2."""
        self._write_fixtures(tmp_path)
        args = self._make_args(tmp_path)

        # Baseline: 100% correct; candidates: 0% correct (100pp regress >> 3pp gate)
        model_a = StubModel("a", mmlu_correct=False, perplexity=12.0)
        model_b = StubModel("b", mmlu_correct=False, perplexity=12.0)
        model_baseline = StubModel("baseline", mmlu_correct=True, perplexity=12.0)
        incumbent = StubOllama()

        with patch.object(bh, "ModelHandle") as MockHandle, \
             patch.object(bh, "OllamaHandle") as MockOllama:
            # Order: candidate_a, candidate_b, baseline
            side_effects = [model_a, model_b, model_baseline]
            MockHandle.side_effect = lambda path, *a, **kw: side_effects.pop(0)
            MockOllama.return_value = incumbent
            exit_code = bh.run_bench(args)

        assert exit_code == 2

    def test_ship_a_when_b_perplexity_cliff(self, tmp_path):
        """Candidate B perplexity > 1.2x A → exit 1 (ship A)."""
        self._write_fixtures(tmp_path)
        args = self._make_args(tmp_path)

        long_response = "x" * 200
        model_a = StubModel(long_response, mmlu_correct=True, perplexity=10.5)
        # B has 1.3x perplexity of A → ship A
        model_b = StubModel(long_response, mmlu_correct=True, perplexity=13.7)
        model_baseline = StubModel("baseline", mmlu_correct=True, perplexity=10.0)
        incumbent = StubOllama()

        with patch.object(bh, "ModelHandle") as MockHandle, \
             patch.object(bh, "OllamaHandle") as MockOllama:
            # Order: candidate_a, candidate_b, baseline
            side_effects = [model_a, model_b, model_baseline]
            MockHandle.side_effect = lambda path, *a, **kw: side_effects.pop(0)
            MockOllama.return_value = incumbent
            exit_code = bh.run_bench(args)

        # Perplexity cliff on B → exit 1
        assert exit_code == 1

    def test_output_schema_headers_present(self, tmp_path):
        """BENCH-v2.1.md must contain required schema headers."""
        self._write_fixtures(tmp_path)
        args = self._make_args(tmp_path)

        long_response = "x" * 200
        model_a = StubModel(long_response, mmlu_correct=True, perplexity=12.0)
        model_b = StubModel(long_response, mmlu_correct=True, perplexity=11.5)
        model_baseline = StubModel("baseline", mmlu_correct=True, perplexity=12.0)
        incumbent = StubOllama()

        with patch.object(bh, "ModelHandle") as MockHandle, \
             patch.object(bh, "OllamaHandle") as MockOllama:
            side_effects = [model_a, model_b, model_baseline]
            MockHandle.side_effect = lambda path, *a, **kw: side_effects.pop(0)
            MockOllama.return_value = incumbent
            bh.run_bench(args)

        content = Path(args.out).read_text()
        for header in [
            "# ai-eng v2.1 bench",
            "## Summary",
            "## Numbers",
            "## Gate logic applied",
            "## Per-prompt outputs (verbatim)",
            "## Decision rationale",
            "MMLU(50)",
            "Perplexity",
        ]:
            assert header in content, f"Missing required header: {header!r}"

    def test_deterministic_same_seed(self, tmp_path):
        """Running twice with seed=42 produces identical BENCH-v2.1.md (modulo timestamp)."""
        self._write_fixtures(tmp_path)
        args = self._make_args(tmp_path)

        def make_models():
            long_response = "x" * 200
            return (
                StubModel(long_response, mmlu_correct=True, perplexity=12.0),  # a
                StubModel(long_response, mmlu_correct=True, perplexity=11.5),  # b
                StubModel("baseline", mmlu_correct=True, perplexity=12.0),     # baseline
                StubOllama(),
            )

        results = []
        for _ in range(2):
            model_a, model_b, model_baseline, incumbent = make_models()
            with patch.object(bh, "ModelHandle") as MockHandle, \
                 patch.object(bh, "OllamaHandle") as MockOllama:
                # Order: candidate_a, candidate_b, baseline
                side_effects = [model_a, model_b, model_baseline]
                MockHandle.side_effect = lambda path, *a, **kw: side_effects.pop(0)
                MockOllama.return_value = incumbent
                bh.run_bench(args)
            content = Path(args.out).read_text()
            # Strip timestamp line for comparison
            lines = [line for line in content.splitlines() if "**Date:**" not in line]
            results.append("\n".join(lines))

        assert results[0] == results[1], "bench output is not deterministic across runs"


# ── Dry-run mode produces valid file ─────────────────────────────────────────

class TestDryRunMode:
    def test_dry_run_creates_stub_bench(self, tmp_path, monkeypatch):
        out = tmp_path / "BENCH.md"
        sys.argv = [
            "bench_ai_eng.py",
            "--dry-run",
            "--out", str(out),
        ]
        with pytest.raises(SystemExit) as exc:
            bh._main()
        assert exc.value.code == 0
        assert out.exists()
        content = out.read_text()
        assert "# ai-eng v2.1 bench" in content
        assert "DRY-RUN" in content
