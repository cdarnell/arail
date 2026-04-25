"""Seed default ``AGENT.md`` files under ``lab/pkb/agents/`` on first boot.

Each builtin agent gets a markdown file with YAML frontmatter
declaring its skill loadout. The file is the source of truth for
which skills an agent loads on every LLM call (see
``arail.skills_loader.load_agent_skills``).

Two reasons to ship default loadouts on disk instead of hardcoding
them in each agent's Python:

* The Skills tab can read + edit one file path consistently across
  builtin and forged agents.
* A user editing ``lab/pkb/agents/researcher/AGENT.md`` immediately
  changes which skills the next LLM call composes — no restart, no
  code change.

Idempotent. Pip already ships its own AGENT.md (richer than the
default — preserved). Researcher / Curator / Browser get scaffolds
that the user can edit freely.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def _pkb_root() -> Path:
    from arail.config import PKB_ROOT
    return PKB_ROOT


# ── Default loadouts ──────────────────────────────────────────────
# Skill ids must match folders under lab/pkb/skills/. The lab seeds
# research-methodology + model-building packs by default, so all the
# skills referenced below exist after first boot.
#
# curation-vetting is opt-in; we still reference its skills in the
# default loadouts so installing that pack later "lights up" the
# curator and browser without further action by the user. Missing
# skills are just skipped at LLM-call time (see skills_loader.py).

_DEFAULT_LOADOUTS: Dict[str, Dict[str, Any]] = {
    "researcher": {
        "name": "Researcher",
        "emoji": "🔬",
        "voice": "Methodical, falsifiable, measurement-first.",
        "purpose": "Decomposes a goal into hypotheses, designs and "
                    "runs experiments, writes reports back to the KB.",
        "skills": [
            "falsify-hypothesis",
            "evaluate-llm",
            "optimize-aerollm",
            "frontier-local-models",
        ],
        "consumes_llm": True,
    },
    "curator": {
        "name": "Curator",
        "emoji": "📚",
        "voice": "Skeptical, source-aware, archives the trail.",
        "purpose": "Vets incoming sources, decides what enters the "
                    "knowledge base, attaches provenance + caveats.",
        "skills": [
            "vet-source",
            "spot-bias",
            "fact-check-claim",
        ],
        "consumes_llm": False,
    },
    "browser": {
        "name": "Browser",
        "emoji": "🌐",
        "voice": "Targeted, source-vetting, anti-clickbait.",
        "purpose": "Web research with source quality controls. "
                    "Hands findings to the Curator for vetting.",
        "skills": [
            "vet-source",
            "fact-check-claim",
        ],
        "consumes_llm": True,
    },
}


def _agent_md(agent_id: str, loadout: Dict[str, Any]) -> str:
    """Render an AGENT.md from a loadout dict."""
    skills_yaml = "\n".join(f"  - {s}" for s in loadout["skills"])
    consumes = "yes" if loadout.get("consumes_llm") else "no"
    return f"""---
title: {loadout['name']}
id: {agent_id}
name: {loadout['name']}
emoji: {loadout.get('emoji', '🤖')}
section: agents/{agent_id}
tags: [agent, {agent_id}, builtin, loadout]
voice: "{loadout.get('voice', '')}"
consumes_llm: {consumes}
# Skills this agent loads on every LLM call. Each entry resolves to
# SKILL.md under lab/pkb/skills/<skill-id>/. Missing skills are
# silently skipped (see arail.skills_loader). Edit this list — or
# the SKILL.md bodies it references — to change agent behavior;
# next call picks up the change (hot reload, no restart).
skills:
{skills_yaml}
---

# {loadout['name']}

{loadout.get('purpose', '')}

## Loadout

The skills above shape this agent's reasoning on every LLM call.
Add or remove entries, or edit the underlying SKILL.md bodies in
[lab/pkb/skills/](../../skills/), to course-correct without
touching code.

{'**Note:** this agent does not currently call the LLM directly. '
 'The loadout is documentary today — installing skills here makes '
 'them visible in the Skills tab and ready for when the agent gets '
 'an LLM-driven path.' if not loadout.get('consumes_llm') else
 'This agent calls the LLM directly — every entry above gets '
 'composed into the system prompt for each generation pass.'}
"""


def _agent_dir(agent_id: str, *, pkb_root: Path | None = None) -> Path:
    return (pkb_root or _pkb_root()) / "agents" / agent_id


def ensure_default_loadouts(pkb_root: Path | None = None) -> Dict[str, Any]:
    """Create AGENT.md scaffolds for builtin agents that lack one.

    Idempotent. Never overwrites an existing AGENT.md — Pip's
    richer file (shipped via builtin_seed) survives untouched, as
    do any user edits to researcher/curator/browser.
    """
    written: List[str] = []
    skipped: List[str] = []
    for agent_id, loadout in _DEFAULT_LOADOUTS.items():
        target = _agent_dir(agent_id, pkb_root=pkb_root) / "AGENT.md"
        if target.exists():
            skipped.append(agent_id)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_agent_md(agent_id, loadout))
        written.append(agent_id)
    return {"ok": True, "written": written, "skipped": skipped}


def list_default_agents() -> List[str]:
    """Builtin agent ids covered by the default loadouts."""
    return list(_DEFAULT_LOADOUTS.keys())
