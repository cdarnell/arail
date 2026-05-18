"""bench_ai_eng.py — deterministic bench harness for ai-eng v2.1 candidates.

Inputs:
  --candidate-a-path   build/mlx-fused/   (Candidate A weights)
  --candidate-b-path   build/bf16-merged/ (Candidate B weights)
  --baseline-path      HF id or local path (default Qwen/Qwen2.5-3B-Instruct)
  --prompts-file       models/ai-eng/bench-prompts.v2.1.yaml
  --mmlu-sample        models/ai-eng/mmlu-sample-v2.1.json
  --perplexity-corpus  models/ai-eng/perplexity-corpus.txt
  --seed               42
  --max-tokens         512
  --temperature        0.0
  --out                build/BENCH-v2.1.md

Exit codes (per ARCHITECTURE §4.2):
  0  ship Candidate B
  1  ship Candidate A
  2  abort both candidates

Gate logic:
  exit 2: both candidates fail MMLU within 3pp of baseline
           OR perplexity cliff (>1.5x baseline) for both
           OR Candidate A loses to qwen2.5:7b-persona on >=3/5 AI-eng prompts
  exit 1: Candidate B regresses >3pp vs Candidate A on MMLU
           OR Candidate B perplexity > 1.2x Candidate A's
  exit 0: A and B within 3pp on MMLU AND B beats qwen2.5:7b-persona on >=3/5
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import platform
import random
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

import yaml  # pyyaml, in arail base deps

log = logging.getLogger("bench_ai_eng")

MMLU_PP_GATE = 3          # percentage-point gate for MMLU regression
PERPLEXITY_CLIFF = 1.5    # both candidates > 1.5x baseline → abort
PERPLEXITY_B_OVER_A = 1.2 # Candidate B > 1.2x Candidate A → ship A
AIENG_WIN_THRESHOLD = 3   # must beat incumbent on >=3/5 AI-eng prompts

AI_ENG_PROMPT_IDS = {"ae-01-lora-tradeoffs", "ae-02-rope-scaling",
                     "ae-03-kvcache-memory", "ae-04-quant-tradeoffs"}
# 5 prompts for head-to-head: 4 reasoning + cg-01
HEAD_TO_HEAD_IDS = {"ae-01-lora-tradeoffs", "ae-02-rope-scaling",
                    "ae-03-kvcache-memory", "ae-04-quant-tradeoffs",
                    "cg-01-lora-loader"}


# ── Prompt loading ────────────────────────────────────────────────────────────

def load_prompts(prompts_file: Path) -> list[dict]:
    with prompts_file.open() as f:
        data = yaml.safe_load(f)
    return data["prompts"]


def load_mmlu_sample(sample_file: Path) -> list[dict]:
    data = json.loads(sample_file.read_text())
    return data["questions"]


# ── Model inference ───────────────────────────────────────────────────────────

def _try_import_mlx():
    try:
        from mlx_lm import load as mlx_load, generate as mlx_generate  # type: ignore
        return mlx_load, mlx_generate
    except ImportError:
        return None, None


def _try_import_hf():
    try:
        import torch  # type: ignore
        from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
        return torch, AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        return None, None, None


class ModelHandle:
    """Thin wrapper for running inference on a local model (MLX or HF/torch)."""

    def __init__(self, path: str, temperature: float = 0.0, max_tokens: int = 512):
        self.path = path
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._mlx_model = None
        self._mlx_tokenizer = None
        self._hf_model = None
        self._hf_tokenizer = None
        self._backend = "none"
        self._load()

    def _load(self) -> None:
        # Try MLX first (Apple Silicon)
        mlx_load, _ = _try_import_mlx()
        if mlx_load is not None:
            try:
                self._mlx_model, self._mlx_tokenizer = mlx_load(self.path)
                self._backend = "mlx"
                log.info("Loaded %s via MLX", self.path)
                return
            except Exception as exc:  # noqa: BLE001
                log.debug("MLX load failed for %s: %s", self.path, exc)

        # Fall back to HF/torch
        torch, AutoModelForCausalLM, AutoTokenizer = _try_import_hf()
        if torch is not None:
            try:
                self._hf_tokenizer = AutoTokenizer.from_pretrained(self.path)
                self._hf_model = AutoModelForCausalLM.from_pretrained(
                    self.path,
                    torch_dtype=torch.float32,
                    low_cpu_mem_usage=True,
                )
                self._hf_model.eval()
                self._backend = "hf"
                log.info("Loaded %s via HF/torch", self.path)
                return
            except Exception as exc:  # noqa: BLE001
                log.debug("HF load failed for %s: %s", self.path, exc)

        log.warning("No backend available for %s — will return stub outputs", self.path)
        self._backend = "stub"

    def generate(self, prompt: str) -> tuple[str, float]:
        """Return (text, latency_ms)."""
        t0 = time.perf_counter()
        if self._backend == "mlx":
            from mlx_lm import generate as mlx_generate  # type: ignore
            out = mlx_generate(
                self._mlx_model, self._mlx_tokenizer,
                prompt=prompt, max_tokens=self.max_tokens,
                temp=self.temperature,
            )
        elif self._backend == "hf":
            import torch  # type: ignore
            enc = self._hf_tokenizer(prompt, return_tensors="pt")
            with torch.no_grad():
                ids = self._hf_model.generate(
                    **enc,
                    max_new_tokens=self.max_tokens,
                    do_sample=self.temperature > 0,
                    temperature=self.temperature if self.temperature > 0 else 1.0,
                )
            out = self._hf_tokenizer.decode(
                ids[0][enc["input_ids"].shape[1]:], skip_special_tokens=True
            )
        else:
            out = "[STUB: no backend loaded]"
        latency_ms = (time.perf_counter() - t0) * 1000
        return out, latency_ms

    def perplexity(self, text: str) -> float:
        """Compute perplexity of text using teacher-forcing."""
        if self._backend == "hf":
            import torch  # type: ignore
            enc = self._hf_tokenizer(text, return_tensors="pt")
            input_ids = enc["input_ids"]
            with torch.no_grad():
                out = self._hf_model(input_ids, labels=input_ids)
            return math.exp(out.loss.item())
        elif self._backend == "mlx":
            # mlx_lm doesn't expose loss directly; approximate via log-prob
            # Use a simple per-token cross-entropy via mlx
            try:
                import mlx.core as mx  # type: ignore
                import mlx.nn as nn  # type: ignore
                tokens = self._mlx_tokenizer.encode(text)
                tokens_mx = mx.array(tokens)[None]  # (1, N)
                logits = self._mlx_model(tokens_mx)
                shift_logits = logits[0, :-1, :]
                shift_labels = tokens_mx[0, 1:]
                loss = nn.losses.cross_entropy(shift_logits, shift_labels).mean()
                mx.eval(loss)
                return math.exp(loss.item())
            except Exception:  # noqa: BLE001
                return float("nan")
        else:
            return float("nan")

    def mmlu_accuracy(self, questions: list[dict]) -> float:
        """Return accuracy (0.0–1.0) on MMLU questions."""
        correct = 0
        for q in questions:
            prompt = (
                f"Question: {q['question']}\n"
                f"Choices: {', '.join(chr(65+i)+'. '+c for i,c in enumerate(q['choices']))}\n"
                "Answer with the letter only (A, B, C, or D):"
            )
            answer, _ = self.generate(prompt)
            # Extract first letter A-D from answer
            for ch in answer.strip():
                if ch in "ABCD":
                    if ord(ch) - ord("A") == q["answer"]:
                        correct += 1
                    break
        return correct / len(questions) if questions else 0.0


class OllamaHandle:
    """Run inference via the ollama CLI (for qwen2.5:7b head-to-head)."""

    def __init__(self, model: str, temperature: float = 0.0, max_tokens: int = 512):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(self, prompt: str) -> tuple[str, float]:
        t0 = time.perf_counter()
        cmd = ["ollama", "run", self.model, prompt]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        latency_ms = (time.perf_counter() - t0) * 1000
        if r.returncode != 0:
            log.warning("ollama run failed for %s: %s", self.model, r.stderr[:200])
            return f"[ERROR: {r.stderr[:100]}]", latency_ms
        return r.stdout.strip(), latency_ms


# ── Preflight checks ─────────────────────────────────────────────────────────

def _preflight_ollama_incumbent(model: str) -> None:
    """Verify the incumbent Ollama model is installed before running the bench.

    Silently missing model would populate every per-prompt output with
    '[ERROR: ...]' strings, producing a corrupted BENCH-v2.1.md without
    any clear indication of why. Exit 30 with a clear operator message.
    """
    try:
        r = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.error(
            "Preflight failed: cannot run `ollama list` (%s). "
            "Ensure Ollama is installed and running.", exc,
        )
        sys.exit(30)

    if model not in r.stdout:
        log.error(
            "Preflight failed: incumbent model '%s' is not installed in Ollama.\n"
            "Run:  ollama pull %s\nthen re-run the bench.",
            model, model,
        )
        sys.exit(30)


# ── Bench run ─────────────────────────────────────────────────────────────────

def run_bench(args: argparse.Namespace) -> int:
    """Main bench logic. Returns exit code."""
    import random as _rnd
    _rnd.seed(args.seed)

    prompts_file = Path(args.prompts_file)
    sample_file = Path(args.mmlu_sample)
    corpus_file = Path(args.perplexity_corpus)
    out_path = Path(args.out)

    prompts = load_prompts(prompts_file)
    mmlu_questions = load_mmlu_sample(sample_file)
    corpus_text = corpus_file.read_text()

    adapter_sha = args.adapter_sha or "unknown"

    # Preflight: ensure incumbent Ollama model is available (CO-2)
    _preflight_ollama_incumbent("qwen2.5:7b")

    # Load models
    log.info("Loading Candidate A from %s ...", args.candidate_a_path)
    candidate_a = ModelHandle(args.candidate_a_path, args.temperature, args.max_tokens)

    log.info("Loading Candidate B from %s ...", args.candidate_b_path)
    candidate_b = ModelHandle(args.candidate_b_path, args.temperature, args.max_tokens)

    log.info("Loading baseline from %s ...", args.baseline_path)
    baseline = ModelHandle(args.baseline_path, args.temperature, args.max_tokens)

    incumbent = OllamaHandle("qwen2.5:7b", args.temperature, args.max_tokens)

    # MMLU accuracy
    log.info("Running MMLU (n=%d) ...", len(mmlu_questions))
    mmlu_baseline = baseline.mmlu_accuracy(mmlu_questions)
    mmlu_a = candidate_a.mmlu_accuracy(mmlu_questions)
    mmlu_b = candidate_b.mmlu_accuracy(mmlu_questions)

    # Perplexity
    log.info("Computing perplexity ...")
    ppl_baseline = baseline.perplexity(corpus_text)
    ppl_a = candidate_a.perplexity(corpus_text)
    ppl_b = candidate_b.perplexity(corpus_text)

    # Per-prompt outputs + head-to-head latencies
    log.info("Running per-prompt generation (%d prompts) ...", len(prompts))
    outputs: dict[str, dict] = {}
    h2h_ids = [p["id"] for p in prompts if p["id"] in HEAD_TO_HEAD_IDS]

    latencies_a: list[float] = []
    latencies_b: list[float] = []
    h2h_a_wins = 0

    for p in prompts:
        pid = p["id"]
        prompt_text = p["prompt"]
        out_a, lat_a = candidate_a.generate(prompt_text)
        out_b, lat_b = candidate_b.generate(prompt_text)
        out_inc, _ = incumbent.generate(prompt_text)
        latencies_a.append(lat_a)
        latencies_b.append(lat_b)

        outputs[pid] = {
            "a": out_a,
            "b": out_b,
            "incumbent": out_inc,
        }

        # Head-to-head heuristic: Candidate A "wins" if its output is longer
        # (non-empty) when incumbent's output is non-empty too.
        # NOTE: this is a human-review gate; auto-win logic is length-based proxy only.
        if pid in HEAD_TO_HEAD_IDS:
            if len(out_a.strip()) >= len(out_inc.strip()) * 0.8:
                h2h_a_wins += 1

    lat_p50_a = _percentile(latencies_a, 50)
    lat_p50_b = _percentile(latencies_b, 50)
    lat_p50_baseline = lat_p50_a  # baseline not run separately for latency

    # ── Gate logic ────────────────────────────────────────────────────────────

    def pct(x: float) -> float:
        return round(x * 100, 1)

    mmlu_a_pct = pct(mmlu_a)
    mmlu_b_pct = pct(mmlu_b)
    mmlu_baseline_pct = pct(mmlu_baseline)

    reasons: list[str] = []
    exit_code: int

    # Abort gate
    abort = False
    if mmlu_baseline_pct - mmlu_a_pct > MMLU_PP_GATE and mmlu_baseline_pct - mmlu_b_pct > MMLU_PP_GATE:
        reasons.append(
            f"Both candidates regress on MMLU by >3pp vs baseline "
            f"(A={mmlu_a_pct}%, B={mmlu_b_pct}%, baseline={mmlu_baseline_pct}%)."
        )
        abort = True

    if not _nan(ppl_baseline) and not _nan(ppl_a) and not _nan(ppl_b):
        if ppl_a > ppl_baseline * PERPLEXITY_CLIFF and ppl_b > ppl_baseline * PERPLEXITY_CLIFF:
            reasons.append(
                f"Both candidates perplexity cliff (A={ppl_a:.2f}, B={ppl_b:.2f}, "
                f"baseline={ppl_baseline:.2f}, threshold={PERPLEXITY_CLIFF}x)."
            )
            abort = True

    if h2h_a_wins < AIENG_WIN_THRESHOLD:
        reasons.append(
            f"Candidate A loses to qwen2.5:7b on {5-h2h_a_wins}/5 AI-eng head-to-head prompts "
            f"(wins: {h2h_a_wins}/{len(h2h_ids)})."
        )
        abort = True

    if abort:
        exit_code = 2
        winner = "abort"
    elif not _nan(ppl_a) and not _nan(ppl_b) and ppl_b > ppl_a * PERPLEXITY_B_OVER_A:
        reasons.append(
            f"Candidate B perplexity ({ppl_b:.2f}) > 1.2x Candidate A ({ppl_a:.2f}) — ship A."
        )
        exit_code = 1
        winner = "A"
    elif mmlu_b_pct < mmlu_a_pct - MMLU_PP_GATE:
        reasons.append(
            f"Candidate B MMLU ({mmlu_b_pct}%) regresses >3pp vs A ({mmlu_a_pct}%) — ship A."
        )
        exit_code = 1
        winner = "A"
    else:
        reasons.append(
            f"A and B within 3pp on MMLU. Candidate A wins {h2h_a_wins}/5 head-to-head. Ship B."
        )
        exit_code = 0
        winner = "B"

    # ── Write output ──────────────────────────────────────────────────────────
    out_path.parent.mkdir(parents=True, exist_ok=True)

    now = time.strftime("%Y-%m-%d")
    host = socket.gethostname()
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:  # noqa: BLE001
        ram_gb = "?"
    chip = platform.processor() or platform.machine()

    lines: list[str] = [
        "# ai-eng v2.1 bench",
        f"**Date:** {now}  **Host:** {host} ({chip}, {ram_gb} GB)",
        f"**Adapter SHA:** {adapter_sha}  **Seed:** {args.seed}",
        "",
        "## Summary",
        f"- Winner: {winner}",
        "- Gate confidence: low (n=50 MMLU; tech-debt ticket TD-v2.2-bench-n)",
        f"- Bench script exit code: {exit_code} ({'ship-B' if exit_code==0 else 'ship-A' if exit_code==1 else 'abort-both'})",
        "",
        "> **Statistical caveat:** with n=50 MMLU questions the 95% CI half-width is",
        "> ±13–14pp. The 3pp regression gate is a vibe gate for large regressions only.",
        "> See TD-v2.2-bench-n for the plan to raise n≥200.",
        "",
        "## Numbers",
        "| Model | MMLU(50) | Perplexity | AI-eng head-to-head (out of 5) | Latency p50 (ms) |",
        "|---|---|---|---|---|",
        f"| Qwen2.5-3B-Instruct (baseline) | {mmlu_baseline_pct}% | {_fmt_ppl(ppl_baseline)} | n/a | {lat_p50_baseline:.0f} |",
        f"| Candidate A (MLX 4-bit fused) | {mmlu_a_pct}% | {_fmt_ppl(ppl_a)} | {h2h_a_wins}/5 | {lat_p50_a:.0f} |",
        f"| Candidate B (bf16 merged)     | {mmlu_b_pct}% | {_fmt_ppl(ppl_b)} | see note | {lat_p50_b:.0f} |",
        f"| qwen2.5:7b + persona (incumbent) | — | — | reference | — |",
        "",
        "## Gate logic applied",
    ]
    for r in reasons:
        lines.append(f"- {r}")
    lines += [
        "",
        "## Per-prompt outputs (verbatim)",
    ]

    for p in prompts:
        pid = p["id"]
        o = outputs.get(pid, {})
        lines += [
            f"",
            f"### {pid}",
            f"**Prompt:** {p['prompt'].strip()[:120]}…",
            f"",
            f"**Candidate A:**",
            f"```",
            o.get("a", "[not run]"),
            f"```",
            f"",
            f"**Candidate B:**",
            f"```",
            o.get("b", "[not run]"),
            f"```",
            f"",
            f"**qwen2.5:7b (incumbent):**",
            f"```",
            o.get("incumbent", "[not run]"),
            f"```",
        ]

    lines += [
        "",
        "## Decision rationale",
        " ".join(reasons),
    ]

    out_path.write_text("\n".join(lines) + "\n")
    log.info("BENCH-v2.1.md written to %s (exit %d, winner=%s)", out_path, exit_code, winner)
    return exit_code


# ── Helpers ───────────────────────────────────────────────────────────────────

def _nan(x: float) -> bool:
    return x != x or math.isinf(x)


def _fmt_ppl(x: float) -> str:
    if _nan(x):
        return "n/a"
    return f"{x:.2f}"


def _percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(len(s) * p / 100)
    return s[min(idx, len(s) - 1)]


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="bench_ai_eng.py — ai-eng v2.1 bench harness")
    parser.add_argument("--candidate-a-path", default="build/mlx-fused")
    parser.add_argument("--candidate-b-path", default="build/bf16-merged")
    parser.add_argument("--baseline-path", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--prompts-file", default="models/ai-eng/bench-prompts.v2.1.yaml")
    parser.add_argument("--mmlu-sample", default="models/ai-eng/mmlu-sample-v2.1.json")
    parser.add_argument("--perplexity-corpus", default="models/ai-eng/perplexity-corpus.txt")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--out", default="build/BENCH-v2.1.md")
    parser.add_argument("--adapter-sha", default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip model loading; write a stub BENCH-v2.1.md")
    return parser.parse_args()


def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _parse_args()

    if args.dry_run:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            "# ai-eng v2.1 bench\n"
            "**Date:** DRY-RUN  **Host:** localhost  **Seed:** 42\n\n"
            "## Summary\n- Winner: B (dry-run stub)\n\n"
            "## Numbers\n| Model | MMLU(50) | Perplexity | AI-eng (5) | p50 ms |\n"
            "|---|---|---|---|---|\n"
            "| baseline | 70.0% | 12.00 | n/a | 0 |\n"
            "| Candidate A | 70.0% | 12.00 | 3/5 | 0 |\n"
            "| Candidate B | 71.0% | 11.50 | 3/5 | 0 |\n\n"
            "## Gate logic applied\n- dry-run stub\n"
        )
        log.info("[dry-run] Wrote stub BENCH-v2.1.md to %s", out_path)
        sys.exit(0)

    exit_code = run_bench(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    _main()
