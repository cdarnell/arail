"""Agent Forge — turn a form into a working agent folder.

The Forge is the user-facing way to mint a new agent without
hand-editing Python. It's a thin server-side wrapper over three
operations:

    1. Slugify the agent name into a Python-safe id.
    2. Generate ``AGENT.md`` from the form fields.
    3. Generate ``<id>.py`` from a template (the same shape as Pip,
       minus the specific watchers — watchers are added post-deploy
       via the Knowledge tab's markdown editor).

Deployment writes the folder under ``lab/pkb/agents/<id>/`` and
immediately calls ``loader.load_one()`` so the new agent goes live
without a portal restart. If hot-load works, the caller also gets
a ``.start()`` + dream-daemon registration.

The frontend regenerates the same code client-side for the live
preview, so users can see what they're about to ship before they
click Deploy. This module is authoritative — whatever it writes is
what gets deployed; the client preview is a best-effort mirror.

## Scope (v1)

- One template — "voice-only agent with skills." No watcher builder.
- No code-level editing in the Forge itself (you get a preview,
  not a textarea of the generated .py). Post-deploy editing goes
  through ``/knowledge`` on the new `pip.py`-style file.
- No overwrite. Deploying with an id that already exists errors.
- No deletion. Remove an agent by deleting its folder from
  ``/knowledge`` and restarting.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from oglab.pkb import _pkb_root

log = logging.getLogger(__name__)


# ── Slugify ────────────────────────────────────────────────────────
# The agent id has to be a valid Python identifier because it's the
# name of the singleton the loader imports. "Lab Buddy" → "lab_buddy".
# Keep it conservative: lowercase, alnum + underscore only, starts
# with a letter.

_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def slugify(name: str) -> str:
    """Name → Python-safe lowercase identifier."""
    n = (name or "").strip().lower().replace("-", "_").replace(" ", "_")
    n = _SLUG_RE.sub("", n)
    # Must start with a letter to be a valid Python identifier.
    if not n or not n[0].isalpha():
        n = "agent_" + n
    return n


def _camel(slug: str) -> str:
    """slug → ClassName (PascalCase)."""
    return "".join(part.capitalize() for part in slug.split("_")) or "Agent"


# ── Validation ────────────────────────────────────────────────────
# Keep validation permissive but enough to prevent the obvious foot-
# guns: empty names, id clashes with built-ins or output dirs, syntax
# errors in the generated code.

_RESERVED_IDS = {
    # Existing agent id
    "pip",
    # Shared output directories under lab/pkb/agents/ that would
    # clash with the loader's discovery rules.
    "research", "experiments", "synthesis", "recommendations",
}


def validate(form: Dict[str, Any]) -> Optional[str]:
    """Return an error string when the form is invalid, else None."""
    name = (form.get("name") or "").strip()
    if not name:
        return "name required"
    if len(name) > 40:
        return "name too long (max 40 chars)"
    agent_id = slugify(name)
    if agent_id in _RESERVED_IDS:
        return f"agent id {agent_id!r} is reserved"
    if (_pkb_root() / "agents" / agent_id).exists():
        return f"agent folder already exists: {agent_id}"
    voice = (form.get("voice") or "").strip()
    if not voice:
        return "voice (personality prompt) required"
    if len(voice) > 600:
        return "voice too long (max 600 chars — long prompts dilute signal)"
    tick = int(form.get("tick_interval_sec") or 90)
    if not (30 <= tick <= 3600):
        return "tick_interval_sec must be 30-3600"
    cooldown = int(form.get("global_cooldown_sec") or 300)
    if not (60 <= cooldown <= 86400):
        return "global_cooldown_sec must be 60-86400"
    return None


# ── AGENT.md generator ────────────────────────────────────────────

_AGENT_MD_TEMPLATE = """---
title: {name}
name: {name}
emoji: {emoji}
section: agents/{agent_id}
tags: [agent, {agent_id}, forged{personality_tag}]
voice: "{voice_escaped}"
tick_interval_sec: {tick}
global_cooldown_sec: {cooldown}
dream: {dream}
auto_start_env: LAB_{env_name}
skills: [{skills_list}]
forged_at: {forged_at}
---

# {name}

Forged via the Agent Forge on {forged_date}.

## Voice
{voice}

## Skills
This agent loads the following procedural knowledge on every LLM call:
{skills_bullet_list}

## Editing
- **Voice / intervals** — edit the YAML frontmatter above. Changes
  take effect on next portal restart.
- **Watchers** — edit [{agent_id}.py]({agent_id}.py) and add
  functions to the `WATCHERS` list. The template has comments
  explaining the shape.
- **Mute** — set `LAB_{env_name}=off` in `.env`.

## Memory
- [state.json](state.json) — cooldowns and counters (auto-saved).
- [decisions.md](decisions.md) — append-only log of tweaks.
- [dreams/](dreams/) — nightly reflections when `dream: true`.
"""


def generate_agent_md(form: Dict[str, Any]) -> str:
    name = (form.get("name") or "").strip()
    agent_id = slugify(name)
    emoji = (form.get("emoji") or "").strip()
    voice = (form.get("voice") or "").strip()
    tick = int(form.get("tick_interval_sec") or 90)
    cooldown = int(form.get("global_cooldown_sec") or 300)
    dream = bool(form.get("dream"))
    skills = form.get("skills") or []
    if not isinstance(skills, list):
        skills = []

    skills_list = ", ".join(str(s) for s in skills)
    if skills:
        skills_bullet_list = "\n".join(f"- `{s}`" for s in skills)
    else:
        skills_bullet_list = "(none — edit the frontmatter to add some)"

    return _AGENT_MD_TEMPLATE.format(
        name=name,
        emoji=emoji,
        agent_id=agent_id,
        voice=voice,
        voice_escaped=voice.replace('"', '\\"'),
        tick=tick,
        cooldown=cooldown,
        dream=str(dream).lower(),
        env_name=agent_id.upper(),
        skills_list=skills_list,
        skills_bullet_list=skills_bullet_list,
        personality_tag=", personality" if form.get("personality_tag") else "",
        forged_at=datetime.now(timezone.utc).isoformat(),
        forged_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )


# ── Python generator ──────────────────────────────────────────────
# The template is a voice-only agent — skills + dreams + state, no
# watchers. Users add watchers later by editing the file. The shape
# matches _builtin_pip.py so if the user reads Pip for reference
# nothing is surprising.

_AGENT_PY_TEMPLATE = '''"""{name} — {role}.

Forged {forged_date} via the Agent Forge. Voice is the personality
block below; skills load from AGENT.md and get woven into every
prompt. Watchers start empty — add functions to WATCHERS to teach
{name} what to notice.

If you\'re editing this file and want context on the overall shape,
read docs/agents-explained.md and src/oglab/agents/_builtin_pip.py.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from oglab.activity import activity_log


def _state_file() -> Path:
    from oglab.pkb import _pkb_root
    return _pkb_root() / "agents" / "{agent_id}" / "state.json"


# ══════════════════════════════════════════════════════════════════════
#  1. PERSONALITY
# ══════════════════════════════════════════════════════════════════════

NAME = {name_literal}
EMOJI = {emoji_literal}

SYSTEM_PROMPT = (
    {voice_literal}
)


# ══════════════════════════════════════════════════════════════════════
#  2. OBSERVATIONS
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Observation:
    """One fact {name} might say. Watchers produce, the loop picks."""
    watcher: str
    severity: str  # "praise" | "info" | "warn"
    fact: str
    cooldown_sec: int = 30 * 60

    def rank(self) -> int:
        return {{"praise": 3, "warn": 2, "info": 1}}.get(self.severity, 0)


# ══════════════════════════════════════════════════════════════════════
#  3. WATCHERS — teach {name} what to notice
# ══════════════════════════════════════════════════════════════════════
#
# Each watcher is a function taking no args, returning either an
# Observation or None. Example template:
#
#     def _watch_inbox() -> Optional[Observation]:
#         from oglab.pkb import _pkb_root
#         inbox = _pkb_root() / "inbox"
#         if inbox.exists() and len(list(inbox.iterdir())) > 5:
#             return Observation(
#                 watcher="inbox",
#                 severity="info",
#                 fact="inbox has more than 5 unprocessed files",
#             )
#         return None
#
# Register watchers in WATCHERS below. Without any watchers, {name}
# will emit the "online" message on start and then stay quiet.

WATCHERS: List[Callable[[], Optional[Observation]]] = [
    # Add your watchers here.
]


# ══════════════════════════════════════════════════════════════════════
#  4. SPEECH
# ══════════════════════════════════════════════════════════════════════

def _compose_prompt(fact: str) -> str:
    base = SYSTEM_PROMPT
    try:
        from oglab.skills_loader import load_agent_skills, compose_system_context
        skills = load_agent_skills({agent_id_literal})
        skill_ctx = compose_system_context(skills)
    except Exception:
        skill_ctx = ""
    sections = [base]
    if skill_ctx:
        sections.append(skill_ctx)
    sections.append(f"Observation: {{fact}}")
    sections.append(f"{{NAME}}\'s one-sentence note:")
    return "\\n\\n".join(sections)


def _voice(fact: str) -> str:
    try:
        from oglab.router import ModelRouter
    except Exception:
        return fact
    try:
        router = ModelRouter()
    except Exception:
        return fact
    try:
        response = router.complete(
            _compose_prompt(fact), max_tokens=60, temperature=0.6
        )
        text = (response.text or "").strip().strip(\'"\').strip("\'")
        if text.lower().startswith(NAME.lower() + ":"):
            text = text[len(NAME) + 1:].strip()
        if len(text) > 200:
            text = text[:197] + "…"
        return text or fact
    except Exception:
        return fact


# ══════════════════════════════════════════════════════════════════════
#  5. LOOP
# ══════════════════════════════════════════════════════════════════════

class {class_name}:
    """Background task that ticks every {tick}s and occasionally
    says something worth noting in the activity feed."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._status = "idle"
        self._last_said: Dict[str, float] = {{}}
        self._last_global: float = 0.0
        self._utterances: int = 0

    @property
    def status(self) -> str:
        return self._status

    def _load_state(self) -> None:
        path = _state_file()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            self._last_said = dict(data.get("last_said") or {{}})
            self._last_global = float(data.get("last_global") or 0.0)
            self._utterances = int(data.get("utterances") or 0)
        except Exception:
            pass

    def _save_state(self) -> None:
        path = _state_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({{
                "last_said": self._last_said,
                "last_global": self._last_global,
                "utterances": self._utterances,
            }}, indent=2))
        except OSError:
            pass

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._load_state()
        self._status = "running"
        self._task = asyncio.create_task(self._run())
        activity_log.emit(
            {agent_id_literal},
            f"{{EMOJI}} {{NAME}} is online.",
            "info",
        )

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._status = "idle"

    async def _run(self) -> None:
        interval = max(30, int(os.getenv("LAB_{env_name}_INTERVAL_SEC", "{tick}")))
        global_cooldown = max(
            60, int(os.getenv("LAB_{env_name}_COOLDOWN_SEC", "{cooldown}"))
        )
        try:
            while True:
                await asyncio.sleep(interval)
                self._maybe_speak(global_cooldown)
        except asyncio.CancelledError:
            return

    def _maybe_speak(self, global_cooldown: int) -> None:
        now = time.time()
        if now - self._last_global < global_cooldown:
            return
        candidates: List[Observation] = []
        for watcher in WATCHERS:
            try:
                obs = watcher()
            except Exception:
                continue
            if obs is None:
                continue
            last = self._last_said.get(obs.watcher, 0.0)
            if now - last < obs.cooldown_sec:
                continue
            candidates.append(obs)
        if not candidates:
            return
        candidates.sort(key=lambda o: o.rank(), reverse=True)
        chosen = candidates[0]
        sentence = _voice(chosen.fact)
        level = {{"praise": "success", "warn": "warn"}}.get(chosen.severity, "info")
        activity_log.emit(
            {agent_id_literal},
            f"{{EMOJI}} {{NAME}}: {{sentence}}",
            level,
            data={{
                "watcher": chosen.watcher,
                "severity": chosen.severity,
                "fact": chosen.fact,
            }},
        )
        self._last_said[chosen.watcher] = now
        self._last_global = now
        self._utterances += 1
        self._save_state()

    async def dream(self) -> str:
        """Nightly reflection stub — returns empty until a real
        implementation lands. To enable: pattern-copy the dream()
        method from src/oglab/agents/_builtin_pip.py."""
        return ""


{agent_id} = {class_name}()
'''


def generate_agent_py(form: Dict[str, Any]) -> str:
    name = (form.get("name") or "").strip()
    agent_id = slugify(name)
    emoji = (form.get("emoji") or "").strip()
    voice = (form.get("voice") or "").strip()
    tick = int(form.get("tick_interval_sec") or 90)
    cooldown = int(form.get("global_cooldown_sec") or 300)
    role = (form.get("role") or "forged agent").strip()

    return _AGENT_PY_TEMPLATE.format(
        name=name,
        name_literal=repr(name),
        emoji_literal=repr(emoji),
        agent_id=agent_id,
        agent_id_literal=repr(agent_id),
        class_name=_camel(agent_id) + "Agent",
        voice_literal=repr(voice),
        tick=tick,
        cooldown=cooldown,
        env_name=agent_id.upper(),
        role=role,
        forged_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )


# ── Decisions log starter ─────────────────────────────────────────

_DECISIONS_MD = """---
title: {name} — Decisions
section: agents/{agent_id}
tags: [agent, {agent_id}, decisions]
---

# {name} — Decision Log

Append-only record of meaningful choices about this agent. Format:
`YYYY-MM-DD — what changed — why`.

- {forged_date} — Forged via the Agent Forge.
"""


def generate_decisions_md(form: Dict[str, Any]) -> str:
    name = (form.get("name") or "").strip()
    return _DECISIONS_MD.format(
        name=name,
        agent_id=slugify(name),
        forged_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )


# ── Deploy ────────────────────────────────────────────────────────
# The money function. Validates, writes the folder, tries to hot-
# load the agent, starts it, registers dream if opted in. Returns a
# status dict the API echoes back to the UI.

def deploy(form: Dict[str, Any]) -> Dict[str, Any]:
    """Write the agent folder + hot-load. Returns a status dict.

    Success shape:
        {"ok": True, "agent_id": "owl", "hot_loaded": True,
         "folder": "lab/pkb/agents/owl"}

    Failure:
        {"ok": False, "error": "<message>"}
    """
    err = validate(form)
    if err:
        return {"ok": False, "error": err}

    name = form["name"].strip()
    agent_id = slugify(name)
    folder = _pkb_root() / "agents" / agent_id

    # Generate everything up-front so a failure during one file
    # doesn't leave a half-written folder.
    try:
        md = generate_agent_md(form)
        py = generate_agent_py(form)
        decisions = generate_decisions_md(form)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"codegen failed: {type(e).__name__}: {e}"}

    # Parse the generated Python to catch template bugs before we
    # write to disk. Users should never see a syntax error on Deploy.
    try:
        ast.parse(py)
    except SyntaxError as e:
        return {"ok": False, "error": f"generated code has syntax error: {e}"}

    # Write folder.
    try:
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "AGENT.md").write_text(md)
        (folder / f"{agent_id}.py").write_text(py)
        (folder / "decisions.md").write_text(decisions)
        (folder / "dreams").mkdir(exist_ok=True)
        (folder / "dreams" / ".gitkeep").write_text("")
    except FileExistsError:
        return {"ok": False, "error": f"agent folder already exists: {folder}"}
    except OSError as e:
        return {"ok": False, "error": f"write failed: {e}"}

    # Try to hot-load so the new agent is live without a restart.
    hot_loaded = False
    started = False
    try:
        from oglab.agents.loader import load_one, start_all_auto
        instance = load_one(agent_id)
        if instance is not None:
            hot_loaded = True
            # Run through the same auto-start path shipped agents use.
            start_all_auto({agent_id: instance})
            if hasattr(instance, "status") and instance.status == "running":
                started = True
    except Exception as e:  # noqa: BLE001
        log.warning("hot-load of %s failed: %s", agent_id, e)

    return {
        "ok": True,
        "agent_id": agent_id,
        "folder": str(folder),
        "hot_loaded": hot_loaded,
        "started": started,
    }
