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
