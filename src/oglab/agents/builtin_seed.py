"""Seed the shipped agent folders into the PKB on first boot.

Mirrors the pattern in ``oglab.pkb_seed`` for knowledge starter packs:
canonical source lives in the installed package (``_builtin_pip.py``);
a user-editable copy lives under ``lab/pkb/agents/<name>/`` in the
PKB where the Knowledge tab can browse and edit it.

Runs on every portal start. Idempotent — writes nothing if the
folder already exists with a ``pip.py`` inside. After ``./oglab reset
pkb`` the folder is gone; this helper re-creates it on next start so
Pip is always available.

The seed also drops a short ``README.md`` at ``lab/pkb/agents/``
explaining the folder layout to anyone browsing the Knowledge tree.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from oglab.pkb import _pkb_root

log = logging.getLogger(__name__)


# ── AGENT.md template ──────────────────────────────────────────────
# Frontmatter is the machine-readable contract. Prose under it is for
# humans who open the file in /knowledge. v1 only reads the `dream`
# and `auto_start_env` fields; the rest document intent and reserve
# fields for Steps 2-5 (dreams, skills, Forge).
_AGENT_MD = """---
title: Pip — Lab Buddy
name: Pip
emoji: 🐧
section: agents/pip
tags: [agent, pip, builtin, personality]
voice: "Warm, observant lab buddy. One short sentence. Never emojis in replies."
tick_interval_sec: 90
global_cooldown_sec: 300
dream: true
auto_start_env: LAB_PIP
# Skills this agent uses. Each entry resolves to SKILL.md under
# lab/pkb/skills/<skill-id>/. The body of each listed skill gets
# appended to Pip's system prompt on every LLM call (hot reload —
# edit the skill file, next utterance uses the new version).
skills: [observe-lab]
---

# Pip — the lab buddy

Pip is the lab's fourth core agent and the **reference implementation
for the personality-agent pattern**. Unlike the researcher (which
drives a goal) or the curator (which finds sources), Pip doesn't
accomplish anything — it *notices*. Pip watches the state of the lab
and speaks up with one warm sentence when something's worth
commenting on.

## What Pip watches (v1)

| Watcher | Severity | Cooldown | Fires when |
|---|---|---|---|
| `gpu` | warn | 20 min | RAM ≥ 92% |
| `inbox` | info | 4 h | 3+ files in PKB inbox > 6 h old |
| `researcher-win` | praise | 3 h | An experiment landed "supported" today |
| `plateau` | info | 2 h | Last 4 experiments reached the same verdict |

## Rules of engagement

- **Global cooldown: 5 minutes.** Pip stays quiet for at least 5 min
  after any utterance, no matter which watcher fires.
- **Replies under 20 words.** Hard-capped at 200 characters after
  paraphrasing, because models sometimes get chatty.
- **Praise first.** When multiple watchers fire in one tick, praise
  wins, then warn, then info — because good news is cheap to deliver
  and feels good.

## Editing Pip

- Voice / personality → edit the `voice:` frontmatter field above OR
  edit `SYSTEM_PROMPT` directly in `pip.py`.
- Add / remove watchers → edit the `WATCHERS` list in `pip.py`.
- Tuning → `LAB_PIP_INTERVAL_SEC`, `LAB_PIP_GLOBAL_COOLDOWN_SEC` in
  `.env`.
- Mute Pip → set `LAB_PIP=off` in `.env`.
- Wipe Pip's memory → delete `state.json` or run `./oglab reset pkb`.

## Companion files

- [pip.py](pip.py) — the body (watchers + loop + speech)
- [state.json](state.json) — persisted memory (cooldowns, utterance count)
- [decisions.md](decisions.md) — append-only decision log
- [dreams/](dreams/) — nightly reflection journal (Step 2 writes here)
"""


_DECISIONS_MD = """---
title: Pip — Decisions
section: agents/pip
tags: [agent, pip, decisions]
---

# Pip — Decision Log

Append-only record of meaningful choices about Pip. Format:
`YYYY-MM-DD — what changed — why`.

When the Agent Forge lands, the researcher will be able to propose
changes here; for now, edit it by hand when you tune Pip's behavior.

- 2026-04-18 — Spawned. Starting with 4 watchers (gpu, inbox, researcher-win, plateau).
- 2026-04-18 — Global cooldown 5 min. Cheaper to be quiet than annoying.
"""


_AGENTS_README = """---
title: Agents
section: agents
tags: [agents, overview]
---

# Agents

Every agent in OGLab lives as a folder under this directory. The
folder contains everything the agent is:

- **`AGENT.md`** — the root config: voice, skills, intervals, dream
  on/off. Edit this to change the agent's behavior without touching
  Python.
- **`<agent>.py`** — the body: watchers, loop, speech. Editable if
  you want to extend what the agent notices or how it acts.
- **`state.json`** — persisted memory (cooldowns, counts). Survives
  portal restarts. Delete to wipe the agent's memory.
- **`decisions.md`** — append-only log of meaningful choices about
  the agent. Humans write to it; the Agent Forge will too.
- **`dreams/`** — one markdown file per night, written by the agent's
  optional `dream()` hook during the heavy work window. Yesterday's
  dream becomes part of today's system prompt — that's how agents
  remember.

## How agents stay in sync with the rest of the lab

Agents live under `lab/pkb/agents/` inside the PKB so every file
above is:

- Indexed by the wiki (`/wiki`)
- Browsable from `/knowledge`
- Searchable via the unified search
- Wiped cleanly by `./oglab reset pkb`
- Re-seeded on next `./oglab start` for the shipped agents

## What's here today

- **`pip/`** — 🐧 Pip, the lab buddy. Notices things, speaks up
  occasionally. Template shape for the upcoming Agent Forge.
- **`research/`, `experiments/`, `synthesis/`, `recommendations/`** —
  these are the **output directories** where the researcher agent
  writes findings. They don't have an `AGENT.md` — that's how the
  agent loader distinguishes "agent folders" from "output folders".

## Roadmap

See `docs/agents.md` for the full architecture, including how this
folder shape fits into skills, dreams, and the forthcoming Agent
Forge.
"""


# ── Research program template ─────────────────────────────────────
# First-boot seed for lab/pkb/research/. Ships with the lab's
# signature research goal baked in: optimize AeroLLM on frontier-
# scale models. Users override by editing program.md from /knowledge.

_RESEARCH_PROGRAM_MD = """---
title: SSD-hosted model inference — lab research program
section: research
tags: [meta, agent-instructions, aerollm, ssd-inference, optimization]
lab_theme: Making SSD-hosted model inference faster
auto_goal: Optimize AeroLLM's tokens-per-minute on frontier-scale models
---

# SSD-hosted model inference — the lab's signature research area

**Lab theme (overwrite via `LAB_THEME` in `.env`):** making
SSD-hosted model inference faster — running frontier open-weight
models on laptop hardware at usable speeds.

This is the long-running research area. Specific goals come and go
(today it's "optimize AeroLLM's tokens-per-minute"); the theme is
the north star that outlasts any single goal.

**Today's concrete goal.** AeroLLM runs frontier-scale language
models (100B-750B+) on laptop hardware by streaming transformer
layers from disk with a multi-threaded prefetcher that overlaps
I/O and compute across concurrent prompts. It works, but there's
room to push further — throughput per watt, per dollar, per
simultaneous prompt. The lab's research goal is to make it
noticeably faster on YOUR hardware, measure the wins, and
contribute them upstream.

## Goal

**Increase AeroLLM throughput on frontier-scale models by at least
2× without sacrificing more than 0.5% quality on a held-out eval.**

Primary metric: tokens-per-minute (t/min), captured automatically
to `lab/data/aerollm-bench.jsonl` on every deep-model chat reply.

Secondary metric: quality delta vs a FP16 baseline on the
validation set defined in [prepare.py](prepare.py).

## Why this matters

Frontier-class intelligence used to cost $20+/month in API fees.
Open-weight models from Qwen, GLM, DeepSeek, Meta closed the
knowledge gap. Layer-streaming runtimes closed the hardware gap.
The remaining gap is speed — and it's the kind of gap clever
engineering (not scaling laws) can close.

## Hypotheses worth testing

Ordered by estimated effort/impact ratio. Pick one per cycle.

1. **Prefetch lookahead tuning** — more layers in flight hides more
   disk I/O on NVMe, until memory pressure flips the curve.
   Moderate effort; likely win.
2. **Mixed-precision per-layer** — attention at INT8/FP16, FFN at
   INT4. ~30-50% disk shrink with minimal quality loss. Easy win
   once you've measured per-layer sensitivity.
3. **Speculative decoding with the lab's fast SLM** — the 8B model
   already loaded in RAM drafts tokens; AeroLLM validates in batch.
   Hard to implement, 3-5× potential. Lab-specific advantage.
4. **Persistent KV cache** — cache per-layer K/V to disk keyed by
   prompt prefix hash so follow-up messages skip most work.
   Huge on conversational use cases.
5. **Concurrent-prompt batching** — AeroLLM's raison d'être; keep
   pushing N up and measure where the per-prompt latency curve
   flattens on your hardware.

## Success criteria

A candidate optimization "ships" when:

- Measurement delta reproduces across ≥ 3 separate runs.
- Quality delta under 0.5% on our validation benchmarks.
- The change fits in a 500-word PR description upstream.
- A human can look at before/after t/min graph and see it.

Anything that clears those bars → PR to
[github.com/cdarnell/aerollm](https://github.com/cdarnell/aerollm).
Anything that doesn't → stays in the lab's branch as an experiment.

## Constraints

- Do NOT modify [prepare.py](prepare.py) — it's the validation
  substrate. Changing it means the agent is grading its own
  homework.
- Do NOT skip the baseline. Every optimization run needs a
  pre-change measurement.
- Log every experiment, not just the winners. The failures are
  often where the next hypothesis comes from.

## Relevant skills loaded by the researcher

The researcher agent reads these procedural knowledge files on
every LLM call — edit them to sharpen the agent's approach:

- [optimize-aerollm](../skills/optimize-aerollm/SKILL.md) — the
  methodology for this specific goal.
- [understanding-precision](../skills/understanding-precision/SKILL.md) —
  INT vs FP, quantization bit-counts, sensitivity per layer.
- [frontier-local-models](../skills/frontier-local-models/SKILL.md) —
  which deep models to target and why.
- [falsify-hypothesis](../skills/falsify-hypothesis/SKILL.md) —
  how to reduce confirmation bias in throughput claims.
- [evaluate-llm](../skills/evaluate-llm/SKILL.md) — how to measure
  quality rigorously.

## Out of scope

- **Training** — this lab doesn't train models. Quantization means
  post-training quantization only.
- **Alternative inference engines** — no vLLM, no TGI, no separate
  MLX port. The goal is specifically to improve AeroLLM.
- **New model architectures** — we use whatever Qwen/GLM/DeepSeek
  ships. Research is on the inference stack, not the models.

## Background / prior art

- [AeroLLM source](https://github.com/cdarnell/aerollm)
- Model primers in [lab/pkb/sources/seeds/model-building/](../sources/seeds/model-building/)
- The existing [evaluate-llm](../skills/evaluate-llm/SKILL.md)
  and [falsify-hypothesis](../skills/falsify-hypothesis/SKILL.md)
  skills
"""


_RESEARCH_PREPARE_PY = '''"""prepare.py — validation substrate for the AeroLLM research goal.

This is the cheat-proof side of the research contract: the
researcher agent CANNOT modify this file. If it wants a better
throughput number, it has to write faster AeroLLM code, not
redefine what "good" means.

See program.md for the natural-language side.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

RANDOM_SEED = int(os.getenv("LAB_RESEARCH_SEED", "1337"))
DATA_DIR = Path(os.getenv("LAB_RESEARCH_DATA", "lab/research/data"))


def prepare_environment() -> Dict[str, Any]:
    """Return the evaluation environment. Idempotent."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return {
        "data_dir": DATA_DIR,
        "primary_metric": "tokens_per_minute",
        "secondary_metric": "quality_delta_vs_fp16",
        "metric_docstring": throughput_metric.__doc__,
        "random_seed": RANDOM_SEED,
        "min_runs": 3,
        "min_prompts_per_run": 10,
    }


def throughput_metric(model_name: str, duration_sec: float,
                      tokens_generated: int) -> float:
    """Measure inference throughput in tokens per minute.

    Higher is better. Captured automatically by the portal for every
    deep-model call; aggregates live at /api/aerollm/bench.
    """
    if duration_sec <= 0:
        return 0.0
    return (tokens_generated / duration_sec) * 60.0


def quality_delta_vs_fp16(before: float, after: float) -> float:
    """Absolute delta in validation score between FP16 baseline
    and the candidate quantization.

    Positive = worse (quality lost). Under 0.5% is noise; over 2%
    is user-visible. Anything in between is a judgment call for the
    research cycle.
    """
    return abs(before - after)


def check_guardrails(submission: Dict[str, Any]) -> Optional[str]:
    """Veto submissions that break the research contract."""
    # Must include at least 3 separate measurement runs.
    runs = submission.get("runs") or []
    if len(runs) < 3:
        return "need at least 3 separate runs to claim a throughput gain"
    # Must include FP16 baseline for comparison.
    if not submission.get("fp16_baseline"):
        return "missing FP16 baseline — can't measure quality delta"
    # Must pass quality gate.
    delta = submission.get("quality_delta_pct", 100)
    if delta > 0.5:
        return f"quality delta {delta}% exceeds 0.5% ship threshold"
    return None


if __name__ == "__main__":
    meta = prepare_environment()
    print(f"Primary metric: {meta['primary_metric']}")
    print(f"Secondary:      {meta['secondary_metric']}")
    print(f"Min runs:       {meta['min_runs']}")
'''


def ensure_research_files(pkb_root: Path | None = None) -> dict:
    """Materialize lab/pkb/research/ with the AeroLLM research plan.

    Idempotent — writes only when files are missing so user edits
    survive subsequent boots. Users who want to swap the goal can
    either edit program.md directly or point the researcher at a
    different goal via the dashboard.
    """
    root = pkb_root or _pkb_root()
    research_dir = root / "research"
    research_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    program = research_dir / "program.md"
    if not program.exists():
        program.write_text(_RESEARCH_PROGRAM_MD)
        written.append("program.md")
    prepare = research_dir / "prepare.py"
    if not prepare.exists():
        prepare.write_text(_RESEARCH_PREPARE_PY)
        written.append("prepare.py")
    return {"ok": True, "written": written}


def ensure_pip_folder(pkb_root: Path | None = None) -> dict:
    """Materialize lab/pkb/agents/pip/ if missing.

    Idempotent: if the folder exists AND ``pip.py`` is present inside,
    do nothing. Otherwise write all five files (AGENT.md, pip.py copy,
    decisions.md, dreams/.gitkeep, and the agents/ README).

    Returns a small summary dict describing what happened — useful for
    the startup activity-log line.
    """
    root = pkb_root or _pkb_root()
    agents_dir = root / "agents"
    pip_dir = agents_dir / "pip"

    # The PKB's agents/ directory already exists for output dirs. Drop
    # the README next to them (write once; don't clobber user edits).
    agents_dir.mkdir(parents=True, exist_ok=True)
    readme = agents_dir / "README.md"
    wrote_readme = False
    if not readme.exists():
        readme.write_text(_AGENTS_README)
        wrote_readme = True

    # Pip folder — short-circuit when it's already set up. User may
    # have intentionally edited or deleted individual files; we don't
    # overwrite their choices on subsequent boots.
    pip_py = pip_dir / "pip.py"
    if pip_py.exists():
        return {"ok": True, "created": False, "readme": wrote_readme}

    pip_dir.mkdir(parents=True, exist_ok=True)
    (pip_dir / "dreams").mkdir(exist_ok=True)

    # Copy _builtin_pip.py → pip.py. sibling path resolves at runtime.
    builtin = Path(__file__).parent / "_builtin_pip.py"
    shutil.copy(builtin, pip_py)

    (pip_dir / "AGENT.md").write_text(_AGENT_MD)
    (pip_dir / "decisions.md").write_text(_DECISIONS_MD)
    # .gitkeep so dreams/ shows up in trees even when empty.
    (pip_dir / "dreams" / ".gitkeep").write_text("")

    return {
        "ok": True,
        "created": True,
        "readme": wrote_readme,
        "path": str(pip_dir),
    }


# ── SRE Watch templates ──────────────────────────────────────────────
_SRE_AGENT_MD = """---
title: SRE Watch — Crash Monitor
name: SRE
emoji: 🔥
section: agents/sre
tags: [agent, sre, monitoring, builtin]
voice: "Terse incident reporter. One sentence, clinical precision. No emojis. State error type, location, count."
tick_interval_sec: 120
global_cooldown_sec: 180
dream: false
auto_start_env: LAB_SRE
skills: []
---

# SRE Watch — the crash monitor

SRE Watch is a reliability agent. It reads `lab/data/activity.jsonl`
on every tick and surfaces errors and crash recurrences in the
activity feed — so you notice them without having to tail a log file.

## What SRE Watch monitors

| Watcher | Severity | Cooldown | Fires when |
|---|---|---|---|
| `recent-errors` | warn | 10 min per fingerprint | A new error/warn pattern appeared in the last 5 min |
| `crash-recurrence` | warn | 15 min per fingerprint | Same error pattern hit 3+ times in 30 min |
| `service-health` | warn | 10 min | Portal `/api/jobs/state` is unreachable |

## Editing SRE Watch

- Add new watchers → add a function to `WATCHERS` in `sre.py`.
- Tune cooldowns → env vars `LAB_SRE_INTERVAL_SEC`, `LAB_SRE_COOLDOWN_SEC`.
- Mute → set `LAB_SRE=off` in `.env`.
- Wipe memory → delete `state.json`.

## Companion files

- [sre.py](sre.py) — watchers + loop
- [state.json](state.json) — persisted fingerprint memory + cooldowns
"""


def ensure_sre_folder(pkb_root: Path | None = None) -> dict:
    """Materialize lab/pkb/agents/sre/ if missing.

    Idempotent: if the folder exists AND ``sre.py`` is present inside,
    do nothing. Otherwise write AGENT.md and copy _builtin_sre.py.
    """
    root = pkb_root or _pkb_root()
    sre_dir = root / "agents" / "sre"

    sre_py = sre_dir / "sre.py"
    if sre_py.exists():
        return {"ok": True, "created": False}

    sre_dir.mkdir(parents=True, exist_ok=True)

    builtin = Path(__file__).parent / "_builtin_sre.py"
    shutil.copy(builtin, sre_py)
    (sre_dir / "AGENT.md").write_text(_SRE_AGENT_MD)

    return {
        "ok": True,
        "created": True,
        "path": str(sre_dir),
    }
