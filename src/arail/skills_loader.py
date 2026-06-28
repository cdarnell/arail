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

# ── World-skill caps (DoS / prompt-bloat guard) ────────────────────
_MAX_WORLD_SKILL_BYTES = 64 * 1024          # whole-file read cap (file-level)
# Body cap: 56K chars — comfortably above the largest real World glossary
# (~32K for art-history); truncation is a last resort and emits a WARN.
_MAX_WORLD_SKILL_BODY_CHARS = 56 * 1024

# ARAIL structural delimiters a tampered body must NOT be able to forge.
# Matched against the STRIPPED (lstripped) line so that indented variants
# (e.g. "  # WORLD FRAMING") are also caught (Defect 3 fix).
_ARAIL_DELIMITERS = (
    "# WORLD FRAMING",
    "# END WORLD FRAMING",
    "# Procedural knowledge",
    "## Skill:",
    "Observation:",
    "Source:",
    "Buddy's one-sentence note:",
)

# H1/H2 heading pattern at column 0 (optional leading whitespace) that is NOT
# a legitimate glossary header (h3+ like "### Dance" are preserved).
# Matches: "#<space>" (h1) or "##<space>" (h2 — e.g. "## Skill: ..."),
# but NOT "###" or deeper (those are the glossary category headers).
_HEADING_H1_H2_RE = re.compile(r"^\s*#{1,2}(?!#)\s")


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


def _contain_skill_body(body: str) -> str:
    """Defense-in-depth: re-apply DaC's containment in Python so a SKILL.md
    tampered AFTER DaC emitted it cannot forge prompt structure.

    Neutralization rules (per physical line):
    1. Normalize ``\\r\\n`` / ``\\r`` → ``\\n``.
    2. A bare YAML fence (``---``, possibly with leading whitespace) →
       neutralize with U+200C prefix.
    3. A backtick fence line (``````` or ```````` at any indent) → neutralize.
    4. Any ARAIL structural delimiter (see ``_ARAIL_DELIMITERS``) matched
       against the lstripped line — so both column-0 and indented variants
       are caught (e.g. ``  # WORLD FRAMING`` is caught).
    5. Any H1 or H2 markdown heading (``# ...`` or ``## ...``) that was NOT
       already neutralized above → neutralize. This prevents forging
       ``# WORLD FRAMING`` or ``## Skill: EVIL`` via a novel variant not in
       the delimiter list. H3 (``###``) and deeper are explicitly preserved —
       they are the legitimate glossary category headers (``### Dance`` etc.).

    Preserved:
    - ``### Category`` / ``#### subcategory`` headers (h3+)
    - ``- **term** — definition`` bullet lines (even at column 0)
    - ``  - Source: …`` lines (leading whitespace → not column-0 ``Source:``)
    - All indented prose lines

    Deterministic; mirrors skill.ts sanitizeBodyField at the line granularity
    ARAIL injects.
    """
    # Normalize line endings
    body = body.replace("\r\n", "\n").replace("\r", "\n")

    ZWNJ = "‌"  # U+200C zero-width non-joiner prefix for neutralized lines
    out_lines: List[str] = []

    for line in body.split("\n"):
        stripped = line.lstrip()

        # 2. YAML fence
        if stripped == "---":
            out_lines.append(ZWNJ + line)
            continue

        # 3. Backtick fence
        if stripped.startswith("```"):
            out_lines.append(ZWNJ + line)
            continue

        # 4. ARAIL structural delimiter (matched on lstripped so indented variants caught)
        forged = False
        for delim in _ARAIL_DELIMITERS:
            if (stripped == delim
                    or stripped.startswith(delim + " ")
                    or stripped.startswith(delim + "\t")):
                out_lines.append(ZWNJ + line)
                forged = True
                break
        if forged:
            continue

        # 5. H1 / H2 heading (## or # but NOT ###+ which are glossary headers)
        if _HEADING_H1_H2_RE.match(line):
            out_lines.append(ZWNJ + line)
            continue

        out_lines.append(line)

    return "\n".join(out_lines)


def load_skill_from_path(path: Path, skill_id: str) -> Optional["Skill"]:
    """Load a Skill from an explicit SKILL.md path (not the skills/ dir).

    Returns None when missing / oversized / unreadable.
    Applies on-load containment to the body (treats SKILL.md as untrusted DATA).
    """
    if not path.exists():
        return None
    try:
        raw_bytes = path.read_bytes()
    except OSError as e:
        log.warning("load_skill_from_path: cannot read %s: %s", path, e)
        return None
    if len(raw_bytes) > _MAX_WORLD_SKILL_BYTES:
        log.warning(
            "load_skill_from_path: %s exceeds %d-byte cap (%d bytes) — skipping",
            path, _MAX_WORLD_SKILL_BYTES, len(raw_bytes),
        )
        return None
    try:
        raw = raw_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        log.warning("load_skill_from_path: decode error on %s: %s", path, e)
        return None
    fm = parse_frontmatter(raw)
    body = strip_frontmatter(raw).strip()
    # Apply containment BEFORE size cap so a padded-then-stripped body can't
    # circumvent the byte cap with whitespace.
    body = _contain_skill_body(body)
    if len(body) > _MAX_WORLD_SKILL_BODY_CHARS:
        log.warning(
            "load_skill_from_path: %s body exceeds %d-char cap (%d chars) — truncating",
            path, _MAX_WORLD_SKILL_BODY_CHARS, len(body),
        )
        body = body[:_MAX_WORLD_SKILL_BODY_CHARS]
    return Skill(
        id=skill_id,
        name=str(fm.get("name") or fm.get("title") or skill_id),
        domain=str(fm.get("domain") or "general"),
        version=str(fm.get("version") or "0"),
        body=body,
        path=path,
        frontmatter=fm,
    )


def load_world_skill(
    pkb_root: Optional[Path] = None,
    data_dir: Optional[Path] = None,
) -> Optional["Skill"]:
    """Load the mounted World's SKILL.md as a Skill, or None when nothing is
    mounted / no SKILL.md staged.

    Keyed off current_mount().staged_dir so it tracks mount/unmount/swap
    with no extra state. Never raises.
    """
    try:
        from arail.world_mount import current_mount, _WORLD_SKILL_NAME
        record = current_mount(data_dir)
        if record is None:
            return None
        staged_skill = Path(record.staged_dir) / _WORLD_SKILL_NAME
        skill_id = f"world-{record.world}"
        return load_skill_from_path(staged_skill, skill_id)
    except Exception as e:
        log.warning("load_world_skill: unexpected error: %s", e)
        return None


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
