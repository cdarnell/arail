# ai-eng v2.1 bench
<!-- TEMPLATE — populated by scripts/bench_ai_eng.py on run. Do not edit by hand. -->
**Date:** YYYY-MM-DD  **Host:** &lt;hostname&gt; (&lt;chip&gt;, &lt;RAM&gt; GB)
**Adapter SHA:** &lt;sha&gt;  **Seed:** 42

## Summary
- Winner: &lt;A | B | abort&gt;
- Gate confidence: low (n=50 MMLU; tech-debt ticket TD-v2.2-bench-n)
- Bench script exit code: &lt;0=ship-B | 1=ship-A | 2=abort-both&gt;

## Numbers
| Model | MMLU(50) | Perplexity | AI-eng head-to-head (out of 5) | Latency p50 (ms) |
|---|---|---|---|---|
| Qwen2.5-3B-Instruct (baseline) | … | … | n/a | … |
| Candidate A (MLX 4-bit fused) | … | … | … | … |
| Candidate B (bf16 merged)     | … | … | … | … |
| qwen2.5:7b + persona (incumbent) | … | … | reference | … |

> **Statistical caveat:** with n=50 MMLU questions the 95% CI half-width is
> ±13–14pp. The 3pp regression gate is a vibe gate for large regressions only.
> See TD-v2.2-bench-n for the plan to raise n≥200.

## Gate logic applied
<!-- bench_ai_eng.py fills this section with the decision rationale. -->
&lt;Decision rationale: which gate fired and why&gt;

## Per-prompt outputs (verbatim)
<!-- bench_ai_eng.py appends one sub-section per prompt from bench-prompts.v2.1.yaml. -->

### ae-01-lora-tradeoffs
**Candidate A:** &lt;output&gt;
**Candidate B:** &lt;output&gt;
**qwen2.5:7b:** &lt;output&gt;

### ae-02-rope-scaling
**Candidate A:** &lt;output&gt;
**Candidate B:** &lt;output&gt;
**qwen2.5:7b:** &lt;output&gt;

### ae-03-kvcache-memory
**Candidate A:** &lt;output&gt;
**Candidate B:** &lt;output&gt;
**qwen2.5:7b:** &lt;output&gt;

### ae-04-quant-tradeoffs
**Candidate A:** &lt;output&gt;
**Candidate B:** &lt;output&gt;
**qwen2.5:7b:** &lt;output&gt;

### cg-01-lora-loader
**Candidate A:** &lt;output&gt;
**Candidate B:** &lt;output&gt;
**qwen2.5:7b:** &lt;output&gt;

### cg-02-token-budget
**Candidate A:** &lt;output&gt;
**Candidate B:** &lt;output&gt;
**qwen2.5:7b:** &lt;output&gt;

### cg-03-perplexity
**Candidate A:** &lt;output&gt;
**Candidate B:** &lt;output&gt;
**qwen2.5:7b:** &lt;output&gt;

### hn-01-obscure-paper
**Candidate A:** &lt;output&gt;
**Candidate B:** &lt;output&gt;
**qwen2.5:7b:** &lt;output&gt;

### hn-02-nonexistent-technique
**Candidate A:** &lt;output&gt;
**Candidate B:** &lt;output&gt;
**qwen2.5:7b:** &lt;output&gt;

### mt-01-context-retention
**Candidate A:** &lt;output&gt;
**Candidate B:** &lt;output&gt;
**qwen2.5:7b:** &lt;output&gt;

### mt-02-debugging-session
**Candidate A:** &lt;output&gt;
**Candidate B:** &lt;output&gt;
**qwen2.5:7b:** &lt;output&gt;

### am-01-underspecified-request
**Candidate A:** &lt;output&gt;
**Candidate B:** &lt;output&gt;
**qwen2.5:7b:** &lt;output&gt;

## Decision rationale
<!-- Filled by bench_ai_eng.py. -->
&lt;Narrative explanation of winner selection, gate thresholds, and any flags raised.&gt;
