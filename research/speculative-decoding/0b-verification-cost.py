#!/usr/bin/env python3
"""
Experiment 0b: Verification Cost — Is Multi-Token Verification Cheaper?

The fundamental question for AeroLLM:
=====================================
In standard GPU serving, verifying K draft tokens costs ~1 forward pass
(all K tokens processed in parallel via prefill). This is why speculative
decoding gives K× speedup per verification round.

But AeroLLM streams layers from NVMe. The bottleneck is DISK I/O, not compute.
The question becomes: if we load a layer's weights once, can we run K tokens
through it faster than loading the weights K separate times?

Three scenarios we're measuring:
================================
1. STANDARD DECODE: Generate N tokens one at a time (N forward passes)
2. PREFILL: Process N tokens in one forward pass (batch along sequence dim)
3. SPECULATIVE VERIFY: Process K draft tokens + context in one forward pass,
   then compare — simulating what a speculative verification round looks like

If prefill of K tokens ≈ 1 standard decode step, speculative decoding works.
If prefill of K tokens ≈ K standard decode steps, it doesn't help.

On unified memory (Apple Silicon), we expect prefill to be MUCH faster than
K sequential decodes because:
- Weights loaded once from memory, reused for K positions
- Attention computation parallelizes across the K positions
- The memory bandwidth cost is dominated by weight loading, not activation compute

This directly simulates what happens inside AeroLLM when:
- PrefetchWorker loads a layer's weights from NVMe (T_load: fixed)
- apply_block() runs the forward pass (T_compute: scales with tokens)
- The ratio T_compute(K) / T_compute(1) determines if speculation helps

Usage:
    python 0b-verification-cost.py [--model MODEL] [--tokens 1,4,6,8,12,20]
"""

import argparse
import json
import time
from pathlib import Path

import mlx.core as mx


def measure_decode_latency(model, tokenizer, prompt: str, n_tokens: int, n_trials: int = 5) -> dict:
    """Measure wall-clock time for standard autoregressive decode of n_tokens.

    Each token requires a separate forward pass (single-token input, KV cache
    extends by 1 each step). This is the baseline that speculative decoding
    must beat.
    """
    input_ids = mx.array([tokenizer.encode(prompt)])
    times = []

    for trial in range(n_trials):
        mx.eval(input_ids)  # ensure input is materialized

        # Warm up: one forward pass to populate caches
        _ = model(input_ids)
        mx.eval(_)

        context = input_ids
        start = time.perf_counter()
        for _ in range(n_tokens):
            logits = model(context)
            mx.eval(logits)
            next_token = mx.argmax(logits[:, -1, :], axis=-1, keepdims=True)
            mx.eval(next_token)
            context = mx.concatenate([context, next_token], axis=1)
        elapsed = time.perf_counter() - start
        times.append(elapsed)

    return {
        "mode": "sequential_decode",
        "n_tokens": n_tokens,
        "times": times,
        "mean_sec": sum(times) / len(times),
        "per_token_sec": (sum(times) / len(times)) / n_tokens,
    }


def measure_prefill_latency(model, tokenizer, prompt: str, n_tokens: int, n_trials: int = 5) -> dict:
    """Measure wall-clock time for prefilling n_tokens in a single forward pass.

    This simulates speculative verification: the draft model has already
    proposed n_tokens, and now the target model processes all of them at once
    to get logits for each position. One forward pass, one weight-loading cycle.

    If this is much faster than n sequential decodes, speculative decoding
    is viable for AeroLLM.
    """
    # Create a context that includes n_tokens of "draft" content
    # (we use real tokens from encoding a longer prompt to be realistic)
    base_ids = tokenizer.encode(prompt)
    # Extend with repeated tokens to simulate draft tokens
    # In practice these would be draft model outputs
    extended = base_ids + base_ids[:n_tokens]  # append n_tokens as "draft"
    input_ids = mx.array([extended])

    times = []
    for trial in range(n_trials):
        mx.eval(input_ids)

        # Warm up
        _ = model(input_ids)
        mx.eval(_)

        start = time.perf_counter()
        logits = model(input_ids)
        mx.eval(logits)
        elapsed = time.perf_counter() - start
        times.append(elapsed)

    return {
        "mode": "prefill_batch",
        "n_tokens": n_tokens,
        "total_input_length": len(extended),
        "times": times,
        "mean_sec": sum(times) / len(times),
    }


def measure_speculative_simulation(
    model, tokenizer, prompt: str, k: int, n_trials: int = 5
) -> dict:
    """Simulate a full speculative decoding verification round.

    This measures the realistic cost of:
    1. Feeding [context + K draft tokens] as one input
    2. Getting logits for all positions
    3. Extracting and comparing logits at the K draft positions
    4. Sampling the bonus token

    Steps 3-4 are pure CPU/array ops (fast). Step 1-2 is the expensive part.
    """
    base_ids = tokenizer.encode(prompt)
    draft_tokens = base_ids[:k]  # simulate draft tokens
    full_input = base_ids + draft_tokens
    input_ids = mx.array([full_input])

    times = []
    for trial in range(n_trials):
        mx.eval(input_ids)

        # Warm up
        _ = model(input_ids)
        mx.eval(_)

        start = time.perf_counter()

        # Step 1-2: Forward pass with all tokens
        logits = model(input_ids)
        mx.eval(logits)

        # Step 3: Extract logits at draft positions and compute acceptance
        # (this is what rejection sampling does)
        draft_start = len(base_ids) - 1  # -1 because logits[i] predicts token[i+1]
        draft_logits = logits[:, draft_start:draft_start + k, :]
        draft_probs = mx.softmax(draft_logits, axis=-1)
        greedy_tokens = mx.argmax(draft_probs, axis=-1)
        mx.eval(greedy_tokens)

        # Step 4: "Bonus token" — argmax of last position
        bonus_logits = logits[:, -1, :]
        bonus_token = mx.argmax(bonus_logits, axis=-1)
        mx.eval(bonus_token)

        elapsed = time.perf_counter() - start
        times.append(elapsed)

    return {
        "mode": "speculative_verify",
        "k": k,
        "context_length": len(base_ids),
        "total_input_length": len(full_input),
        "times": times,
        "mean_sec": sum(times) / len(times),
    }


def run_experiment(
    model_name: str = "mlx-community/Qwen2.5-7B-Instruct-4bit",
    token_counts: list[int] = None,
    n_trials: int = 5,
    output_path: str = "results/0b-verification-cost.json",
):
    """Run the verification cost experiment."""
    import mlx_lm

    if token_counts is None:
        token_counts = [1, 4, 6, 8, 12, 20]

    print(f"Loading model: {model_name}")
    model, tokenizer = mlx_lm.load(model_name)

    prompt = ("Explain how the Linux kernel's Completely Fair Scheduler uses "
              "a red-black tree to manage task scheduling. The CFS maintains "
              "a timeline of task execution using virtual runtime values.")

    results = {"sequential": [], "prefill": [], "speculative": []}

    # ── Sequential decode baseline ──────────────────────────────────────
    print("\n1. Sequential decode (baseline)")
    for n in token_counts:
        print(f"   n_tokens={n} ...", end=" ", flush=True)
        r = measure_decode_latency(model, tokenizer, prompt, n, n_trials)
        results["sequential"].append(r)
        print(f"mean={r['mean_sec']:.4f}s  per_token={r['per_token_sec']:.4f}s")

    # ── Prefill (batch verification) ────────────────────────────────────
    print("\n2. Prefill (simulated batch verification)")
    for n in token_counts:
        print(f"   n_tokens={n} ...", end=" ", flush=True)
        r = measure_prefill_latency(model, tokenizer, prompt, n, n_trials)
        results["prefill"].append(r)
        print(f"mean={r['mean_sec']:.4f}s")

    # ── Speculative verification simulation ─────────────────────────────
    print("\n3. Speculative verification simulation")
    for k in token_counts:
        print(f"   K={k} ...", end=" ", flush=True)
        r = measure_speculative_simulation(model, tokenizer, prompt, k, n_trials)
        results["speculative"].append(r)
        print(f"mean={r['mean_sec']:.4f}s")

    # ── Analysis ────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("ANALYSIS: Verification Cost Ratio")
    print("="*60)
    print("\nIf ratio < 1.0: speculative verification is CHEAPER than sequential decode")
    print("If ratio ≈ 1.0: no benefit (verification costs the same)")
    print("If ratio > 1.0: verification is MORE expensive (shouldn't happen)\n")

    print(f"{'K':>4s}  {'Sequential':>12s}  {'Spec Verify':>12s}  {'Ratio':>8s}  {'Effective Speedup':>18s}")
    print("-" * 60)

    for i, k in enumerate(token_counts):
        seq_time = results["sequential"][i]["mean_sec"]
        spec_time = results["speculative"][i]["mean_sec"]
        ratio = spec_time / seq_time if seq_time > 0 else float("inf")

        # Effective speedup: K tokens in spec_time vs K tokens in seq_time
        speedup = seq_time / spec_time if spec_time > 0 else 0
        print(f"{k:4d}  {seq_time:12.4f}s  {spec_time:12.4f}s  {ratio:8.3f}  {speedup:15.2f}x")

    print("\n" + "="*60)
    print("KEY INSIGHT FOR AEROLLM")
    print("="*60)

    # Compare K=6 (our expected operating point)
    if 6 in token_counts:
        idx = token_counts.index(6)
        seq = results["sequential"][idx]["mean_sec"]
        spec = results["speculative"][idx]["mean_sec"]
        ratio = spec / seq

        if ratio < 0.5:
            print(f"\nAt K=6: verification takes {ratio:.1%} of sequential time.")
            print("STRONG WIN: Speculative decoding is highly viable for AeroLLM.")
            print("Each layer load produces ~6x more useful tokens.")
        elif ratio < 0.8:
            print(f"\nAt K=6: verification takes {ratio:.1%} of sequential time.")
            print("MODERATE WIN: Speculative decoding helps, but less than theory predicts.")
            print("Memory bandwidth may be limiting parallelism.")
        else:
            print(f"\nAt K=6: verification takes {ratio:.1%} of sequential time.")
            print("MARGINAL: Verification isn't much cheaper than sequential decode.")
            print("On disk-streamed models, the story may differ (fixed I/O cost).")

    # ── Save ────────────────────────────────────────────────────────────
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "experiment": "0b-verification-cost",
        "model": model_name,
        "prompt_length_tokens": len(tokenizer.encode(prompt)),
        "token_counts_tested": token_counts,
        "n_trials": n_trials,
        "results": results,
    }

    with open(output, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nResults saved to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Speculative decoding verification cost experiment")
    parser.add_argument("--model", default="mlx-community/Qwen2.5-7B-Instruct-4bit")
    parser.add_argument("--tokens", default="1,4,6,8,12,20", help="Token counts to test")
    parser.add_argument("--trials", type=int, default=5, help="Trials per measurement")
    parser.add_argument("--output", default="results/0b-verification-cost.json")
    args = parser.parse_args()

    run_experiment(
        model_name=args.model,
        token_counts=[int(x) for x in args.tokens.split(",")],
        n_trials=args.trials,
        output_path=args.output,
    )
