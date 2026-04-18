"""Seed starter skills into the PKB on first boot.

Mirrors ``oglab.pkb_seed`` but for the new ``lab/pkb/skills/`` tree.
Three starter skills ship:

- ``observe-lab`` — how to notice things, used by Pip
- ``evaluate-llm`` — how to benchmark a local model, used by the
  researcher when the lab intent is AI engineering
- ``falsify-hypothesis`` — critical thinking applied to experiments

Idempotent. After ``./oglab reset pkb`` the skills re-seed on next
start. User edits survive subsequent boots — once a skill exists on
disk we never overwrite it.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from oglab.pkb import _pkb_root

log = logging.getLogger(__name__)


# ── observe-lab ────────────────────────────────────────────────────
# Pip's first named skill. Procedural knowledge of "what's worth
# saying." This file drives Pip's voice — edit it to change how Pip
# decides what to comment on.

_OBSERVE_LAB = """---
title: Observe the lab
id: observe-lab
name: Observe Lab
domain: meta
version: 1.0.0
tags: [skill, observation, personality]
when_to_use:
  - When acting as a personality agent (Pip and friends)
  - When deciding whether speaking up is worth it
  - When describing what just happened in plain English
when_not_to_use:
  - When driving a goal forward (that's the researcher's job)
  - When the user asked a direct question (answer it, don't observe)
  - When you have nothing interesting to say — silence is valid
---

# Observe the lab

Procedural knowledge for noticing useful things about an AI lab and
translating raw facts into one short, warm sentence.

## What's worth saying

A fact is worth a sentence when all four are true:

1. **Actionable or informative.** The user can do something with it,
   or it changes their mental model of the lab's current state.
2. **Time-sensitive.** It's more useful now than an hour from now.
   "GPU is hot right now" > "GPU has been hot sometimes."
3. **Non-obvious.** You're surfacing something the dashboard
   doesn't already make visible at a glance.
4. **Not recently said.** If a similar observation went out in the
   last half-hour, stay quiet.

## What's not worth saying

- Steady-state conditions ("the portal is running")
- Counts that only go up ("32 files in the PKB" — surface a delta
  instead: "five new files since yesterday")
- Anything the user can see by glancing at the dashboard

## How to phrase it

- **One sentence.** Never paragraphs. Under 20 words.
- **Report, don't narrate.** "RAM is at 94%" not "I notice RAM is at 94%."
- **No markdown, no emoji in the body.** The caller frames with a
  name/icon; the sentence itself stays plain text.
- **Specific over vague.** "The last four experiments all came back
  falsified" not "things seem stuck."
- **Praise lands softer than warn.** Celebrate wins generously; flag
  risks quietly.

## Tie-breaking when multiple facts fire

Pick in this order:

1. **Praise** — good news is cheap to deliver and feels good.
2. **Warn** — something's at risk; user may want to act.
3. **Info** — neutral pattern worth knowing.

If several observations land in the same class, pick the one with
the most recent trigger timestamp.

## Cadence

Prefer silence. A personality agent that speaks every five minutes
is annoying; one that speaks three times a day is a trusted friend.
Global cooldown is 5 min by default — honor it even when you have
something "good" to say.
"""


# ── evaluate-llm ───────────────────────────────────────────────────
# Researcher skill for the AI-engineering lab intent. Procedural
# approach to benchmarking a local model.

_EVALUATE_LLM = """---
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
"""


# ── falsify-hypothesis ─────────────────────────────────────────────
# Research methodology skill. Procedural bias-reduction.

_FALSIFY_HYPOTHESIS = """---
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
"""


_FRONTIER_LOCAL = """---
title: Frontier models, running locally
id: frontier-local-models
name: Frontier Local Models
domain: ai
version: 1.0.0
tags: [skill, frontier, airllm, local-inference, open-models]
when_to_use:
  - When reasoning about which deep model to pick for AirLLM
  - When the task deserves frontier-tier intelligence and can tolerate slow throughput
  - When documenting a result that came from a specific deep model
when_not_to_use:
  - For interactive chat (use the fast model instead)
  - For throughput-sensitive batch work
---

# Frontier models, running locally

OGLab can run models up to and beyond 700B parameters on a laptop
via AirLLM — layer-by-layer streaming from disk, one transformer
block loaded at a time. Throughput at that scale is tokens-per-
minute, not per-second, but the model itself is frontier-class.
This skill covers the mental model and which deep model to pick
for what.

## The AirLLM trick in one sentence

Instead of loading all of a model's layers into RAM, AirLLM loads
one layer from disk, computes through it, unloads, loads the
next. RAM use is tiny (one layer); disk use equals the whole
model (~100-800 GB depending on size and quantization); time per
token scales with the number of layers.

## Open models worth knowing about

All run on OGLab via AirLLM by setting `AIRLLM_MODEL=` in `.env`
to the HuggingFace repo ID. Dashboard's Frontier chip shows the
Spec Sheet for the currently-configured one.

### Elite generalists
- **Qwen3-235B-A22B** — Alibaba's flagship MoE. 22B active per
  token, so inference is cheaper than dense 235B. OGLab default.
  Apache 2.0.
- **DeepSeek-V3** — 671B MoE, 37B active. MIT license. Rivals
  GPT-4o on code and math. Incredible cost-efficiency.
- **Llama-3.1-405B** — Meta's dense flagship. Solid across the
  board, widely supported, slower via AirLLM because dense.

### Code + agent specialists
- **GLM-4.6** (Zhipu AI) — ~357B MoE. Strives to be declarative,
  strong on structured output and function-call pipelines.
  Near-frontier HumanEval scores at open-weight license.
- **GLM-5.1** — Zhipu's 2025+ flagship line. Scales up to
  ~754B MoE variants aiming at GPT-4-class capability while
  staying open-weight. Fits on any disk via AirLLM.
- **DeepSeek-R1** — reasoning-tuned derivative of V3. Shows its
  chain-of-thought. Rivals o1 on AIME + MATH-500 benchmarks.

### Smaller "deep" options
- **Qwen3-32B** / **Llama-3.1-70B** — still MoE or dense
  heavyweights, but small enough that AirLLM is seconds-per-token
  rather than minutes.

## Choosing the right deep model

Three questions:

1. **What's the disk budget?** 4-bit quantized:
   - 32B → ~20 GB
   - 70B → ~40 GB
   - 235B MoE → ~120 GB
   - 400B+ → 200 GB+
   - 700B+ → 400 GB+
2. **What's the task?** Code/agent → GLM-4.6 or DeepSeek-V3.
   Math/reasoning → DeepSeek-R1 or Qwen3-235B. Generalist →
   Qwen3-235B or Llama-3.1-70B.
3. **How patient are you?** MoE routes cheaper per token than
   dense at the same total params. A 400B MoE (37B active) is
   ~11× faster than 400B dense through AirLLM.

## Workflow for a deep-model research run

1. Configure: set `AIRLLM_MODEL=<repo-id>` in `.env`, restart.
2. Frame the question. Deep runs are expensive — write down the
   exact question you want answered before you send the chat.
3. Use the dashboard's **Deep model** toggle to flip for one
   message. Watch the Frontier chip for confirmation.
4. Give it 1-15 minutes depending on model size. The UI shows
   latency + tokens/sec so you'll know when it lands.
5. Save the reply to the PKB (`notes/` or `agents/research/`)
   with the model name + date — repro matters for frontier runs.

## Why this matters

Frontier-grade intelligence used to live behind expensive APIs.
Open-weight releases from Qwen, Zhipu, DeepSeek, and Meta closed
the gap. AirLLM made the hardware barrier vanish. The only thing
stopping a determined user from running GPT-4-class inference on
a MacBook is disk space — and that's a solvable problem.

Treat deep-model runs like you'd treat a batch job on a shared
cluster: frame the question carefully, write down the result,
learn from each turn.
"""


_SKILLS: Dict[str, Dict[str, Any]] = {
    "observe-lab":             {"content": _OBSERVE_LAB},
    "evaluate-llm":            {"content": _EVALUATE_LLM},
    "falsify-hypothesis":      {"content": _FALSIFY_HYPOTHESIS},
    "frontier-local-models":   {"content": _FRONTIER_LOCAL},
}


def _skill_dir(skill_id: str, pkb_root: Path | None = None) -> Path:
    return (pkb_root or _pkb_root()) / "skills" / skill_id


def ensure_starter_skills(pkb_root: Path | None = None) -> Dict[str, Any]:
    """Materialize shipped skills under ``lab/pkb/skills/`` if missing.

    Idempotent. Writes only when a skill directory has no
    ``SKILL.md`` — never overwrites user edits.
    """
    root = pkb_root or _pkb_root()
    (root / "skills").mkdir(parents=True, exist_ok=True)

    # Skills index README — drop it next to the skill folders so
    # users browsing /knowledge see what this tree is for.
    readme = root / "skills" / "README.md"
    if not readme.exists():
        readme.write_text(_SKILLS_README)

    installed: List[str] = []
    skipped: List[str] = []
    for skill_id, meta in _SKILLS.items():
        target = _skill_dir(skill_id, pkb_root=pkb_root) / "SKILL.md"
        if target.exists():
            skipped.append(skill_id)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(meta["content"])
        installed.append(skill_id)

    return {"ok": True, "installed": installed, "skipped": skipped}


# User-facing index page at lab/pkb/skills/README.md. Seeded once.
_SKILLS_README = """---
title: Skills
section: skills
tags: [skills, overview]
---

# Skills

This tree holds **procedural knowledge** — how-to markdown that
agents compose into their system prompts. Skills are the lab's
domain expertise in editable form.

Each subfolder is one skill. At minimum it contains ``SKILL.md``
with YAML frontmatter (id, domain, version, when-to-use) and a
markdown body explaining the skill.

## Skills vs tools

- **Skill** — markdown procedural knowledge. Agents load it into the
  system prompt. Editable by users and by agents themselves.
  Example: *how to evaluate a local LLM*.
- **Tool** — Python function the agent can call. Developer-authored,
  versioned in git, not editable at runtime.
  Example: ``system.gpu_pct()``.

## How agents use skills

An agent's ``AGENT.md`` lists the skills it needs:

```yaml
skills: [observe-lab, evaluate-llm]
```

On every LLM call, the agent reads these files and appends their
bodies to the system prompt. **Hot reload:** edit a skill, next
utterance uses the new version.

## Shipped starter skills

- [observe-lab](observe-lab/SKILL.md) — Pip's skill. What to notice,
  when to stay quiet, how to phrase an observation.
- [evaluate-llm](evaluate-llm/SKILL.md) — Researcher skill for the
  AI-engineering intent. Reproducible benchmarking.
- [falsify-hypothesis](falsify-hypothesis/SKILL.md) — Research
  methodology. Reduces confirmation bias.

## Authoring new skills

Drop a new folder here with a ``SKILL.md``. Frontmatter required
fields:

```yaml
---
title: <display name>
id: <folder-name-must-match>
name: <short name>
domain: <free-form category>
version: 1.0.0
tags: [skill, ...]
when_to_use: [...]
when_not_to_use: [...]
---
```

Then list your skill in any agent's ``AGENT.md``. No restart
needed — the next LLM call picks it up.

## Future

Today the system loads every listed skill **eagerly** — all bodies
appended to every LLM call. A planned v2 ("self-sufficient agents")
will let the agent decide which skill to consult per task, closer
to the tool-calling pattern in Claude. Skills shape doesn't change;
only the dispatch layer gets smarter.
"""
