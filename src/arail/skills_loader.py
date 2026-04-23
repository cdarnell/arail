"""Skill loader — turns procedural markdown into agent system prompts.

A **skill** is a folder under ``lab/pkb/skills/<skill-id>/`` containing
at minimum a ``SKILL.md`` with YAML frontmatter + markdown body. The
frontmatter is the machine-readable contract (id, domain, version,
when-to-use); the body is the procedural knowledge that gets woven
into the agent's system prompt.

Design choices for v1:

- **Eager loading.** Every skill listed in an agent's ``AGENT.md``
  gets appended to its system prompt on every LLM call. Simple,
  predictable, and the payoff — "edit SKILL.md, next utterance
  behaves differently" — is the whole point.
- **Hot reload.** Skills are read from disk each time an agent
  assembles its prompt. Markdown files are tiny, the read is
  effectively free, and the user-facing responsiveness is worth it.
- **No execution layer.** Skills are pure prose. They don't resolve
  to Python functions — that's what tools are for. Keeping the two
  clean-separated (prose is knowledge, code is capability) makes
  both easier to reason about.

**Future work (v2):** self-sufficient agents that pick a skill
lazily ("I need the `falsify-hypothesis` skill for this task"). That
needs a dispatch layer and agents smart enough to choose. Eager
first proves the shape; lazy comes when we have more skills than
fit comfortably in a prompt.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from arail.pkb import _pkb_root

log = logging.getLogger(__name__)


# ── Minimal YAML frontmatter parser ────────────────────────────────
# Pulled inline instead of adding a pyyaml dependency. Handles the
# subset we actually use in skill / agent frontmatter:
#   key: value                     → string
#   key: [a, b, c]                 → list of strings
#   key:                           → list (next-line dashes)
#     - a
#     - b
# Doesn't handle nested maps — we don't need them in skills today.

_FM_FENCE = "---"


def parse_frontmatter(text: str) -> Dict[str, Any]:
    """Return the YAML frontmatter as a dict, {} when missing."""
    stripped = text.lstrip()
    if not stripped.startswith(_FM_FENCE):
        return {}
    end = stripped.find(f"\n{_FM_FENCE}", len(_FM_FENCE))
    if end == -1:
        return {}
    body = stripped[len(_FM_FENCE):end].strip("\n")
    return _parse_yaml_block(body)


def strip_frontmatter(text: str) -> str:
    """Return the markdown body with frontmatter removed."""
    stripped = text.lstrip()
    if not stripped.startswith(_FM_FENCE):
        return text
    end = stripped.find(f"\n{_FM_FENCE}", len(_FM_FENCE))
    if end == -1:
        return text
    after = stripped[end + len(_FM_FENCE) + 1:]
    return after.lstrip("\n")


def _parse_yaml_block(block: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$", line)
        if not match:
            i += 1
            continue
        key, val = match.group(1), match.group(2).strip()
        if val == "":
            # Next-line list or map; we only support lists.
            items: List[str] = []
            j = i + 1
            while j < len(lines) and lines[j].lstrip().startswith("- "):
                items.append(lines[j].lstrip()[2:].strip().strip("'\""))
                j += 1
            result[key] = items
            i = j
            continue
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if not inner:
                result[key] = []
            else:
                result[key] = [
                    s.strip().strip("'\"") for s in inner.split(",")
                ]
            i += 1
            continue
        # Plain scalar — strip surrounding quotes if present.
        result[key] = val.strip("'\"")
        i += 1
    return result


# ── Skill dataclass + loading ──────────────────────────────────────

@dataclass
class Skill:
    """One procedural-knowledge module loaded from SKILL.md."""

    id: str                         # matches the directory name
    name: str                       # display name from frontmatter
    domain: str                     # free-form category ("meta", "ai", ...)
    version: str                    # semver-ish string
    body: str                       # markdown body (frontmatter stripped)
    path: Path                      # on-disk path to SKILL.md
    frontmatter: Dict[str, Any] = field(default_factory=dict)


def _skills_dir(pkb_root: Path | None = None) -> Path:
    return (pkb_root or _pkb_root()) / "skills"


def load_skill(skill_id: str, pkb_root: Path | None = None) -> Optional[Skill]:
    """Load a single skill by id. Returns None when missing or broken."""
    if not skill_id or "/" in skill_id or ".." in skill_id:
        return None
    path = _skills_dir(pkb_root) / skill_id / "SKILL.md"
    if not path.exists():
        return None
    try:
        raw = path.read_text(errors="replace")
    except OSError:
        return None
    fm = parse_frontmatter(raw)
    body = strip_frontmatter(raw).strip()
    return Skill(
        id=skill_id,
        name=str(fm.get("name") or fm.get("title") or skill_id),
        domain=str(fm.get("domain") or "general"),
        version=str(fm.get("version") or "0"),
        body=body,
        path=path,
        frontmatter=fm,
    )


def load_skills(skill_ids: List[str], pkb_root: Path | None = None) -> List[Skill]:
    """Load many skills. Missing or broken skills are skipped with a warning."""
    out: List[Skill] = []
    for sid in skill_ids or []:
        skill = load_skill(sid, pkb_root=pkb_root)
        if skill is None:
            log.warning("Skill %r not found under %s — skipping",
                        sid, _skills_dir(pkb_root))
            continue
        out.append(skill)
    return out


def list_installed_skills(pkb_root: Path | None = None) -> List[Skill]:
    """Return every skill currently in lab/pkb/skills/. For the
    Knowledge tab's skill gallery + future Forge skill picker."""
    root = _skills_dir(pkb_root)
    if not root.exists():
        return []
    out: List[Skill] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        skill = load_skill(child.name, pkb_root=pkb_root)
        if skill is not None:
            out.append(skill)
    return out


# ── Agent-side composition ─────────────────────────────────────────
# Called by each agent when it's assembling the system prompt for an
# LLM call. Reads the agent's AGENT.md to get its skill list, loads
# each skill, returns the concatenated context to append.

def load_agent_skills(agent_id: str,
                      pkb_root: Path | None = None) -> List[Skill]:
    """Read lab/pkb/agents/<agent_id>/AGENT.md, load its skills."""
    root = pkb_root or _pkb_root()
    agent_md = root / "agents" / agent_id / "AGENT.md"
    if not agent_md.exists():
        return []
    try:
        raw = agent_md.read_text(errors="replace")
    except OSError:
        return []
    fm = parse_frontmatter(raw)
    skill_ids = fm.get("skills") or []
    if not isinstance(skill_ids, list):
        return []
    return load_skills([str(s) for s in skill_ids], pkb_root=pkb_root)


def compose_system_context(skills: List[Skill]) -> str:
    """Concatenate skill bodies into a single system-prompt section.

    Output is markdown with each skill under its own H2 so the local
    model can distinguish one body of knowledge from another. Empty
    when no skills loaded — caller should still prepend its base
    prompt even without skills.
    """
    if not skills:
        return ""
    parts = ["# Procedural knowledge"]
    for skill in skills:
        parts.append(f"\n## Skill: {skill.name}  ·  v{skill.version}")
        parts.append(skill.body)
    return "\n\n".join(parts)
