"""Seed starter skills into the PKB on first boot.

Mirrors ``arail.pkb_seed`` for the ``lab/pkb/skills/`` tree.

Two sources of truth:

* ``observe-lab`` is **inlined here** because it's tied to Buddy's
  personality and the dashboard expects Buddy to always have something
  to say even after every domain pack has been uninstalled.
* The domain packs (``research-methodology``, ``model-building``,
  ``curation-vetting``) live in :mod:`arail.skill_packs` as
  on-disk pack folders so the Skills tab can reinstall, edit, or
  remove them without touching this module. First boot installs the
  default two; ``curation-vetting`` is opt-in.

Idempotent. After ``./arail reset pkb`` the skills re-seed on next
start. User edits survive subsequent boots — once a skill exists
on disk we never overwrite it (unless the Skills tab triggers a
forced re-install).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from arail.pkb import _pkb_root

log = logging.getLogger(__name__)


# ── observe-lab ────────────────────────────────────────────────────
# Buddy's first named skill. Procedural knowledge of "what's worth
# saying." This file drives Buddy's voice — edit it to change how
# Buddy decides what to comment on.

_OBSERVE_LAB = """---
title: Observe the lab
id: observe-lab
name: Observe Lab
domain: meta
version: 1.0.0
tags: [skill, observation, personality]
when_to_use:
  - When acting as a personality agent (Buddy and friends)
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

- **One sentence.** Never paragraphs. Under 25 words.
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
4. **Suggest** — goal-anchored proposal (technique, review, run).

If several observations land in the same class, pick the one with
the most recent trigger timestamp.

## Cadence

Prefer silence. A personality agent that speaks every five minutes
is annoying; one that speaks three times a day is a trusted friend.
Global cooldown is 5 min by default — honor it even when you have
something "good" to say.
"""


# Inline-only skills — anything that must ship with the lab even
# when a user has uninstalled every domain pack. observe-lab is the
# only one today: it's tied to Buddy's personality and the dashboard
# expects Buddy to always have something to say. Everything else
# lives in arail.skill_packs and is managed via the Skills tab.
_SKILLS: Dict[str, Dict[str, Any]] = {
    "observe-lab": {"content": _OBSERVE_LAB},
}


def _skill_dir(skill_id: str, pkb_root: Path | None = None) -> Path:
    return (pkb_root or _pkb_root()) / "skills" / skill_id


def ensure_starter_skills(pkb_root: Path | None = None) -> Dict[str, Any]:
    """Materialize shipped skills under ``lab/pkb/skills/`` if missing.

    Idempotent. Writes only when a skill directory has no
    ``SKILL.md`` — never overwrites user edits.

    Two sources of skills:
      * **observe-lab** stays inline in this module — it's Buddy's
        intrinsic personality skill, not part of a domain pack.
      * **Domain packs** (research-methodology, model-building) are
        delegated to :mod:`arail.skill_packs` so the on-disk pack
        folders are the single source of truth. The Skills tab can
        reinstall or remove these packs without touching this code.
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

    # 1. Inline skills (just observe-lab today).
    for skill_id, meta in _SKILLS.items():
        target = _skill_dir(skill_id, pkb_root=pkb_root) / "SKILL.md"
        if target.exists():
            skipped.append(skill_id)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(meta["content"])
        installed.append(skill_id)

    # 2. Default packs — install on first boot. force=False so user
    # edits survive every restart.
    try:
        from arail.skill_packs import install_pack
    except Exception:
        install_pack = None  # type: ignore[assignment]
    if install_pack is not None:
        for pack_id in ("research-methodology", "model-building"):
            res = install_pack(pack_id, pkb_root=root, force=False)
            installed.extend(res.get("installed", []))
            skipped.extend(res.get("skipped_existing", []))

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

- [observe-lab](observe-lab/SKILL.md) — Buddy's skill. What to notice,
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
