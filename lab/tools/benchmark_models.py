#!/usr/bin/env python3
"""
Benchmark harness for model profiling.

Measures single-prompt and batched throughput (tokens/sec) for each model.
Outputs to lab/data/model_profiles.json for agent routing decisions.

Usage:
  python lab/tools/benchmark_models.py --model qwen-7b --batch-size 1 50
  python lab/tools/benchmark_models.py --all                    # benchmark all configured models
  python lab/tools/benchmark_models.py --all --batch-size 1 10 50  # custom batch sizes
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

# ── Logging ──────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────

LAB_ROOT = Path(__file__).parent.parent
ARAIL_ROOT = LAB_ROOT.parent
DATA_DIR = LAB_ROOT / "data"
MODELS_DIR = ARAIL_ROOT / "models"  # Models live in arail/models/, not lab/models/
PROFILES_PATH = DATA_DIR / "model_profiles.json"

# Standard test prompt (measures both prompt + generation TPS)
TEST_PROMPT = """You are an AI research assistant. Analyze the following query and provide a concise, structured response.

Query: Explain the differences between MoE (Mixture of Experts) and dense transformer architectures in terms of inference efficiency and latency tradeoffs.

Provide your analysis in 200-300 tokens, structured as:
1. Throughput characteristics
2. Latency characteristics
3. When to use each

Be precise and educational."""

# Test params
DEFAULT_MAX_TOKENS = 256
DEFAULT_BATCH_SIZES = [1, 50]  # Single and full batch


@dataclass
class BenchmarkRun:
    """One timing measurement."""

    model: str
    backend: str  # "airllm" | "aerollm" | "anthropic" | "mlx"
    batch_size: int
    prompt_tokens: int
    output_tokens: int
    total_latency_ms: float
    tokens_per_sec: float  # output_tokens / (total_latency_ms / 1000)
    ts: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelBenchmark:
    """Benchmark a model via its configured backend."""

    def __init__(self, model_name: str, backend: str):
        """
        Args:
            model_name: Name/ID of the model (e.g., "Qwen2.5-7B-Instruct")
            backend: Backend type ("airllm", "anthropic", etc.)
        """
        self.model_name = model_name
        self.backend = backend

    def benchmark(
        self,
        batch_size: int = 1,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> BenchmarkRun | None:
        """
        Run one benchmark iteration.

        Args:
            batch_size: How many prompts to batch (1 = single)
            max_tokens: Max output tokens

        Returns:
            BenchmarkRun with timing, or None on error.
        """
        try:
            if self.backend == "anthropic":
                return self._benchmark_anthropic(batch_size, max_tokens)
            elif self.backend == "airllm":
                return self._benchmark_airllm(batch_size, max_tokens)
            elif self.backend == "aerollm":
                return self._benchmark_aerollm(batch_size, max_tokens)
            else:
                log.error(f"Unknown backend: {self.backend}")
                return None
        except Exception as e:
            log.error(f"Benchmark failed for {self.model_name} ({self.backend}): {e}")
            return None

    def _benchmark_anthropic(
        self,
        batch_size: int,
        max_tokens: int,
    ) -> BenchmarkRun | None:
        """Benchmark Claude via Anthropic API."""
        if not os.getenv("ANTHROPIC_API_KEY"):
            log.error("ANTHROPIC_API_KEY not set")
            return None

        # Map model alias to actual Claude model
        # Map model alias to a current Claude model. The previous targets
        # (claude-3-5-sonnet-20241022) retired 2026-02-19 and would 404.
        model_map = {
            "claude-opus": "claude-opus-4-7",
            "claude-sonnet": "claude-sonnet-4-6",
        }
        actual_model = model_map.get(self.model_name.lower(), self.model_name)

        client = anthropic.Anthropic()

        start_time = time.time()
        try:
            message = client.messages.create(
                model=actual_model,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": TEST_PROMPT
                        * batch_size,  # Simple batching: repeat prompt
                    }
                ],
            )
            latency_ms = (time.time() - start_time) * 1000

            prompt_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            tps = output_tokens / (latency_ms / 1000) if latency_ms > 0 else 0

            return BenchmarkRun(
                model=self.model_name,
                backend="anthropic",
                batch_size=batch_size,
                prompt_tokens=prompt_tokens,
                output_tokens=output_tokens,
                total_latency_ms=latency_ms,
                tokens_per_sec=tps,
                ts=datetime.now(timezone.utc).isoformat(),
            )
        except anthropic.APIError as e:
            log.error(f"API error: {e}")
            return None

    def _benchmark_airllm(
        self,
        batch_size: int,
        max_tokens: int,
    ) -> BenchmarkRun | None:
        """Benchmark model via AirLLM (local layer-streaming)."""
        try:
            from transformers import pipeline
        except ImportError:
            log.error("Transformers not installed")
            return None

        try:
            # Use transformers pipeline for simpler API
            model_path = MODELS_DIR / self.model_name
            if not model_path.exists():
                log.error(f"Model not found at {model_path}")
                return None

            # Create a text generation pipeline
            pipe = pipeline(
                "text-generation",
                model=str(model_path),
                device_map="auto",
                trust_remote_code=True,
            )

            # Prepare prompts
            prompt = TEST_PROMPT * batch_size

            # Time generation
            start_time = time.time()
            outputs = pipe(
                prompt,
                max_new_tokens=max_tokens,
                return_full_text=False,
            )
            latency_ms = (time.time() - start_time) * 1000

            # Extract token counts (approximate from text)
            generated_text = outputs[0].get("generated_text", "")
            # Rough estimate: ~4 chars per token
            output_tokens = len(generated_text) // 4
            prompt_tokens = len(prompt) // 4

            tps = output_tokens / (latency_ms / 1000) if latency_ms > 0 else 0

            return BenchmarkRun(
                model=self.model_name,
                backend="airllm",
                batch_size=batch_size,
                prompt_tokens=prompt_tokens,
                output_tokens=output_tokens,
                total_latency_ms=latency_ms,
                tokens_per_sec=tps,
                ts=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as e:
            log.error(f"AirLLM benchmark error: {e}")
            return None

    def _benchmark_aerollm(
        self,
        batch_size: int,
        max_tokens: int,
    ) -> BenchmarkRun | None:
        """Benchmark model via AeroLLM (Rust runtime)."""
        # TODO: wire this once AeroLLM stable Rust API is available
        log.warning("AeroLLM benchmarking not yet implemented")
        return None


# ── Model registry ──────────────────────────────────────────────

@dataclass
class ModelProfile:
    """Capability profile for agent routing."""

    model: str
    arch: str
    backend: str
    single_prompt_tps: float | None = None
    batched_tps: float | None = None  # Measured at batch_size=50
    context_window: int | None = None
    cost_per_1m_tokens: float = 0  # USD; 0 for local
    last_benchmarked: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_profiles() -> dict[str, ModelProfile]:
    """Load existing model_profiles.json."""
    if not PROFILES_PATH.exists():
        return {}
    try:
        data = json.loads(PROFILES_PATH.read_text())
        return {
            name: ModelProfile(**profile) for name, profile in data.items()
        }
    except Exception as e:
        log.error(f"Failed to load profiles: {e}")
        return {}


def save_profiles(profiles: dict[str, ModelProfile]) -> None:
    """Save profiles to model_profiles.json."""
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {name: profile.to_dict() for name, profile in profiles.items()}
    PROFILES_PATH.write_text(json.dumps(data, indent=2))
    log.info(f"Saved profiles to {PROFILES_PATH}")


# ── CLI ──────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark models for autoresearch routing decisions.",
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Single model to benchmark (e.g., qwen-7b, claude-opus)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Benchmark all configured models",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        nargs="+",
        default=DEFAULT_BATCH_SIZES,
        help="Batch sizes to benchmark (default: 1 50)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Max output tokens per run (default: {DEFAULT_MAX_TOKENS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be benchmarked, don't run",
    )

    args = parser.parse_args()

    if not args.model and not args.all:
        parser.print_help()
        sys.exit(1)

    # Define models to benchmark
    models_to_run: list[tuple[str, str]] = []

    if args.all:
        # Detect what's installed and benchmarkable
        models_to_run = [
            ("Qwen2.5-7B-Instruct", "airllm"),  # Local via AirLLM
            ("claude-opus", "anthropic"),  # Frontier via Anthropic
        ]
    elif args.model:
        # Single model: guess backend from name
        model_lower = args.model.lower()
        if "qwen" in model_lower or "llama" in model_lower:
            backend = "airllm"
        elif "claude" in model_lower:
            backend = "anthropic"
        else:
            backend = "airllm"  # default
        models_to_run = [(args.model, backend)]

    # Load existing profiles
    profiles = load_profiles()

    # Run benchmarks
    runs: list[BenchmarkRun] = []
    for model_name, backend in models_to_run:
        log.info(f"Benchmarking {model_name} ({backend})...")

        if args.dry_run:
            for batch_size in args.batch_size:
                log.info(f"  Would benchmark batch_size={batch_size}")
            continue

        benchmark = ModelBenchmark(model_name, backend)
        for batch_size in args.batch_size:
            log.info(f"  Running batch_size={batch_size}...")
            run = benchmark.benchmark(batch_size, args.max_tokens)
            if run:
                runs.append(run)
                log.info(
                    f"    {run.output_tokens} tokens in {run.total_latency_ms:.1f}ms "
                    f"= {run.tokens_per_sec:.2f} tok/s"
                )

    # Update profiles from runs
    for run in runs:
        profile_key = f"{run.model}_{run.backend}"
        if profile_key not in profiles:
            # Guess arch from model name
            arch = "qwen" if "qwen" in run.model.lower() else "llama"
            profiles[profile_key] = ModelProfile(
                model=run.model,
                arch=arch,
                backend=run.backend,
            )

        profile = profiles[profile_key]
        profile.last_benchmarked = run.ts

        # Store TPS by batch size
        if run.batch_size == 1:
            profile.single_prompt_tps = run.tokens_per_sec
        elif run.batch_size == 50:
            profile.batched_tps = run.tokens_per_sec

    if runs and not args.dry_run:
        save_profiles(profiles)
        log.info(f"Benchmarked {len(runs)} configurations")
        for run in runs:
            log.info(f"  {run.model} ({run.backend}) batch={run.batch_size}: {run.tokens_per_sec:.2f} tok/s")


if __name__ == "__main__":
    main()
