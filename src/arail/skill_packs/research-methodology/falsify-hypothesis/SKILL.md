---
title: Falsify a hypothesis
id: falsify-hypothesis
name: Falsify Hypothesis
domain: research
version: 1.0.0
tags: [skill, methodology, critical-thinking, research]
when_to_use:
  - After forming any hypothesis — before designing an experiment
  - When analyzing results that "confirm" what you expected
  - When experiment verdicts are all coming back the same
when_not_to_use:
  - For exploratory work where you don't have a hypothesis yet
  - When the hypothesis is already falsifiable by design
---

# Falsify a hypothesis

Procedural knowledge for reducing confirmation bias in the
researcher agent. A hypothesis that can't be falsified isn't a
hypothesis — it's a belief.

## The three-question check

Before designing an experiment, ask:

1. **What observation would change my mind?** Be specific. "A loss
   worse than 2.0" is good; "bad results" is not.
2. **What alternative explanation should I rule out?** For every
   hypothesis there's usually a confound — different tokenization,
   different prompt format, lucky seed. Name the top one.
3. **What result would this hypothesis forbid?** A hypothesis that
   predicts *any* outcome is predicting nothing.

If any of the three are hard to answer, the hypothesis is too vague.
Sharpen it before running.

## Three ways an experiment lies to you

1. **Training-data leakage.** The model has seen something similar
   to your "held-out" evaluation. Validation loss looks great;
   generalization is worse. Check the training data source.
2. **Selection effect.** You report the run that worked, forget
   the three that didn't. Log every run, not just the winners.
3. **Post-hoc reasoning.** Run the experiment, then decide what
   it "really" tested. Commit the hypothesis before starting.

## When the verdict is always the same

Four consecutive "supported" verdicts is a red flag. It usually
means one of:

- The experiment isn't actually testing the hypothesis.
- The bar for "supported" is too loose.
- There's a shared confound across all four experiments.

Pivot the question. Design the *next* experiment to distinguish
between "hypothesis is actually true" and "the setup is broken."

## How to write up a falsification

When a hypothesis is rejected, that's valuable — more valuable than
a win. The write-up lives in
``lab/pkb/agents/experiments/<id>.md`` and must include:

- **What was predicted** (restate the hypothesis in one sentence)
- **What was observed** (the specific result)
- **Why it falsifies** (why the observation rules out the
  hypothesis — not just "didn't work")
- **What's next** (the sharper hypothesis that replaces this one)

The researcher agent treats falsifications as progress. So should
the user.
