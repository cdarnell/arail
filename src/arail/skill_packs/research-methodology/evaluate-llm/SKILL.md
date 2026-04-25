---
title: Evaluate a local LLM
id: evaluate-llm
name: Evaluate LLM
domain: ai
version: 1.0.0
tags: [skill, evaluation, benchmarking, ai]
when_to_use:
  - When the goal is model selection or tuning
  - When a new model arrives and we want to know if it's better
  - When reporting results to the knowledge base
when_not_to_use:
  - For one-off "does this work?" smoke tests (no need for full rigor)
  - For subjective style tasks — use blind human rating instead
---

# Evaluate a local LLM

Procedural knowledge for benchmarking a language model that runs on
the lab's hardware. Produces comparable, reproducible numbers rather
than impressions.

## The minimum viable benchmark

Three measurements, in order of importance:

1. **Validation loss on held-out data.** Lower is better. Use the
   validation split defined in the current ``prepare.py`` — never
   the training data, never a sampled subset of it.
2. **Tokens-per-second at your typical prompt length.** Inference
   speed on the actual hardware, not the advertised number.
3. **Peak memory during inference.** Tells you how much headroom is
   left for longer contexts or bigger batches.

Skip BLEU / ROUGE / perplexity unless the goal explicitly calls for
them. They're noise for most local-lab questions.

## Ground rules

- **Fix the seed.** Every eval run uses the same random seed so
  sampling variance doesn't masquerade as capability difference.
- **Compare apples to apples.** Same prompt template, same max
  tokens, same temperature (always 0.0 for evals — sampling kills
  reproducibility).
- **Report three runs.** Single-run numbers lie. Report median and
  range.
- **Mark the hardware.** "Qwen3-8B on M2 Max, 32 GB" — without it
  the number means nothing to anyone else.

## What to write to the knowledge base

After an eval, drop a markdown file in ``lab/pkb/agents/research/``
following this shape:

```
# Eval: <model-name> on <task>

- Date: YYYY-MM-DD
- Hardware: <platform + RAM>
- Prompt count: N
- Temperature: 0.0
- Seed: <fixed>

## Results

| Metric | Value |
|---|---|
| Validation loss | 1.234 |
| Tokens/sec (median) | 62 |
| Peak RAM (GB) | 14.2 |

## Observations

<one paragraph of plain-English notes>
```

## When the numbers disagree with intuition

Trust the numbers. But dig:

- Did the prompt format match what the model was trained on?
- Is the validation set representative of what the user actually
  does with this model?
- Is tokenization different between models being compared?

If all three check out and the numbers still disagree with feel,
write both down. Note the contradiction explicitly. Future runs
will reveal which one was right.
