#!/usr/bin/env python3
"""
Experiment 0a: Speculative Decoding Acceptance Rate Measurement

Measures how well a small draft model predicts a larger target model's outputs
on domain-specific content. This is the GO/NO-GO gate for the entire speculative
decoding integration.

The Core Algorithm (Leviathan et al., 2022):
============================================
1. Draft model proposes K tokens autoregressively (cheap)
2. Target model scores all K tokens in one forward pass (expensive but batched)
3. For each draft token x_i with draft probability q(x_i) and target probability p(x_i):
   - Accept with probability min(1, p(x_i) / q(x_i))
   - If rejected: sample replacement from residual distribution norm(max(0, p - q))
   - All subsequent draft tokens after the first rejection are discarded
4. After the accepted prefix, sample one bonus token from the target's distribution

This guarantees the output distribution is IDENTICAL to standard autoregressive
sampling from the target model. It's not an approximation — it's mathematically exact.

Why acceptance rate matters:
============================
- At acceptance rate α with draft length K, mean accepted tokens ≈ α·K / (1-α)
  (geometric distribution, simplified)
- More precisely: E[accepted] = (1 - α^(K+1)) / (1 - α) - 1
- Each accepted token is "free" — it didn't require a separate target forward pass
- For AeroLLM: each accepted token avoided a 56-second layer-streaming pass

Usage:
    python 0a-acceptance-rate.py [--draft-model MODEL] [--target-model MODEL] [--k 4,6,8,12]
"""

import argparse
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ── Domain-specific prompts (Linux kernel) ──────────────────────────────────
# These simulate the kind of prompts the TICE Corpus Phase 1a will produce.
# The adversarial swarm (Interrogator agent) generates probing questions like these.

DOMAIN_PROMPTS = [
    # Scheduling subsystem
    "Explain how the Completely Fair Scheduler (CFS) in the Linux kernel uses a red-black tree to manage task scheduling. What is the role of vruntime?",
    "What happens in the Linux kernel when a real-time SCHED_FIFO task preempts a CFS task? Walk through the scheduler code path.",
    "Describe the difference between voluntary and involuntary context switches in the Linux kernel. When does each occur?",
    "How does the Linux kernel's load balancer distribute tasks across CPU cores in a NUMA topology?",
    "Explain the purpose of the sched_entity structure and how it relates to task_struct in the kernel scheduler.",

    # Memory management
    "Walk through the Linux kernel's page fault handler for an anonymous memory mapping. What happens at each stage?",
    "Explain how the kernel's slab allocator (SLUB) manages small memory allocations. What is a slab cache?",
    "What is the OOM killer in the Linux kernel? How does it decide which process to terminate?",
    "Describe the role of struct page and struct folio in the kernel's memory management subsystem.",
    "How does transparent huge pages (THP) work in the Linux kernel? What are the tradeoffs?",

    # Filesystems and I/O
    "Explain the Linux kernel's VFS (Virtual File System) layer. How does it abstract different filesystem implementations?",
    "Walk through what happens in the kernel when a process calls read() on an ext4 file. Include the page cache path.",
    "How does the Linux kernel's I/O scheduler (mq-deadline or BFQ) prioritize block I/O requests?",
    "Explain the role of struct inode and struct dentry in the Linux VFS. How are they cached?",
    "What is direct I/O in the Linux kernel and when would you use it instead of buffered I/O?",

    # Networking
    "Describe the path of a TCP packet through the Linux kernel's network stack, from NIC driver to socket buffer.",
    "How does the Linux kernel's netfilter framework process packets? Explain the hook points.",
    "What is eBPF and how does the Linux kernel verify BPF programs before executing them?",
    "Explain the difference between NAPI and interrupt-driven packet processing in Linux network drivers.",
    "How does the kernel's TCP congestion control work? Compare CUBIC and BBR.",

    # Device drivers and hardware
    "Explain the Linux kernel's device model: struct device, struct device_driver, and the bus abstraction.",
    "How does a PCI device driver register itself with the kernel? Walk through probe() and the matching process.",
    "What is DMA (Direct Memory Access) in the Linux kernel and how does the IOMMU interact with it?",
    "Explain how the Linux kernel handles interrupts: top-half vs bottom-half, hardirq vs softirq vs tasklet.",
    "How does the kernel's power management framework handle device suspend and resume?",

    # Security and namespaces
    "Explain how Linux namespaces provide process isolation. What are the different namespace types?",
    "How does the Linux kernel's capability system work? What replaced the traditional root/non-root model?",
    "Walk through how seccomp-BPF filters system calls in the Linux kernel.",
    "Explain the role of SELinux's MAC (Mandatory Access Control) in the kernel's security framework.",
    "How does the kernel's cgroup v2 hierarchy manage resource limits for container workloads?",

    # Synchronization and concurrency
    "Explain the difference between spinlocks, mutexes, and RCU in the Linux kernel. When do you use each?",
    "What is RCU (Read-Copy-Update) in the Linux kernel? Walk through a read-side and write-side example.",
    "How does the kernel's lockdep validator detect potential deadlocks at runtime?",
    "Explain the role of memory barriers (smp_mb, smp_rmb, smp_wmb) in the Linux kernel's concurrency model.",
    "What is per-CPU data in the Linux kernel and why is it important for scalability?",

    # Kernel internals
    "How does the Linux kernel's module loading system work? Walk through insmod to init_module.",
    "Explain the kernel's printk and the structured logging infrastructure. How does it differ from userspace logging?",
    "What is the kernel's workqueue subsystem and how does it differ from kernel threads?",
    "How does the kernel's timer subsystem (hrtimers) work on modern hardware with TSC and HPET?",
    "Explain the boot process of the Linux kernel from the bootloader handoff to the first userspace process.",

    # Advanced/edge cases (Adversary agent style)
    "What happens if a kernel module tries to sleep while holding a spinlock? How does the kernel detect this?",
    "Explain the thundering herd problem in the Linux kernel's epoll implementation and how it was solved.",
    "How does the kernel handle a fork bomb? What resource limits prevent it?",
    "What is priority inversion in the Linux kernel and how does the RT mutex solve it with priority inheritance?",
    "Explain the KASAN (Kernel Address Sanitizer) memory error detector. How does it instrument memory accesses?",
]

# General-purpose prompts (control group)
GENERAL_PROMPTS = [
    "Write a Python function that implements binary search on a sorted array.",
    "Explain the difference between TCP and UDP protocols.",
    "What are the SOLID principles in object-oriented programming?",
    "Describe how a hash table works, including collision resolution strategies.",
    "Explain the CAP theorem in distributed systems.",
    "Write a SQL query to find the second highest salary from an employees table.",
    "What is the difference between a process and a thread?",
    "Explain how garbage collection works in Java.",
    "Describe the Model-View-Controller (MVC) architectural pattern.",
    "What is a closure in JavaScript and why is it useful?",
    "Explain the difference between symmetric and asymmetric encryption.",
    "How does a B-tree index work in a database?",
    "What is eventual consistency and when would you choose it over strong consistency?",
    "Explain the publish-subscribe messaging pattern.",
    "Describe how DNS resolution works step by step.",
    "What is a memory leak and how would you detect one?",
    "Explain the difference between REST and GraphQL APIs.",
    "How does HTTPS establish a secure connection (TLS handshake)?",
    "What is a bloom filter and what are its use cases?",
    "Explain the difference between horizontal and vertical scaling.",
    "Describe the producer-consumer problem and a solution using semaphores.",
    "What is cache invalidation and why is it considered a hard problem?",
    "Explain how a load balancer distributes traffic across servers.",
    "What is the difference between optimistic and pessimistic locking?",
    "Describe the circuit breaker pattern in microservices.",
    "How does a CDN (Content Delivery Network) improve performance?",
    "What is the difference between a stack and a queue? Give use cases for each.",
    "Explain the MapReduce programming model.",
    "What is database sharding and what are its tradeoffs?",
    "Describe how WebSocket connections differ from HTTP connections.",
    "Explain the concept of backpressure in streaming systems.",
    "What is the difference between unit tests, integration tests, and end-to-end tests?",
    "How does a write-ahead log (WAL) ensure database durability?",
    "Explain the difference between concurrency and parallelism.",
    "What is tail-call optimization and which languages support it?",
    "Describe how consistent hashing works for distributed caching.",
    "What is the difference between a monorepo and a polyrepo?",
    "Explain the actor model of concurrency.",
    "How does a garbage collector's generational hypothesis improve performance?",
    "What is the difference between a forward proxy and a reverse proxy?",
    "Describe the event loop in Node.js.",
    "What is CQRS (Command Query Responsibility Segregation)?",
    "Explain how virtual memory works at the hardware level.",
    "What is a trie data structure and when would you use one?",
    "Describe the saga pattern for distributed transactions.",
    "How does a compiler's lexer differ from its parser?",
    "What is the difference between mutable and immutable data structures?",
    "Explain the concept of back-of-the-envelope estimation in system design.",
    "How does rate limiting work and what algorithms are commonly used?",
    "What is the difference between a soft delete and a hard delete?",
]


@dataclass
class TokenResult:
    """Result of evaluating one draft token against the target."""
    position: int
    draft_token: int
    target_token: int
    draft_prob: float       # q(x) — draft model's probability for this token
    target_prob: float      # p(x) — target model's probability for this token
    acceptance_prob: float  # min(1, p(x)/q(x))
    accepted: bool          # whether the coin flip accepted this token


@dataclass
class RoundResult:
    """Result of one speculative decoding round (K draft tokens → verify)."""
    draft_length: int           # K
    accepted_count: int         # how many consecutive tokens accepted
    bonus_token: int | None     # the correction token from the target
    tokens: list[TokenResult] = field(default_factory=list)

    @property
    def acceptance_rate(self) -> float:
        """Fraction of draft tokens accepted."""
        if self.draft_length == 0:
            return 0.0
        return self.accepted_count / self.draft_length


@dataclass
class PromptResult:
    """Result of running speculative decoding on one prompt."""
    prompt: str
    prompt_category: str        # "domain" or "general"
    draft_length_k: int
    rounds: list[RoundResult] = field(default_factory=list)
    total_time_sec: float = 0.0

    @property
    def mean_accepted(self) -> float:
        if not self.rounds:
            return 0.0
        return sum(r.accepted_count for r in self.rounds) / len(self.rounds)

    @property
    def mean_acceptance_rate(self) -> float:
        if not self.rounds:
            return 0.0
        return sum(r.acceptance_rate for r in self.rounds) / len(self.rounds)

    @property
    def total_tokens_generated(self) -> int:
        """Total tokens: accepted draft tokens + bonus tokens."""
        return sum(r.accepted_count + (1 if r.bonus_token is not None else 0)
                   for r in self.rounds)

    @property
    def speedup_estimate(self) -> float:
        """Estimated speedup over standard decoding.

        In standard decoding, each token costs one forward pass.
        In speculative decoding, each round costs ~1 forward pass (verification)
        plus the cheap draft cost, but produces mean_accepted + 1 tokens.

        Simplified: speedup ≈ (mean_accepted + 1) / (1 + draft_cost_ratio)
        where draft_cost_ratio ≈ 0.05 for a 0.5B draft vs 7B target.
        """
        if not self.rounds:
            return 1.0
        tokens_per_round = self.mean_accepted + 1  # +1 for bonus token
        draft_cost_ratio = 0.05  # approximate: 0.5B is ~7% of 7B compute
        return tokens_per_round / (1 + draft_cost_ratio)


def speculative_decode_round(
    draft_model,
    target_model,
    draft_tokenizer,
    target_tokenizer,
    context_tokens: list[int],
    k: int,
    temperature: float = 0.0,
) -> RoundResult:
    """Run one round of speculative decoding.

    This implements the Leviathan et al. (2022) algorithm:
    1. Draft model generates K tokens autoregressively
    2. Target model scores all K tokens in one forward pass
    3. Accept/reject each token using rejection sampling
    4. Sample bonus token from target at first rejection point

    Args:
        draft_model: The small, fast model (e.g., Qwen2.5-0.5B)
        target_model: The large, accurate model (e.g., Qwen2.5-7B)
        context_tokens: The token sequence so far
        k: Number of tokens to draft
        temperature: Sampling temperature (0.0 = greedy)

    Returns:
        RoundResult with per-token acceptance details
    """
    import mlx.core as mx
    import mlx.nn as nn
    import numpy as np

    tokens = []
    round_result = RoundResult(draft_length=k, accepted_count=0, bonus_token=None)

    # ── Step 1: Draft model generates K tokens autoregressively ─────────
    draft_tokens = []
    draft_logprobs = []  # log q(x_i) for each drafted token
    draft_context = mx.array([context_tokens])

    for i in range(k):
        draft_logits = draft_model(draft_context)
        # Take logits for the last position
        last_logits = draft_logits[:, -1, :]

        if temperature == 0.0:
            draft_token = mx.argmax(last_logits, axis=-1).item()
            # For greedy: probability is 1.0 for the chosen token
            draft_probs = mx.softmax(last_logits, axis=-1)
            draft_prob = draft_probs[0, draft_token].item()
        else:
            draft_probs = mx.softmax(last_logits / temperature, axis=-1)
            draft_token = mx.random.categorical(mx.log(draft_probs)).item()
            draft_prob = draft_probs[0, draft_token].item()

        draft_tokens.append(draft_token)
        draft_logprobs.append(draft_prob)
        # Extend context for next draft token
        draft_context = mx.concatenate([
            draft_context,
            mx.array([[draft_token]])
        ], axis=1)
    mx.eval(draft_context)  # force evaluation

    # ── Step 2: Target model scores all K draft tokens in ONE pass ──────
    # This is the key efficiency: one forward pass, not K separate passes.
    # We feed [context + draft_tokens] and get logits for all positions.
    verify_input = mx.array([context_tokens + draft_tokens])
    target_logits = target_model(verify_input)
    mx.eval(target_logits)

    # ── Step 3: Rejection sampling for each draft token ─────────────────
    accepted_count = 0
    for i in range(k):
        # Target's probability distribution at position where draft token i was generated
        # (that's position len(context) + i - 1 in the target output, because
        # the logits at position j predict token j+1)
        target_pos = len(context_tokens) + i - 1
        target_probs_at_pos = mx.softmax(
            target_logits[:, target_pos, :] / max(temperature, 1e-10),
            axis=-1
        ) if temperature > 0 else mx.softmax(target_logits[:, target_pos, :], axis=-1)

        target_prob = target_probs_at_pos[0, draft_tokens[i]].item()
        draft_prob = draft_logprobs[i]

        # Acceptance probability: min(1, p(x) / q(x))
        if draft_prob > 0:
            accept_ratio = min(1.0, target_prob / draft_prob)
        else:
            accept_ratio = 0.0

        # For greedy (temperature=0): accept if target agrees with draft
        if temperature == 0.0:
            target_greedy = mx.argmax(target_probs_at_pos, axis=-1).item()
            accepted = (draft_tokens[i] == target_greedy)
        else:
            # Stochastic acceptance via coin flip
            coin = np.random.random()
            accepted = coin < accept_ratio

        token_result = TokenResult(
            position=i,
            draft_token=draft_tokens[i],
            target_token=mx.argmax(target_probs_at_pos, axis=-1).item(),
            draft_prob=draft_prob,
            target_prob=target_prob,
            acceptance_prob=accept_ratio,
            accepted=accepted,
        )
        round_result.tokens.append(token_result)

        if accepted:
            accepted_count += 1
        else:
            # First rejection: sample bonus token from residual distribution
            # For greedy: bonus token is simply the target's argmax
            if temperature == 0.0:
                bonus = mx.argmax(target_probs_at_pos, axis=-1).item()
            else:
                # Residual distribution: norm(max(0, p(x) - q(x)))
                draft_dist = mx.softmax(
                    draft_logits[:, -1, :] / temperature, axis=-1
                )  # approximate — ideally we'd cache this
                residual = mx.maximum(
                    target_probs_at_pos - draft_dist,
                    mx.zeros_like(target_probs_at_pos)
                )
                residual = residual / mx.sum(residual)
                bonus = mx.random.categorical(mx.log(residual + 1e-10)).item()

            round_result.bonus_token = bonus
            break
    else:
        # All K tokens accepted! Sample bonus from target's distribution
        # at position after the last draft token
        target_pos = len(context_tokens) + k - 1
        final_probs = mx.softmax(target_logits[:, target_pos, :], axis=-1)
        if temperature == 0.0:
            bonus = mx.argmax(final_probs, axis=-1).item()
        else:
            bonus = mx.random.categorical(mx.log(final_probs)).item()
        round_result.bonus_token = bonus

    round_result.accepted_count = accepted_count
    return round_result


def run_experiment(
    draft_model_name: str = "mlx-community/Qwen2.5-0.5B-Instruct-4bit",
    target_model_name: str = "mlx-community/Qwen2.5-7B-Instruct-4bit",
    k_values: list[int] = None,
    num_rounds_per_prompt: int = 5,
    max_domain_prompts: int = 50,
    max_general_prompts: int = 50,
    temperature: float = 0.0,
    output_path: str = "results/0a-acceptance-rate.json",
):
    """Run the full acceptance rate experiment.

    Loads both models, runs speculative decoding rounds on domain and general
    prompts, measures acceptance rates, and saves results.
    """
    import mlx_lm

    if k_values is None:
        k_values = [4, 6, 8, 12]

    print(f"Loading draft model: {draft_model_name}")
    draft_model, draft_tokenizer = mlx_lm.load(draft_model_name)
    print(f"Loading target model: {target_model_name}")
    target_model, target_tokenizer = mlx_lm.load(target_model_name)

    all_results = []
    domain_prompts = DOMAIN_PROMPTS[:max_domain_prompts]
    general_prompts = GENERAL_PROMPTS[:max_general_prompts]

    for k in k_values:
        print(f"\n{'='*60}")
        print(f"Draft length K={k}")
        print(f"{'='*60}")

        for category, prompts in [("domain", domain_prompts), ("general", general_prompts)]:
            print(f"\n  Category: {category} ({len(prompts)} prompts)")
            for i, prompt in enumerate(prompts):
                start = time.time()
                # Tokenize the prompt
                context = draft_tokenizer.encode(prompt)

                prompt_result = PromptResult(
                    prompt=prompt[:100] + "..." if len(prompt) > 100 else prompt,
                    prompt_category=category,
                    draft_length_k=k,
                )

                for round_idx in range(num_rounds_per_prompt):
                    result = speculative_decode_round(
                        draft_model=draft_model,
                        target_model=target_model,
                        draft_tokenizer=draft_tokenizer,
                        target_tokenizer=target_tokenizer,
                        context_tokens=context,
                        k=k,
                        temperature=temperature,
                    )
                    prompt_result.rounds.append(result)

                    # Advance context with accepted tokens + bonus
                    accepted = [r.draft_token for r in result.tokens[:result.accepted_count]]
                    context = context + accepted
                    if result.bonus_token is not None:
                        context.append(result.bonus_token)

                prompt_result.total_time_sec = time.time() - start
                all_results.append(prompt_result)

                if (i + 1) % 10 == 0:
                    print(f"    [{i+1}/{len(prompts)}] mean_accepted={prompt_result.mean_accepted:.2f} "
                          f"accept_rate={prompt_result.mean_acceptance_rate:.2%} "
                          f"est_speedup={prompt_result.speedup_estimate:.2f}x")

    # ── Summary ─────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("RESULTS SUMMARY")
    print("="*60)

    for k in k_values:
        print(f"\n  K={k}:")
        for category in ["domain", "general"]:
            cat_results = [r for r in all_results
                           if r.draft_length_k == k and r.prompt_category == category]
            if not cat_results:
                continue
            mean_accept = sum(r.mean_accepted for r in cat_results) / len(cat_results)
            mean_rate = sum(r.mean_acceptance_rate for r in cat_results) / len(cat_results)
            mean_speedup = sum(r.speedup_estimate for r in cat_results) / len(cat_results)
            print(f"    {category:8s}: accept_rate={mean_rate:.2%}  "
                  f"mean_accepted={mean_accept:.2f}/{k}  "
                  f"est_speedup={mean_speedup:.2f}x")

    # ── Save results ────────────────────────────────────────────────────
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    serializable = []
    for r in all_results:
        d = {
            "prompt": r.prompt,
            "category": r.prompt_category,
            "k": r.draft_length_k,
            "mean_accepted": r.mean_accepted,
            "mean_acceptance_rate": r.mean_acceptance_rate,
            "speedup_estimate": r.speedup_estimate,
            "total_time_sec": r.total_time_sec,
            "total_tokens": r.total_tokens_generated,
            "rounds": [
                {
                    "accepted_count": rd.accepted_count,
                    "draft_length": rd.draft_length,
                    "acceptance_rate": rd.acceptance_rate,
                }
                for rd in r.rounds
            ],
        }
        serializable.append(d)

    summary = {
        "experiment": "0a-acceptance-rate",
        "draft_model": draft_model_name,
        "target_model": target_model_name,
        "temperature": temperature,
        "k_values": k_values,
        "num_rounds_per_prompt": num_rounds_per_prompt,
        "results": serializable,
    }

    with open(output, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults saved to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Speculative decoding acceptance rate experiment")
    parser.add_argument("--draft-model", default="mlx-community/Qwen2.5-0.5B-Instruct-4bit")
    parser.add_argument("--target-model", default="mlx-community/Qwen2.5-7B-Instruct-4bit")
    parser.add_argument("--k", default="4,6,8,12", help="Comma-separated draft lengths to test")
    parser.add_argument("--rounds", type=int, default=5, help="Decoding rounds per prompt")
    parser.add_argument("--max-prompts", type=int, default=50, help="Max prompts per category")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--output", default="results/0a-acceptance-rate.json")
    args = parser.parse_args()

    run_experiment(
        draft_model_name=args.draft_model,
        target_model_name=args.target_model,
        k_values=[int(x) for x in args.k.split(",")],
        num_rounds_per_prompt=args.rounds,
        max_domain_prompts=args.max_prompts,
        max_general_prompts=args.max_prompts,
        temperature=args.temperature,
        output_path=args.output,
    )
