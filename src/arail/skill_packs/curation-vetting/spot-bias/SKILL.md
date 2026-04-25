---
title: Spotting Bias in Research
id: spot-bias
name: spot-bias
domain: curation
version: 1.0.0
tags: [skill, curation, bias, methodology]
when_to_use:
  - When summarizing a paper or blog post for the KB
  - When a benchmark result is the load-bearing input to a decision
  - When a finding could change what the lab tries next
when_not_to_use:
  - For uncontroversial procedural docs (how to install a package)
  - For your own observations from local runs (label those as such)
---

# Spotting Bias in Research

Bias rarely announces itself. These are the patterns that show up
most often in AI/ML research, ranked by how often the lab
encounters them.

## 1. Cherry-picked baselines

The author benchmarks against a deliberately weak baseline so their
method "wins by 5×." Tell from:

- Baseline is named but not configured (no version, no flags, no
  hardware).
- Baseline performance is well below what other papers report for
  the same task on similar hardware.
- The "ablation study" only ablates choices that obviously help.

**Red flag phrase:** "compared to standard X, our method achieves Y"
with no link to a reproducible baseline.

## 2. Goalpost drift between abstract and method

Abstract: "We achieve 50% better throughput."
Methods: "On a 13B model with sequence length 512 and batch size 1
when streaming the same prompt 100 times in a row."

The headline number is technically true and operationally useless.
Read the methodology section before quoting the abstract.

## 3. Selection bias in evaluation set

Best-of-N sampling without disclosing the discarded N. Filtering the
eval set down to "the prompts the method handles well." Re-running
with different seeds until one looks good.

**Tell:** the paper reports a single number with no variance bars,
no min/max, no run-count.

## 4. Vendor-flavored conclusions

Big-corp papers tend to land on "scale solves it." Open-source
papers tend to land on "the small clever trick wins." Both can be
right; both are pre-loaded with what the team WANTED to be true
before measurement started.

When the conclusion conveniently aligns with the author's
commercial interest, weight the evidence harder, not the conclusion.

## 5. Survivorship bias in case studies

"We deployed X in production and it worked great." What about the
five teams that tried X and reverted? They don't write blog posts.

Treat single-team success stories as existence proofs, not
recommendations. Look for the matching "we tried X and it didn't
work for us" post — its absence is data.

## What to write in the KB

When you import a source with detected bias, add a brief note in
the SOURCE.md:

```markdown
**Bias notes:**
- Baseline missing version info (likely outdated comparison)
- Single-team result, no independent reproduction
```

Future readers (you, in two months) will thank you.
