---
title: Fact-checking a Claim
id: fact-check-claim
name: fact-check-claim
domain: curation
version: 1.0.0
tags: [skill, curation, verification, evidence]
when_to_use:
  - When a claim from a source could shift the lab's research direction
  - When someone reports a benchmark number you'd cite in a report
  - When a "common knowledge" assertion turns out to be load-bearing
when_not_to_use:
  - For claims clearly marked as opinion
  - For internal lab observations (run them again instead of fact-checking them)
---

# Fact-checking a Claim

The triangulation rule: **a claim is verified when three independent
sources agree.** Independence is the hard part.

## What "independent" means

Two sources are NOT independent when:

- They cite each other.
- They share an author or institution.
- They reproduce the same dataset and report the same numbers.
- One is a press release and the other is the company blog
  reporting on the press release.

Two sources ARE independent when:

- Different authors, different orgs, different methodology, same
  conclusion.
- One is the original measurement; the other is a third party who
  re-ran it on different hardware.
- One is the paper; the other is an angry blog post explaining
  why the paper is wrong AND the disagreement narrows the claim
  rather than overturning it.

## The triangulation procedure

1. Write the exact claim you're checking, in one sentence. If you
   can't write it tightly, the claim is too fuzzy to verify.
2. Find the **primary source** — the original paper / repo / dataset.
3. Find a **second independent source** that confirms the claim.
4. Find a **third independent source**. Stop when you have three OR
   when you've spent 30 minutes (whichever first).
5. If you have three: mark the claim "verified-3x" in the KB.
6. If you have two: mark "verified-2x — single-domain risk" so
   future you remembers it could still be wrong if you only
   triangulated within one community.
7. If you have one: don't quote it as fact; quote it as "according
   to <source>".

## Edge case: the only source is the original

Some genuinely new findings live in exactly one paper for a long
time before being reproduced. That's fine — just label it.

```markdown
**Verification:** primary source only (no independent reproduction
as of <date>). Track for follow-up.
```

If the lab's plan depends on the unverified claim being true,
that's the next thing the Researcher should try to reproduce —
add it to `program.md`'s hypotheses list.

## What to write in the KB

When you've fact-checked something, leave the trail:

```markdown
**Claim:** AirLLM achieves 3 tok/s for Llama-70B on 8GB VRAM.
**Verified:** ✓ 3x
- Primary: github.com/lyogavin/airllm README (2024-09)
- Independent: <name>'s blog post benchmarking on M1 (2024-11)
- Independent: discussion on r/LocalLLaMA with reproductions
**Caveat:** all three measure decode speed only, not TTFT.
```

The caveat line is the most useful. Three sources agreeing on a
narrow definition of the claim is signal. Three sources hand-waving
is noise.
