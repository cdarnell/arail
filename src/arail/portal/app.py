"""Arail Portal — local web dashboard served at arail.local."""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, AsyncIterator, Iterator, cast

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from arail.activity import activity_log
from arail.agent_redirects import clear_agent_redirect, get_agent_redirect, set_agent_redirect
from arail.agent_workflows import get_agent_workflow, list_agent_workflows
from arail.agents.consent import ConsentStore
from arail.config import DATA_DIR
from arail.goals import GoalStore
from arail.agents.researcher import researcher
from arail.agents.pip import pip
from arail.plugins.manager import PluginManager
from arail.scheduler import (halt_all_jobs, jobs_halted, resume_all_jobs,
                              startup_delay_seconds)
from arail.scheduler import state as scheduler_state
from arail.skills.goal_parser import GoalParser
from arail.skills.experiment_tracker import ExperimentTracker
from arail.router.backends import BACKEND_MAP
from arail.portal.wiki_routes import router as wiki_router

from arail.brand import load_brand
from arail.router.backends import ModelResponse
from arail.ui_theme import list_ui_themes, load_ui_theme, theme_css

_BRAND = load_brand()
_UI_THEME = load_ui_theme()

# Tier gating — the nav shows only the surfaces matching the current tier.
# Two tiers: min (everyday) and max (full bench). Upgrade with ./arail upgrade max.
_TIER_SURFACES: dict[str, set[str]] = {
    "min": {"dashboard", "chat", "research", "knowledge", "agents"},
    "max": {"dashboard", "chat", "research", "knowledge", "agents",
            "admin", "docs", "notebooks", "terminal", "tuning", "plugins"},
}


def _current_tier() -> str:
    tier = os.getenv("LAB_TIER", "min").strip().lower()
    return tier if tier in _TIER_SURFACES else "min"


def _visible_surfaces() -> set[str]:
    return _TIER_SURFACES[_current_tier()]


# ── First-run onboarding state ───────────────────────────────────────
# When ARAIL_PASSWORD isn't set (or is a placeholder), the portal
# refuses to render any tab and redirects to /welcome instead. The
# user picks a passphrase in the browser; the welcome endpoint writes
# it to .env, lab.conf, and ~/.config/code-server/config.yaml. After
# that, the lab unlocks for normal use.
#
# Placeholder values that count as "not set yet":
_PASSWORD_PLACEHOLDERS = {"", "change-me", "__needs_setup__"}


def _lab_password_set() -> bool:
    """True if a real ARAIL_PASSWORD is configured.

    Reads the live env var, then falls back to the .env file on disk
    so a fresh write from /api/welcome/setup unlocks the next request
    without requiring a process restart.
    """
    val = (os.getenv("ARAIL_PASSWORD") or "").strip()
    if val and val not in _PASSWORD_PLACEHOLDERS:
        return True
    # Fall back to the file on disk (covers the post-onboarding window
    # before the running process re-reads the env).
    env_path = Path(".env")
    if env_path.exists():
        try:
            for line in env_path.read_text().splitlines():
                if line.startswith("ARAIL_PASSWORD="):
                    file_val = line.split("=", 1)[1].strip()
                    if file_val and file_val not in _PASSWORD_PLACEHOLDERS:
                        # Pull the just-written value into the live env so
                        # downstream getenv calls see it too.
                        os.environ["ARAIL_PASSWORD"] = file_val
                        return True
                    return False
        except OSError:
            pass
    return False


app = FastAPI(title=_BRAND.name, docs_url="/api/docs")


@app.middleware("http")
async def onboarding_gate(request, call_next):
    """Block all surfaces until the operator has set a passphrase.

    Lets through:
      - /welcome and /api/welcome/* (the onboarding flow itself)
      - /static/* (so the welcome page can load CSS)
      - /api/system/health (so health checks keep working pre-onboarding)
      - /favicon.ico
    HTML routes get a 302 to /welcome; API routes get a 401 with a hint.
    """
    if _lab_password_set():
        return await call_next(request)

    path = request.url.path
    allowed_prefixes = (
        "/welcome",
        "/api/welcome",
        "/static/",
        "/api/system/health",
        "/favicon.ico",
    )
    if any(path == p or path.startswith(p) for p in allowed_prefixes):
        return await call_next(request)

    # API call → JSON error so the caller sees a clean signal.
    if path.startswith("/api/") or request.headers.get("accept", "").startswith("application/json"):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"error": "lab_not_onboarded",
             "detail": "Set the lab passphrase via POST /api/welcome/setup or open / in a browser."},
            status_code=401,
        )

    # HTML → bounce to the welcome page.
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/welcome", status_code=302)


app.include_router(wiki_router)

PORTAL_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=PORTAL_DIR / "static"), name="static")
# Mount integrations frontend (core/knowledge-canvas/frontend) if present.
KC_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "core" / "knowledge-canvas" / "frontend"
KC_FRONTEND_DIST_DIR = KC_FRONTEND_DIR / "dist"
KC_BACKEND_DIR = Path(__file__).resolve().parents[3] / "core" / "knowledge-canvas" / "backend"
knowledge_canvas_app: Any = None
_knowledge_canvas_store = None
if KC_FRONTEND_DIST_DIR.exists() or KC_FRONTEND_DIR.exists():
    kc_static_dir = KC_FRONTEND_DIST_DIR if KC_FRONTEND_DIST_DIR.exists() else KC_FRONTEND_DIR
    app.mount("/_integrations/knowledge-canvas",
              StaticFiles(directory=kc_static_dir),
              name="integrations_kc_static")

# Optional: mount imported knowledge-canvas backend under /knowledge-canvas
# so its native graph/source/nlq routes are available without replacing
# Arail's own API surface.
if KC_BACKEND_DIR.exists():
    try:
        kc_backend = str(KC_BACKEND_DIR)
        if kc_backend not in sys.path:
            sys.path.insert(0, kc_backend)
        from app.main import app as knowledge_canvas_app  # type: ignore
        app.mount("/knowledge-canvas", cast(Any, knowledge_canvas_app))
    except Exception as e:  # noqa: BLE001
        activity_log.emit("system",
                          f"Knowledge Canvas backend mount skipped: {type(e).__name__}: {e}",
                          "warn")

templates = Jinja2Templates(directory=PORTAL_DIR / "templates")
# Expose the brand + tier info to every Jinja template — so `{{ brand.name }}`
# and `{{ tier_surfaces }}` work everywhere without each route passing them.
templates.env.globals["brand"] = _BRAND
templates.env.globals["tier_surfaces"] = _visible_surfaces()
templates.env.globals["lab_tier"] = _current_tier()
templates.env.globals["ui_theme"] = _UI_THEME
templates.env.globals["ui_themes"] = list_ui_themes()
templates.env.globals["ui_theme_css"] = theme_css(_UI_THEME)

consent_store = ConsentStore()
goal_store = GoalStore()
tracker = ExperimentTracker()
parser = GoalParser()
plugin_mgr = PluginManager()


@app.on_event("startup")
async def _startup():
    import os
    global _knowledge_canvas_store
    intent_name = os.getenv("LAB_INTENT_NAME", "AI Engineer")
    activity_log.emit("system",
                      f"{_BRAND.name} portal started — {intent_name} lab.",
                      "success")

    if knowledge_canvas_app is not None and not hasattr(knowledge_canvas_app.state, "store"):
        try:
            from app.routers import ws as kc_ws  # type: ignore
            from app.services.graph_store import GraphStore  # type: ignore

            _knowledge_canvas_store = GraphStore(
                lance_path=os.getenv("LANCE_PATH", "./data/lance"),
                neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                neo4j_auth=(
                    os.getenv("NEO4J_USER", "neo4j"),
                    os.getenv("NEO4J_PASSWORD", "changeme-please"),
                ),
            )
            await _knowledge_canvas_store.init()
            knowledge_canvas_app.state.store = _knowledge_canvas_store
            knowledge_canvas_app.state.ws_broadcaster = kc_ws.broadcaster
            activity_log.emit("system", "Knowledge Canvas backend ready.", "info")
        except Exception as e:  # noqa: BLE001
            _knowledge_canvas_store = None
            activity_log.emit(
                "system",
                f"Knowledge Canvas startup skipped: {type(e).__name__}: {e}",
                "warn",
            )

    asyncio.create_task(_warm_primary_router())

    # Load bootstrap goal if no active goal exists
    current = goal_store.get_current()
    if not current:
        from arail.config import DATA_DIR
        bootstrap_goal_path = DATA_DIR / "goals" / "bootstrap_goal.json"
        if bootstrap_goal_path.exists():
            try:
                bg = json.loads(bootstrap_goal_path.read_text())
                goal_text = bg.get("goal", "")
                if goal_text:
                    try:
                        parsed = parser.parse(goal_text)
                    except Exception:
                        parsed = parser.parse_offline(goal_text)
                    # Carry intent from bootstrap
                    parsed["intent"] = bg.get("intent", os.getenv("LAB_INTENT", "ai"))
                    parsed["intent_name"] = bg.get("intent_name", intent_name)
                    goal_store.set_goal(parsed)
                    activity_log.emit("system",
                        f"Bootstrap goal loaded: {goal_text[:80]}", "info")
                    # Auto-start research — scheduler applies the courtesy delay.
                    researcher.start(parsed)
                    delay = startup_delay_seconds()
                    activity_log.emit("researcher",
                        f"Auto-starting research in {delay}s (courtesy delay). "
                        f"Use 'Halt jobs' to cancel.",
                        "info")
            except (json.JSONDecodeError, OSError) as e:
                activity_log.emit("system",
                    f"Failed to load bootstrap goal: {type(e).__name__}: {e}. "
                    f"Set a goal from the dashboard instead.",
                    "error")

    if not goal_store.get_current():
        activity_log.emit("system",
            "Welcome to Arail. Type a goal above to begin — the researcher agent will take it from there.",
            "info")
        activity_log.emit("system",
            "Tip: Goals can be anything — 'grow peanuts in zone 7', 'build a trading bot', 'learn Rust'.",
            "info")

    # Starter-pack seeding — idempotent. On a fresh lab this populates
    # lab/pkb/sources/seeds/model-building/ with 9 curated primers so
    # the researcher + curator have something to read on their first
    # tick. On every subsequent start it's a no-op.
    try:
        from arail.pkb_seed import seed_all_on_startup
        seed_summary = seed_all_on_startup()
        if seed_summary.get("installed_packs"):
            activity_log.emit("pkb",
                f"Seeded starter pack(s): {', '.join(seed_summary['installed_packs'])}",
                "info")
        for err in seed_summary.get("errors", []):
            activity_log.emit("pkb", f"Seed error: {err}", "warn")
    except Exception as e:  # noqa: BLE001
        activity_log.emit("pkb",
            f"Starter-pack seeding failed: {type(e).__name__}: {e}", "error")

    # Skill seed — shipped procedural-knowledge starters under
    # lab/pkb/skills/. Idempotent. Agents that list these skills in
    # their AGENT.md pick them up on the next LLM call.
    try:
        from arail.skill_seed import ensure_starter_skills
        skill_summary = ensure_starter_skills()
        if skill_summary.get("installed"):
            activity_log.emit("pkb",
                f"Seeded starter skills: {', '.join(skill_summary['installed'])}",
                "info")
    except Exception as e:  # noqa: BLE001
        activity_log.emit("pkb",
            f"Skill seeding failed: {type(e).__name__}: {e}", "error")

    # Default loadouts — write AGENT.md scaffolds for builtin agents
    # that lack one. Pip ships its own (richer) AGENT.md via
    # builtin_seed; researcher / curator / browser get default
    # skill loadouts here so the Skills tab can show + edit them.
    # Idempotent — never overwrites user edits.
    try:
        from arail.agent_seed import ensure_default_loadouts
        loadout_summary = ensure_default_loadouts()
        if loadout_summary.get("written"):
            activity_log.emit("pkb",
                f"Seeded agent loadouts: {', '.join(loadout_summary['written'])}",
                "info")
    except Exception as e:  # noqa: BLE001
        activity_log.emit("pkb",
            f"Agent loadout seeding failed: {type(e).__name__}: {e}", "error")

    # Research program seed — the lab ships with "optimize AeroLLM"
    # pre-loaded so a fresh install has a meaningful research goal
    # the moment the portal comes up. User edits program.md to steer
    # the researcher elsewhere.
    try:
        from arail.agents.builtin_seed import ensure_research_files
        r = ensure_research_files()
        if r.get("written"):
            activity_log.emit("pkb",
                f"Seeded research program: {', '.join(r['written'])}",
                "info")
    except Exception as e:  # noqa: BLE001
        activity_log.emit("pkb",
            f"Research program seeding failed: {type(e).__name__}: {e}", "error")

    # Agent loader — discover every lab/pkb/agents/<name>/AGENT.md,
    # instantiate each, start the ones that opt in via their
    # auto_start_env, register dream-capable ones with the daemon.
    # This subsumes the old "start Pip explicitly" path and works
    # for every future agent the user forges.
    try:
        from arail.agents.loader import load_all, start_all_auto
        agents = load_all()
        activity_log.emit(
            "agents",
            f"Agent loader discovered {len(agents)}: {', '.join(agents) or 'none'}",
            "info",
        )
        start_all_auto(agents)
    except Exception as e:  # noqa: BLE001
        activity_log.emit("agents",
            f"Agent loader failed: {type(e).__name__}: {e}", "error")

    # Dream daemon — nightly reflection loop. The loader above
    # already registered every dream-capable agent; here we just
    # flip the scheduler on (or off via LAB_DREAMS=off).
    if os.getenv("LAB_DREAMS", "on").lower() not in ("off", "0", "false", "no"):
        try:
            from arail.agents.dream_daemon import dream_daemon
            dream_daemon.start()
        except Exception as e:  # noqa: BLE001
            activity_log.emit("dream",
                f"Dream daemon failed to start: {type(e).__name__}: {e}",
                "warn")


@app.on_event("shutdown")
async def _shutdown():
    global _knowledge_canvas_store
    if _knowledge_canvas_store is not None:
        try:
            await _knowledge_canvas_store.close()
        finally:
            _knowledge_canvas_store = None


# ── First-run welcome / passphrase setup ─────────────────────────────────

@app.get("/welcome", response_class=HTMLResponse)
async def welcome_page(request: Request):
    """First-run onboarding form. Allowed by the middleware regardless
    of password state, so a fresh lab can land here on first open."""
    # If they're already onboarded, send them home — nothing to do here.
    if _lab_password_set():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "welcome.html", {
        "current_lab_name": os.getenv("LAB_NAME", _BRAND.name),
    })


@app.post("/api/welcome/setup")
async def api_welcome_setup(request: Request):
    """Accept the first-run passphrase, write it everywhere it's needed.

    Locked to the no-password state so this can never overwrite an
    existing passphrase without explicit auth. Once a real ARAIL_PASSWORD
    exists, this endpoint refuses with 409 — rotate via the dashboard
    settings or by editing .env directly.
    """
    if _lab_password_set():
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"ok": False,
             "error": "lab is already onboarded; rotate via .env or dashboard settings"},
            status_code=409,
        )

    body = await request.json()
    passphrase = (body.get("passphrase") or "").strip()
    confirm    = (body.get("confirm") or "").strip()
    lab_name   = (body.get("lab_name") or "").strip()

    if len(passphrase) < 8:
        return {"ok": False, "error": "passphrase must be at least 8 characters"}
    if passphrase != confirm:
        return {"ok": False, "error": "passphrases don't match"}
    if passphrase in _PASSWORD_PLACEHOLDERS:
        return {"ok": False, "error": "passphrase looks like a placeholder; pick something real"}

    # Write to .env using the same helper setup.sh uses (Python-driven,
    # idempotent, replaces existing lines without duplicating them).
    _write_env_kv("ARAIL_PASSWORD", passphrase)
    _write_env_kv("OPEN_NOTEBOOK_ENCRYPTION_KEY", passphrase)
    if lab_name:
        _write_env_kv("LAB_NAME", lab_name)
        short = lab_name.lower()
        _write_env_kv("LAB_SHORT_NAME", short)

    # Update lab.conf — IDE_PASSWORD is the value tmux + start.sh hand
    # to ttyd / code-server. Same shape as setup.sh writes.
    _patch_lab_conf_password(passphrase)

    # Code-server config — overwritten so the IDE on :8443 unlocks with
    # the new passphrase. This file lives outside the repo at
    # ~/.config/code-server/config.yaml. Setup.sh writes the same yaml.
    try:
        _write_code_server_password(passphrase)
        ide_written = True
    except OSError as exc:
        ide_written = False
        activity_log.emit("system",
            f"code-server config write failed ({type(exc).__name__}); "
            f"IDE on :8443 will not be unlockable until you re-run setup.",
            "warn")

    # Refresh the live env so the next request sees the new password
    # without waiting for the file-fallback in _lab_password_set().
    os.environ["ARAIL_PASSWORD"] = passphrase
    os.environ["OPEN_NOTEBOOK_ENCRYPTION_KEY"] = passphrase
    if lab_name:
        os.environ["LAB_NAME"] = lab_name

    activity_log.emit("system",
        f"Lab onboarded via /welcome — passphrase set"
        f"{' and lab renamed to ' + lab_name if lab_name else ''}.",
        "success")

    return {"ok": True, "ide_written": ide_written}


def _write_env_kv(key: str, value: str) -> None:
    """Idempotent KEY=VALUE write to .env. Replaces any existing real or
    commented-out entry, otherwise appends. Mirrors setup.sh's helper."""
    p = Path(".env")
    lines = p.read_text().splitlines() if p.exists() else []
    prefix = f"{key}="

    def _is_assignment(line: str) -> bool:
        if line.startswith(prefix):
            return True
        # match `#KEY=` (commented-out default) but NOT `# KEY=` (docstring)
        if line.startswith("#") and not line.startswith("# "):
            return line.lstrip("#").startswith(prefix)
        return False

    out, replaced = [], False
    for line in lines:
        if not replaced and _is_assignment(line):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        if out and out[-1] != "":
            out.append("")
        out.append(f"{key}={value}")
    p.write_text("\n".join(out) + "\n")


def _patch_lab_conf_password(passphrase: str) -> None:
    """Update IDE_PASSWORD in lab.conf in place (or write a fresh one)."""
    p = Path("lab.conf")
    if not p.exists():
        # No lab.conf yet — write the minimum shape setup.sh would emit.
        p.write_text(
            "# Arail runtime config — created by /api/welcome/setup\n"
            "PORTAL_PORT=8080\n"
            "TERMINAL_PORT=7681\n"
            "NOTEBOOK_PORT=8888\n"
            "IDE_PORT=8443\n"
            f"IDE_PASSWORD={passphrase}\n"
            "BIND_ADDR=127.0.0.1\n"
        )
        return
    lines = p.read_text().splitlines()
    out, replaced = [], False
    for line in lines:
        if line.startswith("IDE_PASSWORD="):
            out.append(f"IDE_PASSWORD={passphrase}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"IDE_PASSWORD={passphrase}")
    p.write_text("\n".join(out) + "\n")


def _write_code_server_password(passphrase: str) -> None:
    """Write ~/.config/code-server/config.yaml so the IDE unlocks with
    the new passphrase. Same yaml shape setup.sh writes."""
    cfg_dir = Path.home() / ".config" / "code-server"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = cfg_dir / "config.yaml"
    cfg.write_text(
        "bind-addr: 127.0.0.1:8443\n"
        "auth: password\n"
        f"password: {passphrase}\n"
        "cert: false\n"
    )


# ── Pages ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    experiments = tracker.list_all()
    allowed_domains = consent_store.list_allowed()
    pending = consent_store.list_pending()
    current_goal = goal_store.get_current()
    return templates.TemplateResponse(request, "dashboard.html", {
        "experiments": experiments,
        "allowed_domains": allowed_domains,
        "pending_requests": pending,
        "current_goal": current_goal,
        "research_status": researcher.status,
        "recent_activity": activity_log.recent(30),
        # LAB_THEME surfaces on the Mission Objective card as a
        # north-star line above the concrete goal. Env-driven so
        # users reframe the whole lab's focus with one .env edit.
        "lab_theme": os.getenv(
            "LAB_THEME",
            "Making SSD-hosted model inference faster — frontier "
            "open-weight models on laptop hardware"
        ),
    })


@app.get("/mission", response_class=HTMLResponse)
async def mission_page(request: Request):
    current_goal = goal_store.get_current()
    return templates.TemplateResponse(request, "mission.html", {
        "current_goal": current_goal,
        "research_status": researcher.status,
        "recent_activity": activity_log.recent(40),
        "lab_theme": os.getenv(
            "LAB_THEME",
            "Making SSD-hosted model inference faster — frontier "
            "open-weight models on laptop hardware"
        ),
    })


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    embed = request.query_params.get("embed", "").lower() in {
        "1", "true", "yes", "on"
    }
    return templates.TemplateResponse(request, "chat.html", {"embed": embed})


# ─── Chat compute-source pivot ───────────────────────────────────────────
# The Chat tab lets the operator flip between "my machine" and several cloud
# vendors without editing .env. Tokens persist to lab/data/secrets.env with
# 0600 perms (never logged, never echoed back).
#
# Airgapped guard: when LAB_MODE=airgapped (the default), every cloud
# provider operation is blocked at the API layer. Only "my_machine" works.
# Flip LAB_MODE=hybrid in .env to enable external vendors.
_PROVIDER_KEY_ENVS: dict[str, str] = {
    "claude":      "ANTHROPIC_API_KEY",
    "nvidia":      "NVIDIA_API_KEY",
    "openrouter":  "OPENROUTER_API_KEY",
    "huggingface": "HF_TOKEN",
    "custom":      "MODEL_API_KEY",
}

# Per-provider metadata the UI uses to render the Manage Providers modal and
# the /test + /models calls dispatch against.
_PROVIDER_META: dict[str, dict[str, str]] = {
    "claude": {
        "label": "Claude (Anthropic)",
        "base": "https://api.anthropic.com/v1",
        "models_path": "/models",
        "auth": "x-api-key",
        "docs": "https://console.anthropic.com/settings/keys",
    },
    "nvidia": {
        "label": "NVIDIA NIM",
        "base": "https://integrate.api.nvidia.com/v1",
        "models_path": "/models",
        "auth": "bearer",
        "docs": "https://build.nvidia.com/",
    },
    "openrouter": {
        "label": "OpenRouter",
        "base": "https://openrouter.ai/api/v1",
        "models_path": "/models",
        "auth": "bearer",
        "docs": "https://openrouter.ai/keys",
    },
    "huggingface": {
        "label": "HuggingFace Inference",
        "base": "https://api-inference.huggingface.co",
        "models_path": "",     # HF uses a different catalogue endpoint; skip list
        "auth": "bearer",
        "docs": "https://huggingface.co/settings/tokens",
    },
    "custom": {
        "label": "Custom (OpenAI-compatible)",
        "base": "",
        "models_path": "/models",
        "auth": "bearer",
        "docs": "",
    },
}

_CLOUD_PROVIDERS: set[str] = set(_PROVIDER_KEY_ENVS.keys())


def _lab_mode() -> str:
    return os.getenv("LAB_MODE", os.getenv("ARAIL_MODE", "airgapped")).strip().lower()


def _is_airgapped() -> bool:
    return _lab_mode() != "hybrid"


def _secrets_path() -> Path:
    return DATA_DIR / "secrets.env"


def _read_secrets() -> dict[str, str]:
    p = _secrets_path()
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def _write_secrets(pairs: dict[str, str]) -> None:
    p = _secrets_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    body = ["# Auto-generated by Arail Chat > Manage Providers.",
            "# This file is git-ignored and chmod 0600. Do not share.",
            ""]
    for k, v in sorted(pairs.items()):
        body.append(f"{k}={v}")
    p.write_text("\n".join(body) + "\n")
    try:
        p.chmod(0o600)
    except OSError:
        pass


def _load_active_provider() -> str:
    provider = os.getenv("COMPUTE_SOURCE", "").strip().lower()
    if provider in {"my_machine", *_CLOUD_PROVIDERS}:
        return provider
    return "my_machine"


def _provider_token(provider: str) -> str:
    env = _PROVIDER_KEY_ENVS.get(provider)
    if not env:
        return ""
    return (_read_secrets().get(env) or os.getenv(env) or "").strip()


@app.get("/api/providers/status")
async def providers_status():
    """Return current compute source, per-provider token presence, lab mode,
    and a human-readable reason when cloud is locked out."""
    secrets = _read_secrets()
    known = {
        name: bool(secrets.get(env) or os.getenv(env))
        for name, env in _PROVIDER_KEY_ENVS.items()
    }
    known["my_machine"] = True
    mode = _lab_mode()
    return {
        "provider": _load_active_provider(),
        "available": known,
        "lab_mode": mode,
        "cloud_enabled": not _is_airgapped(),
        "airgapped_notice": (
            "Lab is in airgapped mode. Only My Machine is usable. "
            "To enable cloud providers, set LAB_MODE=hybrid in .env and restart."
        ) if _is_airgapped() else "",
        "providers": [
            {
                "id": pid,
                "label": meta["label"],
                "docs": meta.get("docs", ""),
                "has_token": known.get(pid, False),
                "base": meta.get("base", ""),
                "supports_models_list": bool(meta.get("models_path")),
            }
            for pid, meta in _PROVIDER_META.items()
        ],
    }


@app.post("/api/providers/save")
async def providers_save(request: Request):
    """Persist a provider token to lab/data/secrets.env (chmod 0600).
    Blocked in airgapped mode for every cloud provider."""
    body = await request.json()
    provider = (body.get("provider") or "").strip().lower()
    token = (body.get("token") or "").strip()
    endpoint = (body.get("endpoint") or "").strip()
    if provider == "my_machine":
        return {"ok": True, "note": "local — no token needed"}
    if provider not in _CLOUD_PROVIDERS:
        return {"ok": False, "error": f"unknown provider '{provider}'"}
    if _is_airgapped():
        return {"ok": False,
                "error": "Airgapped mode blocks cloud provider setup. Set LAB_MODE=hybrid in .env to enable."}
    if not token and provider != "custom":
        return {"ok": False, "error": "empty token"}

    secrets = _read_secrets()
    if token:
        secrets[_PROVIDER_KEY_ENVS[provider]] = token
        os.environ[_PROVIDER_KEY_ENVS[provider]] = token
    if provider == "custom" and endpoint:
        secrets["MODEL_API_BASE"] = endpoint
        os.environ["MODEL_API_BASE"] = endpoint
    _write_secrets(secrets)
    activity_log.emit("chat", f"Saved provider token for {provider}.", "success")
    return {"ok": True}


@app.post("/api/providers/remove")
async def providers_remove(request: Request):
    """Delete a saved provider token. Works in either mode."""
    body = await request.json()
    provider = (body.get("provider") or "").strip().lower()
    if provider not in _CLOUD_PROVIDERS:
        return {"ok": False, "error": f"unknown provider '{provider}'"}
    secrets = _read_secrets()
    env_key = _PROVIDER_KEY_ENVS[provider]
    removed = secrets.pop(env_key, None) is not None
    if env_key in os.environ:
        os.environ.pop(env_key, None)
        removed = True
    if provider == "custom":
        secrets.pop("MODEL_API_BASE", None)
        os.environ.pop("MODEL_API_BASE", None)
    _write_secrets(secrets)
    activity_log.emit("chat", f"Removed provider token for {provider}.", "warn")
    return {"ok": True, "removed": removed}


@app.post("/api/providers/active")
async def providers_active(request: Request):
    """Switch the active compute source. Airgapped mode locks to my_machine."""
    body = await request.json()
    provider = (body.get("provider") or "").strip().lower()
    if provider not in {"my_machine", *_CLOUD_PROVIDERS}:
        return {"ok": False, "error": f"unknown provider '{provider}'"}
    if provider != "my_machine" and _is_airgapped():
        return {"ok": False,
                "error": "Airgapped mode — only My Machine is active. Set LAB_MODE=hybrid to use cloud providers."}
    os.environ["COMPUTE_SOURCE"] = provider
    activity_log.emit("chat", f"Compute source switched to '{provider}'.", "info")
    return {"ok": True, "provider": provider}


def _auth_headers(provider: str, token: str) -> dict[str, str]:
    meta = _PROVIDER_META.get(provider, {})
    headers = {"Accept": "application/json"}
    if meta.get("auth") == "x-api-key":
        headers["x-api-key"] = token
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@app.post("/api/providers/test")
async def providers_test(request: Request):
    """Ping a provider to verify the saved token authenticates. Blocked
    in airgapped mode."""
    body = await request.json()
    provider = (body.get("provider") or "").strip().lower()
    if provider not in _CLOUD_PROVIDERS:
        return {"ok": False, "error": f"unknown provider '{provider}'"}
    if _is_airgapped():
        return {"ok": False, "error": "Airgapped — cloud test blocked."}
    token = _provider_token(provider)
    if not token:
        return {"ok": False, "error": "no saved token for this provider"}

    meta = _PROVIDER_META[provider]
    base = meta.get("base") or os.getenv("MODEL_API_BASE", "")
    models_path = meta.get("models_path") or "/models"
    if not base:
        return {"ok": False, "error": "no endpoint configured"}
    url = base.rstrip("/") + models_path

    import requests  # lazy — keeps portal startup fast
    try:
        r = requests.get(url, headers=_auth_headers(provider, token), timeout=8)
        ok = 200 <= r.status_code < 300
        return {"ok": ok, "status": r.status_code,
                "message": "authenticated" if ok else f"HTTP {r.status_code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@app.get("/api/providers/models")
async def providers_models(provider: str):
    """List available models for a provider (when it supports /models).
    Blocked in airgapped mode; capped at 200 entries for sanity."""
    provider = provider.strip().lower()
    if provider not in _CLOUD_PROVIDERS:
        return {"ok": False, "error": f"unknown provider '{provider}'"}
    if _is_airgapped():
        return {"ok": False, "error": "Airgapped — cloud catalogue blocked."}
    meta = _PROVIDER_META[provider]
    if not meta.get("models_path"):
        return {"ok": False, "error": f"{provider} has no /models endpoint — use the vendor docs."}
    token = _provider_token(provider)
    if not token:
        return {"ok": False, "error": "no saved token for this provider"}
    base = meta.get("base") or os.getenv("MODEL_API_BASE", "")
    if not base:
        return {"ok": False, "error": "no endpoint configured"}
    url = base.rstrip("/") + meta["models_path"]

    import requests
    try:
        r = requests.get(url, headers=_auth_headers(provider, token), timeout=12)
        if not (200 <= r.status_code < 300):
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        payload = r.json()
        raw = payload.get("data") or payload.get("models") or payload
        models: list[str] = []
        if isinstance(raw, list):
            for item in raw[:200]:
                if isinstance(item, str):
                    models.append(item)
                elif isinstance(item, dict):
                    models.append(str(item.get("id") or item.get("name") or item))
        return {"ok": True, "models": models, "count": len(models)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def _ttyd_context() -> dict:
    """Compute ttyd availability for use in any route that needs it."""
    import shutil, platform
    installed = shutil.which("ttyd") is not None
    running = False
    if installed:
        running = await _port_open(
            os.getenv("BIND_ADDR", "127.0.0.1"),
            int(os.getenv("TTYD_PORT", "7681")),
        )
    install_cmd = {
        "Darwin": "brew install ttyd",
        "Linux": "sudo apt install ttyd  # Debian/Ubuntu\n"
                 "sudo dnf install ttyd  # Fedora\n"
                 "sudo pacman -S ttyd    # Arch\n"
                 "sudo emerge -av www-apps/ttyd  # Gentoo",
    }.get(platform.system(), "https://github.com/tsl0922/ttyd#installation")
    return {
        "ttyd_installed": installed,
        "ttyd_running": running,
        "ttyd_port": int(os.getenv("TTYD_PORT", "7681")),
        "install_cmd": install_cmd,
    }


@app.get("/terminal", response_class=HTMLResponse)
async def terminal_page(request: Request):
    """Serve the terminal iframe if ttyd is running, otherwise show
    install help so the user can get unblocked without leaving the UI."""
    ctx = await _ttyd_context()
    return templates.TemplateResponse(request, "terminal.html", ctx)


@app.get("/notebook", response_class=HTMLResponse)
async def notebook_page(request: Request):
    """Serve the Jupyter Lab iframe if jupyter is running, otherwise
    show install help. Same three-state pattern as /terminal so the
    two services feel consistent."""
    import shutil, platform
    jupyter_installed = shutil.which("jupyter") is not None
    jupyter_running = False
    if jupyter_installed:
        jupyter_running = await _port_open(
            os.getenv("BIND_ADDR", "127.0.0.1"),
            int(os.getenv("NOTEBOOK_PORT", "8888")),
        )
    return templates.TemplateResponse(request, "notebook.html", {
        "jupyter_installed": jupyter_installed,
        "jupyter_running": jupyter_running,
        "notebook_port": int(os.getenv("NOTEBOOK_PORT", "8888")),
        "system": platform.system(),
    })


@app.post("/api/notebook/start")
async def notebook_start():
    """Start Jupyter Lab as a background process."""
    import shutil
    if not shutil.which("jupyter"):
        return {"ok": False, "error": "jupyter not installed"}
    # Ensure Dark High Contrast theme as project default
    try:
        import jupyterlab
        settings_dir = Path(jupyterlab.__file__).parent.parent.parent.parent / "share" / "jupyter" / "lab" / "settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        overrides = settings_dir / "overrides.json"
        if not overrides.exists():
            overrides.write_text(json.dumps({
                "@jupyterlab/apputils-extension:themes": {
                    "theme": "JupyterLab Dark High Contrast"
                }
            }, indent=2))
    except Exception:
        pass
    bind = os.getenv("BIND_ADDR", "127.0.0.1")
    port = int(os.getenv("NOTEBOOK_PORT", "8888"))
    csp = (
        '{"headers":{"Content-Security-Policy":'
        '"frame-ancestors \'self\' http://127.0.0.1:* http://localhost:*"}}'
    )
    subprocess.Popen(
        [
            "jupyter", "lab",
            "--no-browser",
            f"--ip={bind}",
            f"--port={port}",
            "--NotebookApp.token=",
            "--NotebookApp.password=",
            f"--ServerApp.tornado_settings={csp}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Give it a moment to bind
    await asyncio.sleep(1.5)
    return {"ok": True}


@app.post("/api/notebook/stop")
async def notebook_stop():
    """Stop any Jupyter Lab process listening on the notebook port."""
    port = int(os.getenv("NOTEBOOK_PORT", "8888"))
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True,
        )
        pids = result.stdout.strip().split()
        for pid in pids:
            subprocess.run(["kill", pid])
        return {"ok": True, "killed": pids}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Open Notebook (Docker-based NotebookLM alternative) ──────────

def _docker_available() -> bool:
    try:
        return subprocess.run(
            ["docker", "info"], capture_output=True, timeout=5,
        ).returncode == 0
    except Exception:
        return False


def _container_running(name: str) -> bool:
    """True when a Docker container matching ``name`` is up.

    Shared by Open Notebook + Marimo + any future docker-backed
    service. Name is matched against ``docker ps --filter name=…``
    (substring match, so ``arail-marimo`` matches ``arail-marimo``
    but not ``arail-marimo-db``).
    """
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={name}",
             "--filter", "status=running", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5,
        )
        return name in result.stdout
    except Exception:
        return False


# Back-compat alias — the old name reads nicer at call sites that
# only ever check this one container. Dropping it would touch too
# many call sites for zero real benefit.
def _onb_container_running() -> bool:
    return _container_running("arail-open-notebook")


async def _port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    """Lightweight TCP probe — True if the port accepts a connection.

    Replaces a block duplicated across /terminal, /notebook,
    /api/addons/status, and the new /api/notebooks/status. Never
    raises — any failure (refused, timeout, DNS) returns False.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


_COMPOSE_FILE = str(Path(__file__).resolve().parents[3] / "compose" / "open-notebook.yml")
_MARIMO_COMPOSE = str(Path(__file__).resolve().parents[3] / "compose" / "marimo.yml")


@app.get("/open-notebook", response_class=HTMLResponse)
async def open_notebook_page(request: Request):
    """First-class page for Open Notebook — 3-state UI like terminal/notebook."""
    docker_ok = _docker_available()
    running = _onb_container_running() if docker_ok else False
    encryption_key_set = bool(os.getenv("OPEN_NOTEBOOK_ENCRYPTION_KEY"))
    ui_port = int(os.getenv("OPEN_NOTEBOOK_PORT", "8502"))
    api_port = int(os.getenv("OPEN_NOTEBOOK_API_PORT", "5055"))
    return templates.TemplateResponse(request, "open-notebook.html", {
        "docker_available": docker_ok,
        "container_running": running,
        "encryption_key_set": encryption_key_set,
        "ui_port": ui_port,
        "api_port": api_port,
    })


@app.get("/integrations/knowledge-canvas", response_class=HTMLResponse)
async def integrations_knowledge_canvas(request: Request):
    """Integration landing page for the knowledge-canvas frontend.

    Embeds the canvas frontend if it's installed under `core/knowledge-canvas/frontend`.
    """
    has_frontend = KC_FRONTEND_DIST_DIR.exists() or KC_FRONTEND_DIR.exists()
    return templates.TemplateResponse(request, "integrations/knowledge_canvas.html", {
        "has_frontend": has_frontend,
    })


def _repo_env_file() -> str:
    """Absolute path to the repo-root .env so docker compose can
    resolve OPEN_NOTEBOOK_ENCRYPTION_KEY (compose defaults to looking
    next to the yml file, which is compose/.env — the wrong place)."""
    return str(Path(_COMPOSE_FILE).resolve().parents[1] / ".env")


@app.post("/api/open-notebook/start")
async def open_notebook_start():
    """Bring up Open Notebook via docker compose, then seed with lab content."""
    if not _docker_available():
        return {"ok": False, "error": "Docker not available"}
    if not os.getenv("OPEN_NOTEBOOK_ENCRYPTION_KEY"):
        return {"ok": False, "error": "OPEN_NOTEBOOK_ENCRYPTION_KEY not set — run ./arail setup"}
    result = subprocess.run(
        ["docker", "compose", "--env-file", _repo_env_file(),
         "-f", _COMPOSE_FILE, "up", "-d"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr[-500:] if result.stderr else "unknown"}
    # Seed with lab content in the background (non-blocking)
    import threading
    from arail.open_notebook_seed import seed as seed_onb
    api_port = int(os.getenv("OPEN_NOTEBOOK_API_PORT", "5055"))
    threading.Thread(target=seed_onb, args=(api_port,), daemon=True).start()
    return {"ok": True}


@app.post("/api/open-notebook/stop")
async def open_notebook_stop():
    """Tear down Open Notebook containers."""
    result = subprocess.run(
        ["docker", "compose", "--env-file", _repo_env_file(),
         "-f", _COMPOSE_FILE, "down"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr[-500:] if result.stderr else "unknown"}
    return {"ok": True}


# ── Notebooks picker + status ──────────────────────────────────────

@app.get("/notebooks", response_class=HTMLResponse)
async def notebooks_page(request: Request):
    """Picker page — three cards (Jupyter / Marimo / Open Notebook).

    All state is pulled client-side from /api/notebooks/status, so this
    route is a pure template render.
    """
    return templates.TemplateResponse(request, "notebooks.html", {})


@app.get("/api/notebooks/status")
async def notebooks_status():
    """One-shot liveness probe for every notebook surface.

    Drives the picker page's status dots. Checks:
      - Jupyter: ``jupyter`` binary on PATH + TCP probe on NOTEBOOK_PORT.
      - Marimo: Docker available + arail-marimo container running.
      - Open Notebook: Docker available + arail-open-notebook container running.
    """
    import shutil
    bind = os.getenv("BIND_ADDR", "127.0.0.1")
    password = os.getenv("ARAIL_PASSWORD", "arail")
    jupyter_port = int(os.getenv("NOTEBOOK_PORT", "8888"))
    marimo_port = int(os.getenv("MARIMO_PORT", "2718"))
    on_port = int(os.getenv("OPEN_NOTEBOOK_PORT", "8502"))

    docker_ok = _docker_available()
    # Kick off TCP probes concurrently — they each cost ~300ms on miss.
    jup_alive, mar_alive, on_alive = await asyncio.gather(
        _port_open(bind, jupyter_port),
        _port_open(bind, marimo_port),
        _port_open(bind, on_port),
    )
    return {
        "notebooks": [
            {
                "id": "jupyter",
                "name": "Jupyter Lab",
                "installed": shutil.which("jupyter") is not None,
                "alive": jup_alive,
                "url_internal": "/notebook",
                "url_external": f"http://{bind}:{jupyter_port}/lab",
            },
            {
                "id": "marimo",
                "name": "Marimo",
                "installed": docker_ok,
                "alive": mar_alive and _container_running("arail-marimo"),
                "url_internal": "/marimo",
                "url_external": f"http://{bind}:{marimo_port}?access_token={password}",
            },
            {
                "id": "open-notebook",
                "name": "Open Notebook",
                "installed": docker_ok,
                "alive": on_alive and _container_running("arail-open-notebook"),
                "url_internal": "/open-notebook",
                "url_external": f"http://{bind}:{on_port}",
            },
        ],
    }


# ── Marimo — reactive Python notebooks (compose-backed) ─────────────

@app.get("/marimo", response_class=HTMLResponse)
async def marimo_page(request: Request):
    """3-state Marimo page: docker missing / not running / running.

    When running, shows the Marimo iframe with the token baked into the
    URL (same ``?access_token=<ARAIL_PASSWORD>`` contract Marimo itself
    prints on startup). When not running, shows a one-click Start button
    that calls /api/marimo/start.
    """
    docker_ok = _docker_available()
    running = _container_running("arail-marimo") if docker_ok else False
    password = os.getenv("ARAIL_PASSWORD", "arail")
    ui_port = int(os.getenv("MARIMO_PORT", "2718"))
    return templates.TemplateResponse(request, "marimo.html", {
        "docker_available": docker_ok,
        "container_running": running,
        "ui_port": ui_port,
        "password": password,
    })


@app.post("/api/marimo/start")
async def marimo_start():
    """Bring up the Marimo container via docker compose."""
    if not _docker_available():
        return {"ok": False, "error": "Docker not available"}
    result = subprocess.run(
        ["docker", "compose", "--env-file", _repo_env_file(),
         "-f", _MARIMO_COMPOSE, "up", "-d"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr[-500:] if result.stderr else "unknown"}
    return {"ok": True}


@app.post("/api/marimo/stop")
async def marimo_stop():
    """Tear down the Marimo container."""
    result = subprocess.run(
        ["docker", "compose", "--env-file", _repo_env_file(),
         "-f", _MARIMO_COMPOSE, "down"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr[-500:] if result.stderr else "unknown"}
    return {"ok": True}


@app.get("/plugins", response_class=HTMLResponse)
async def plugins_page(request: Request):
    plugins = plugin_mgr.list_plugins()
    return templates.TemplateResponse(request, "plugins.html", {
        "plugins": plugins,
    })


@app.get("/skills", response_class=HTMLResponse)
async def skills_page(request: Request):
    """Skills marketplace + loadout editor.

    The page renders an empty shell — Loadouts, Installed skills,
    and Available packs all populate client-side via /api/agents/loadouts,
    /api/skills/list, and /api/skills/packs respectively.
    """
    return templates.TemplateResponse(request, "skills.html", {})


@app.get("/docs", response_class=HTMLResponse)
async def docs_landing():
    return RedirectResponse(url="/docs/INDEX.md", status_code=302)


def _render_markdown_page(request: Request, target: Path, *, doc_path: str,
                          nav_active: str = "docs", doc_section: str = "docs") -> HTMLResponse:
    try:
        from markdown_it import MarkdownIt  # type: ignore[import-untyped]
    except ImportError:
        return HTMLResponse(target.read_text(errors="replace"), status_code=200)

    md = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
    md.enable(["table", "strikethrough"])
    body_html = md.render(target.read_text(errors="replace"))
    return templates.TemplateResponse(request, "doc_viewer.html", {
        "doc_path": doc_path,
        "doc_html": body_html,
        "nav_active": nav_active,
        "doc_section": doc_section,
    })


@app.get("/design", response_class=HTMLResponse)
async def design_doc(request: Request):
    repo_root = Path(__file__).resolve().parents[3]
    target = repo_root / "design.md"
    if not target.exists():
        return HTMLResponse(
            "<h1>Not found</h1><p>design.md is missing from the repo root.</p>",
            status_code=404,
        )
    return _render_markdown_page(
        request,
        target,
        doc_path="design.md",
        nav_active="docs",
        doc_section="spec",
    )


@app.get("/blueprints-overview", response_class=HTMLResponse)
async def blueprints_overview_doc(request: Request):
    repo_root = Path(__file__).resolve().parents[3]
    target = repo_root / "BLUEPRINTS.md"
    if not target.exists():
        return HTMLResponse("<h1>Not found</h1>", status_code=404)
    return _render_markdown_page(
        request,
        target,
        doc_path="BLUEPRINTS.md",
        nav_active="docs",
        doc_section="repo",
    )


@app.get("/blueprints-guide", response_class=HTMLResponse)
async def blueprints_guide_doc(request: Request):
    repo_root = Path(__file__).resolve().parents[3]
    target = repo_root / "blueprints" / "README.md"
    if not target.exists():
        return HTMLResponse("<h1>Not found</h1>", status_code=404)
    return _render_markdown_page(
        request,
        target,
        doc_path="blueprints/README.md",
        nav_active="docs",
        doc_section="repo",
    )


@app.get("/porting-manifest", response_class=HTMLResponse)
async def porting_manifest_doc(request: Request):
    repo_root = Path(__file__).resolve().parents[3]
    target = repo_root / "AGENTS.md"
    if not target.exists():
        return HTMLResponse("<h1>Not found</h1>", status_code=404)
    return _render_markdown_page(
        request,
        target,
        doc_path="AGENTS.md",
        nav_active="docs",
        doc_section="repo",
    )


# ── Local docs viewer ───────────────────────────────────────────────────
# The agent cards' "📖 Learn" links and the "View source" links used to
# point at https://github.com/cdarnell/autoresearch-lab/blob/main/...
# Two problems with that:
#   1. The repo is private — every external user got 404.
#   2. Going off-host for in-app navigation defeats the lab's
#      local-first ethos.
#
# This route serves the markdown files under the repo's `docs/` dir
# rendered as HTML, with anchor support so existing fragment links
# (`#researcher`, `#curator`, etc.) keep working.
@app.get("/docs/{path:path}", response_class=HTMLResponse)
async def serve_local_doc(path: str, request: Request):
    """Render a markdown file from the repo's docs/ dir as HTML.

    Path is restricted to ``docs/*.md`` — no traversal, no other
    extensions. Returns 404 (not raise) when the file is missing so
    the response stays user-friendly.
    """
    if not path.endswith(".md") or ".." in path or path.startswith("/"):
        return HTMLResponse(
            "<h1>Not found</h1><p>Only .md files under docs/ are served here.</p>",
            status_code=404,
        )
    from pathlib import Path as _P
    repo_root = _P(__file__).resolve().parents[3]  # arail/
    target = (repo_root / "docs" / path).resolve()
    docs_root = (repo_root / "docs").resolve()
    if docs_root not in target.parents and target != docs_root:
        return HTMLResponse("<h1>Not found</h1>", status_code=404)
    if not target.exists() or not target.is_file():
        return HTMLResponse(
            f"<h1>Not found</h1><p>{path} is not in the docs directory.</p>",
            status_code=404,
        )
    return _render_markdown_page(request, target, doc_path=path)


@app.get("/autoresearch", response_class=HTMLResponse)
@app.get("/research", response_class=HTMLResponse)
async def research_page(request: Request):
    """Research cockpit — goal + experiments + live researcher activity.

    All the live state is populated client-side via /api/goal,
    /api/experiments, /api/research/status, and the SSE activity stream.
    The page just needs to render an empty shell."""
    return templates.TemplateResponse(request, "research.html", {})


# ── SSE Activity Stream ─────────────────────────────────────────────────

@app.get("/api/activity/stream")
async def activity_stream():
    async def _generate():
        async for event in activity_log.subscribe():
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/activity/recent")
async def activity_recent(n: int = 30):
    return activity_log.recent(n)


# ── Goal API ─────────────────────────────────────────────────────────────

@app.post("/api/goal")
async def set_goal(request: Request):
    body = await request.json()
    goal_text = body.get("goal", "")
    auto_start = body.get("auto_start", True)
    auto_draft = body.get("auto_draft", True)
    try:
        parsed = parser.parse(goal_text)
    except Exception:
        parsed = parser.parse_offline(goal_text)
    record = goal_store.set_goal(parsed)
    activity_log.emit("goal", f"New goal set: {goal_text}", "info")
    # Auto-start research unless explicitly disabled
    if auto_start and researcher.status in ("idle", "completed", "error"):
        researcher.start(parsed)
        activity_log.emit("researcher",
            "Auto-starting research on your new goal…", "info")
    # Fire-and-forget the program drafter so the user gets a first
    # pass at lab/pkb/research/program.md within seconds. Honors
    # force=False — re-setting a goal never clobbers existing edits.
    if auto_draft:
        asyncio.create_task(_auto_draft_program(record))
    return record


async def _auto_draft_program(goal_record: dict) -> None:
    """Run the program drafter off the request thread.

    Called from POST /api/goal as a fire-and-forget task. Pulls fresh
    KB hits via the LanceDB-backed pkb.search so the Sources section
    reflects the current corpus. Always swallows errors — drafting is
    a nice-to-have, never gate goal-set on it.
    """
    try:
        from arail.research.program_drafter import draft_program
        from arail import pkb as pkb_mod

        goal_text = goal_record.get("goal_text", "") or ""
        kb_hits = []
        try:
            kb_hits = pkb_mod.search(goal_text)[:8]
        except Exception:
            pass
        result = await asyncio.to_thread(
            draft_program,
            goal_record=goal_record,
            kb_hits=kb_hits,
            force=False,
        )
        if result.wrote:
            activity_log.emit(
                "researcher",
                "Drafted research program — review at "
                "/knowledge?file=research/program.md",
                "info",
                {
                    "program_path": str(result.program_path),
                    "hypothesis_count": result.hypothesis_count,
                    "sources_count": result.sources_count,
                },
            )
        else:
            activity_log.emit(
                "researcher",
                f"Skipped re-draft of program.md ({result.reason}). "
                "Click Re-draft on the dashboard to overwrite.",
                "info",
            )
    except Exception as e:
        activity_log.emit(
            "researcher",
            f"Program draft failed: {e!s}", "warn",
        )


@app.get("/api/goal")
async def get_goal():
    return goal_store.get_current()


# ── Research API ─────────────────────────────────────────────────────────

@app.post("/api/research/start")
async def research_start(request: Request):
    current = goal_store.get_current()
    if not current:
        return {"error": "No active goal. Set a goal first."}
    if jobs_halted():
        return {"error": "Jobs are halted. Resume from the dashboard first."}
    # Allow the caller to skip the startup courtesy delay for an explicit
    # "run now" click.
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    delay = 0 if body.get("now") else None
    researcher.start(current["parsed"], delay=delay)
    return {"status": researcher.status}


@app.post("/api/research/pause")
async def research_pause():
    researcher.pause()
    return {"status": researcher.status}


@app.post("/api/research/resume")
async def research_resume():
    researcher.resume()
    return {"status": researcher.status}


@app.post("/api/research/stop")
async def research_stop():
    researcher.stop()
    return {"status": researcher.status}


@app.post("/api/research/reset")
async def research_reset():
    """Stop research and clear the current goal (archives it)."""
    researcher.stop()
    goal_store.clear_current()
    activity_log.emit("researcher", "Research reset — goal archived, ready for a new one.", "info")
    return {"status": "idle"}


@app.get("/api/research/status")
async def research_status():
    current = goal_store.get_current()
    return {
        "status": researcher.status,
        "progress": current["progress"] if current else 0,
        "report": current.get("report") if current else None,
        "redirect": get_agent_redirect("researcher"),
    }


# ── Research program files (prepare.py + program.md) ─────────────────────
# Two files define the research contract:
#   • prepare.py  — fixed environment: datasets + validation metric.
#                   Read-only for the agent (cheat-proof scoring).
#   • program.md  — natural-language instructions / meta-program.
#                   The "what to optimize" half of the contract.
# These live under the PKB at lab/pkb/research/ so they're one tree
# with the rest of the knowledge base — appearing in /knowledge, the
# wiki, and discoverable by agents via the existing PKB reading path.
# The /research cockpit links to both so they're one click from the goal.

_RESEARCH_DIR = Path(__file__).resolve().parents[3] / "lab" / "pkb" / "research"
_RESEARCH_FILES = {
    "prepare.py": {
        "kind": "fixed-environment",
        "title": "prepare.py — Fixed Environment File",
        "blurb": "Data prep + validation metric. Read-only for the agent.",
    },
    "program.md": {
        "kind": "instructions",
        "title": "program.md — Research Instructions",
        "blurb": "Natural-language goal & constraints. The agent's meta-program.",
    },
}


@app.get("/api/research/files")
async def research_files():
    """List the research program files + any human-authored notes.

    ``files`` = the two curated contract files (program.md, prepare.py).
    ``notes`` = every other markdown file dropped under
    lab/pkb/research/ — humans can leave references, observations,
    cost budgets, and the researcher reads them via the wiki.
    """
    out = []
    for name, meta in _RESEARCH_FILES.items():
        path = _RESEARCH_DIR / name
        entry = {"name": name, **meta, "exists": path.exists()}
        if entry["exists"]:
            stat = path.stat()
            entry["size"] = stat.st_size
            entry["mtime"] = stat.st_mtime
        out.append(entry)

    notes = []
    if _RESEARCH_DIR.exists():
        for p in sorted(_RESEARCH_DIR.glob("*.md")):
            if p.name in _RESEARCH_FILES:
                continue  # already in `files`
            try:
                stat = p.stat()
                notes.append({
                    "name": p.name,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
            except OSError:
                continue
    return {"files": out, "notes": notes, "dir": str(_RESEARCH_DIR)}


@app.get("/api/research/file")
async def research_file(name: str = ""):
    """Read a research file.

    Accepts the two curated files (prepare.py, program.md) OR any
    .md note that lives directly under lab/pkb/research/. Rejects
    anything with a path separator to prevent traversal.
    """
    if not name or "/" in name or ".." in name:
        return {"error": "invalid name"}
    path = _RESEARCH_DIR / name
    if not path.exists() or not path.is_file():
        return {"error": f"{name} not found at {path}"}
    # Permit only curated files + .md notes in the research dir.
    if name not in _RESEARCH_FILES and not name.endswith(".md"):
        return {"error": "only .md notes are readable via this endpoint"}

    try:
        meta = _RESEARCH_FILES.get(name, {
            "kind": "note",
            "title": name,
            "blurb": "Human-authored research note.",
        })
        return {
            "name": name,
            "content": path.read_text(errors="replace"),
            "size": path.stat().st_size,
            **meta,
        }
    except OSError as e:
        return {"error": str(e)}


# ── Research program API ─────────────────────────────────────────────────
# Lifecycle endpoints for the system-authored "research recipe" — see
# lab/pkb/research/README.md for the contract. The drafter runs
# automatically on POST /api/goal; these endpoints are for manual
# re-draft and reset triggered from the dashboard or autoresearch tab.

@app.post("/api/research/program/draft")
async def research_program_draft(request: Request):
    """Draft (or re-draft) lab/pkb/research/program.md from the current goal.

    Body: ``{ "force": false }``. Without ``force`` we refuse to
    overwrite an existing program.md so re-setting a goal never
    clobbers user edits. The dashboard's "Re-draft" button passes
    ``force=true``.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    force = bool(body.get("force", False))

    current = goal_store.get_current()
    if not current:
        return {"ok": False, "error": "no active goal — set one first"}

    from arail.research.program_drafter import draft_program
    from arail import pkb as pkb_mod
    goal_text = current.get("goal_text", "") or ""
    kb_hits: list = []
    try:
        kb_hits = pkb_mod.search(goal_text)[:8]
    except Exception:
        pass
    result = await asyncio.to_thread(
        draft_program,
        goal_record=current,
        kb_hits=kb_hits,
        force=force,
    )
    if result.wrote:
        activity_log.emit(
            "researcher",
            f"Re-drafted research program ({result.hypothesis_count} hypotheses, "
            f"{result.sources_count} sources).", "info")
    return {"ok": True, **result.as_dict()}


@app.post("/api/research/program/reset")
async def research_program_reset():
    """Wipe program.md + train.py + curated source fetches.

    Mirrors ``./arail reset program``. Always preserves prepare.py
    (the validation contract is sticky). Resets the autoresearch
    schedule to paused so the next run starts from a clean slate.
    """
    from arail.research.program_drafter import (
        _DEFAULT_RESEARCH_DIR as RESEARCH_DIR,
    )
    program_path = RESEARCH_DIR / "program.md"
    train_path = RESEARCH_DIR / "train.py"
    schedule_path = Path("lab/data/autoresearch-schedule.json")
    research_sources = Path("lab/pkb/sources/research")

    removed = []
    for p in (program_path, train_path):
        if p.exists():
            try:
                p.unlink()
                removed.append(str(p))
            except OSError:
                pass
    # Curated source fetches (when Thread E lands they'll live here).
    if research_sources.exists():
        try:
            for f in research_sources.glob("*.md"):
                f.unlink()
                removed.append(str(f))
        except OSError:
            pass
    # Reset the autoresearch schedule to paused.
    if schedule_path.exists():
        try:
            schedule_path.write_text(
                '{"mode": "paused", "window_start": "22:00", "window_end": "06:00"}\n'
            )
            removed.append(f"{schedule_path} (reset to paused)")
        except OSError:
            pass

    activity_log.emit(
        "researcher",
        f"Reset research program — removed {len(removed)} file(s). "
        "prepare.py is left in place.", "warn")
    return {"ok": True, "removed": removed}


# ── Jobs / Scheduler API ─────────────────────────────────────────────────
# Halt = soft emergency stop: cancels running work but keeps the portal
# and services up, unlike `./arail stop` which tears down everything.

@app.get("/api/jobs/state")
async def jobs_state():
    s = scheduler_state()
    s["researcher_status"] = researcher.status
    return s


@app.post("/api/jobs/halt")
async def jobs_halt():
    halt_all_jobs()
    researcher.stop()
    activity_log.emit("system",
                      "Halt requested — all running jobs cancelled. "
                      "Resume from the dashboard when ready.",
                      "warn")
    return {"halted": True, "researcher_status": researcher.status}


@app.post("/api/jobs/resume")
async def jobs_resume():
    resume_all_jobs()
    activity_log.emit("system",
                      "Jobs resumed. New work will honor the current window.",
                      "info")
    return {"halted": False}


# ── Experiment API ───────────────────────────────────────────────────────

@app.get("/api/experiments")
async def list_experiments(status: str | None = None):
    return tracker.list_all(status=status)


@app.get("/api/experiments/search")
async def search_experiments(q: str, k: int = 5, status: str | None = None):
    """Semantic search over the experiment corpus.

    Backed by the shared LanceDB index (arail.vector_index). Falls back
    to substring scan when LanceDB is unreachable so the endpoint is
    always usable.
    """
    if not q or not q.strip():
        return {"query": q, "hits": []}
    hits = tracker.search(q.strip(), k=max(1, min(k, 25)), status=status)
    return {"query": q, "hits": hits}


@app.post("/api/experiments")
async def create_experiment(request: Request):
    body = await request.json()
    exp = tracker.create(
        hypothesis=body["hypothesis"],
        methodology=body["methodology"],
        variables=body.get("variables", {}),
        duration_days=body.get("duration_days"),
        metrics=body.get("metrics", []),
        domain=body.get("domain", "general"),
    )
    return exp


# ── Plugin API ───────────────────────────────────────────────────────────

@app.post("/api/plugins/install")
async def install_plugin(request: Request):
    body = await request.json()
    url = body.get("github_url", "")
    try:
        result = plugin_mgr.install(url)
        return result
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Install failed: {e}"}


@app.get("/api/plugins")
async def list_plugins():
    return plugin_mgr.list_plugins()


@app.delete("/api/plugins/{name}")
async def uninstall_plugin(name: str):
    try:
        plugin_mgr.uninstall(name)
        return {"status": "removed"}
    except ValueError:
        return {"error": f"Plugin '{name}' not found"}


@app.post("/api/plugins/{name}/toggle")
async def toggle_plugin(name: str, request: Request):
    body = await request.json()
    active = body.get("active", True)
    try:
        plugin_mgr.toggle(name, active)
        return {"status": "active" if active else "disabled"}
    except KeyError:
        return {"error": f"Plugin '{name}' not found"}


@app.get("/api/plugins/{name}/readme")
async def plugin_readme(name: str):
    content = plugin_mgr.get_readme(name)
    return {"readme": content}


# ── Agent Consent API ────────────────────────────────────────────────────

@app.get("/api/consent/pending")
async def pending_requests():
    return consent_store.list_pending()


@app.post("/api/consent/approve")
async def approve_request(request: Request):
    body = await request.json()
    request_id = body["id"]
    remember_domain = body.get("remember_domain", False)
    consent_store.approve(request_id, remember_domain=remember_domain)
    activity_log.emit("consent", f"Approved request {request_id}", "success")
    return {"status": "approved"}


@app.post("/api/consent/deny")
async def deny_request(request: Request):
    body = await request.json()
    consent_store.deny(body["id"])
    activity_log.emit("consent", f"Denied request {body['id']}", "warn")
    return {"status": "denied"}


@app.get("/api/consent/allowlist")
async def get_allowlist():
    return consent_store.list_allowed()


@app.post("/api/consent/revoke")
async def revoke_domain(request: Request):
    body = await request.json()
    domain = body.get("domain", "")
    consent_store.remove_domain(domain)
    activity_log.emit("consent", f"Revoked domain: {domain}", "warn")
    return {"status": "revoked"}


# ── System Graph ─────────────────────────────────────────────────────────

@app.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request):
    preview = request.query_params.get("preview", "0") in {"1", "true", "yes"}
    return templates.TemplateResponse(request, "graph.html", {
        "preview": preview,
    })


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Lab administration — services, components, updates, help."""
    health = {}
    try:
        health = (await system_health())
    except Exception:
        pass
    ttyd = await _ttyd_context()
    return templates.TemplateResponse(request, "admin.html", {
        "health": health,
        "current_ui_theme": _UI_THEME,
        "available_ui_themes": list_ui_themes(),
        **ttyd,
    })


@app.get("/api/system/theme")
async def system_theme():
    return {
        "current": {
            "id": _UI_THEME.id,
            "name": _UI_THEME.name,
            "description": _UI_THEME.description,
            "env_value": _UI_THEME.env_value,
        },
        "themes": [
            {
                "id": theme.id,
                "name": theme.name,
                "description": theme.description,
                "accent": theme.accent,
                "preview_start": theme.preview_start,
                "preview_end": theme.preview_end,
                "env_value": theme.env_value,
            }
            for theme in list_ui_themes()
        ],
    }


# ── Agents tab ──────────────────────────────────────────────────────

@app.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request):
    """Agent Control Center — monitor, instruct, and inspect all agents."""
    return templates.TemplateResponse(request, "agents.html", {
        "current_goal": goal_store.get_current(),
        "mode": os.getenv("LAB_NETWORK_MODE", "hybrid").lower(),
    })


@app.get("/api/agents/status")
async def agents_status():
    """Aggregated status of all three agents."""
    from arail.agents.browser import EXTRACT_DIR

    workflow_rows = {row.get("agent_id"): row for row in list_agent_workflows()}
    researcher_redirect = get_agent_redirect("researcher")

    # Walk the activity log once and bucket per-agent tokens + recent
    # action snippets. Keeping it to a single pass means adding new
    # agents later doesn't multiply the log scans.
    recent = activity_log.recent(200)
    per_agent_tokens: dict[str, int] = {}
    per_agent_recent: dict[str, list[dict]] = {}
    for ev in recent:
        src = ev.get("source")
        if not src:
            continue
        trace = ev.get("data", {}).get("prompt_trace")
        if trace:
            per_agent_tokens[src] = per_agent_tokens.get(src, 0) + int(trace.get("max_tokens", 0) or 0)
        per_agent_recent.setdefault(src, []).append({
            "ts": ev.get("ts"),
            "level": ev.get("level", "info"),
            "message": (ev.get("message") or "")[:140],
        })
    for src in list(per_agent_recent.keys()):
        # Newest-first, cap at 3 — what each card actually shows.
        per_agent_recent[src] = list(reversed(per_agent_recent[src]))[:3]

    # Researcher
    goal = goal_store.get_current()
    researcher_workflow = workflow_rows.get("researcher") or {}
    r_status = {
        "status": researcher.status,
        "progress": goal.get("progress", 0) if goal else 0,
        "experiments": len(goal.get("experiments", [])) if goal else 0,
        "current_task": researcher_workflow.get("current_task"),
        "objective": researcher_workflow.get("objective"),
        "completed_steps": researcher_workflow.get("completed_steps", []),
        "next_step": researcher_workflow.get("next_step"),
        "paused": researcher_workflow.get("paused", False),
        "pause_reason": researcher_workflow.get("pause_reason"),
        "chatty": researcher_workflow.get("chatter", {}),
        "workflow": researcher_workflow,
        "redirect": researcher_redirect,
        "has_goal": bool(goal and goal.get("goal_text")),
        "tokens": per_agent_tokens.get("researcher", 0),
        "recent_actions": per_agent_recent.get("researcher", []),
    }
    if not r_status["current_task"]:
        for ev in reversed(recent):
            if ev.get("source") == "researcher" and ev.get("level") in ("info", "success"):
                r_status["current_task"] = ev["message"][:80]
                break

    # Curator
    c_status = {
        "pending": len(consent_store.list_pending()),
        "allowed": len(consent_store.list_allowed()),
        "tokens": per_agent_tokens.get("curator", 0),
        "recent_actions": per_agent_recent.get("curator", []),
    }

    pip_workflow = dict(workflow_rows.get("pip") or {})
    pip_workflow["tokens"] = per_agent_tokens.get("pip", 0)
    pip_workflow["recent_actions"] = per_agent_recent.get("pip", [])
    sre_workflow = dict(workflow_rows.get("sre") or {})
    sre_workflow["tokens"] = per_agent_tokens.get("sre", 0)
    sre_workflow["recent_actions"] = per_agent_recent.get("sre", [])

    # Browser
    captures = len(list(EXTRACT_DIR.glob("*.md"))) if EXTRACT_DIR.exists() else 0
    last_task = None
    for ev in reversed(recent):
        if ev.get("source") == "browser":
            last_task = ev["message"][:60]
            break
    b_status = {
        "captures": captures,
        "last_task": last_task,
        "tokens": per_agent_tokens.get("browser", 0),
        "recent_actions": per_agent_recent.get("browser", []),
    }

    return {
        "researcher": r_status,
        "curator": c_status,
        "browser": b_status,
        "pip": pip_workflow,
        "sre": sre_workflow,
    }


@app.get("/api/agents/prompts")
async def agents_prompts(agent: str = "", limit: int = 30):
    """Return recent prompt-trace events for the Prompt Inspector."""
    traces = []
    for ev in reversed(activity_log.recent(200)):
        if agent and ev.get("source") != agent:
            continue
        if ev.get("data", {}).get("prompt_trace"):
            traces.append(ev)
            if len(traces) >= limit:
                break
    return list(reversed(traces))


@app.post("/api/agents/instruct")
async def agents_instruct(request: Request):
    """Send an ad-hoc instruction to an agent."""
    body = await request.json()
    agent_name = body.get("agent", "")
    instruction = body.get("instruction", "").strip()
    if not instruction:
        return {"error": "instruction required"}
    activity_log.emit(
        agent_name or "user",
        f"Instruction: {instruction}",
        "info",
        {"instruction": True, "target_agent": agent_name},
    )
    return {"ok": True, "queued": True}


@app.post("/api/agents/redirect")
async def agents_redirect(request: Request):
    """Persist a redirect vector for a live agent."""
    body = await request.json()
    agent_name = str(body.get("agent") or "researcher").strip() or "researcher"
    instruction = str(body.get("instruction") or "").strip()
    preset = str(body.get("preset") or "").strip()
    label = str(body.get("label") or "").strip()
    if not instruction:
        return {"error": "instruction required"}

    redirect = set_agent_redirect(agent_name, instruction, preset=preset, label=label)
    activity_log.emit(
        agent_name,
        f"Redirect vector received: {instruction}",
        "warn",
        {"redirect": redirect, "target_agent": agent_name},
    )
    return {"ok": True, "redirect": redirect}


@app.delete("/api/agents/redirect")
async def agents_redirect_clear(agent: str = "researcher"):
    """Clear the current redirect vector for an agent."""
    removed = clear_agent_redirect(agent)
    if removed:
        activity_log.emit(
            agent,
            "Redirect cleared. Resume the baseline objective.",
            "info",
            {"redirect_cleared": True, "target_agent": agent},
        )
    return {"ok": True, "cleared": bool(removed)}


# ── Agent Forge + skills picker endpoints ────────────────────────
# /api/skills/list feeds the Forge UI's skill multi-select.
# /api/agents/list returns everything the loader currently knows —
#   used by the Forge to prevent id collisions before Deploy.
# /api/agents/forge is the Deploy button's backend.

@app.get("/api/skills/list")
async def api_skills_list():
    """Return every installed skill so the Forge can show toggles."""
    from arail.skills_loader import list_installed_skills
    skills = list_installed_skills()
    return {
        "skills": [
            {
                "id": s.id,
                "name": s.name,
                "domain": s.domain,
                "version": s.version,
                # First ~200 chars of the body for a preview tooltip.
                "preview": (s.body or "")[:200],
            }
            for s in skills
        ]
    }


# ── Skill detail / edit / delete ─────────────────────────────────
# CRUD for individual SKILL.md files. Powers the Skills tab inline
# editor + "Open in IDE" deep-link path. Validates the YAML
# frontmatter on every save so a broken edit can't poison the
# agent's next LLM call.

def _skill_path(skill_id: str) -> Path:
    """Resolve the on-disk SKILL.md path; rejects path-traversal."""
    if not skill_id or "/" in skill_id or ".." in skill_id:
        return Path()
    from arail.config import PKB_ROOT
    return PKB_ROOT / "skills" / skill_id / "SKILL.md"


def _truthy(value) -> bool:
    """Coerce YAML-ish truthy markers to Python bool.

    Accepts native bools, ints, and the common YAML 1.1 strings
    (``yes`` / ``no`` / ``true`` / ``false`` / ``on`` / ``off``).
    parse_frontmatter doesn't use a real YAML loader so all values
    arrive as strings — we have to interpret them here.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


# ── Skill packs (the marketplace) ────────────────────────────────
# Browse + install + remove curated bundles. Pack metadata is in
# src/arail/skill_packs/manifest.yaml; each pack's SKILL.md files
# ship under src/arail/skill_packs/<pack_id>/<skill_id>/.
#
# IMPORTANT: this block lives ABOVE /api/skills/{skill_id} because
# FastAPI route matching is order-dependent — without this, the
# dynamic `{skill_id}` route swallows `packs`, `packs/install`,
# etc.

@app.get("/api/skills/packs")
async def api_skill_packs_list():
    """Return every pack with install status for the marketplace UI."""
    from arail.skill_packs import packs_with_status
    return {"packs": packs_with_status()}


@app.post("/api/skills/packs/install")
async def api_skill_packs_install(request: Request):
    """Install a pack (idempotent). Body: {pack_id, force=false}."""
    body = await request.json()
    pack_id = (body.get("pack_id") or "").strip()
    force = bool(body.get("force", False))
    if not pack_id:
        return {"ok": False, "error": "pack_id required"}
    from arail.skill_packs import install_pack
    result = install_pack(pack_id, force=force)
    if result.get("ok") and (result.get("installed") or force):
        activity_log.emit("pkb",
            f"Skill pack installed: {pack_id} "
            f"({len(result.get('installed', []))} skills)", "info")
    return result


@app.post("/api/skills/packs/remove")
async def api_skill_packs_remove(request: Request):
    """Uninstall a pack — only removes skills declared in its
    manifest, preserving user-added skills."""
    body = await request.json()
    pack_id = (body.get("pack_id") or "").strip()
    if not pack_id:
        return {"ok": False, "error": "pack_id required"}
    from arail.skill_packs import remove_pack
    result = remove_pack(pack_id)
    if result.get("ok"):
        activity_log.emit("pkb",
            f"Skill pack removed: {pack_id} "
            f"({len(result.get('removed', []))} skills)", "warn")
    return result


@app.get("/api/skills/{skill_id}")
async def api_skills_get(skill_id: str):
    """Return the full SKILL.md content for the inline editor."""
    p = _skill_path(skill_id)
    if not p.parts or not p.exists():
        return {"ok": False, "error": f"unknown skill: {skill_id}"}
    return {
        "ok": True,
        "id": skill_id,
        "path": str(p),
        "content": p.read_text(errors="replace"),
    }


@app.post("/api/skills/{skill_id}")
async def api_skills_save(skill_id: str, request: Request):
    """Persist edited SKILL.md content. Validates frontmatter shape
    before writing — refuses an invalid update so a fat-finger save
    can't break the next agent call."""
    body = await request.json()
    content = body.get("content", "")
    if not content or not content.strip():
        return {"ok": False, "error": "content required"}
    p = _skill_path(skill_id)
    if not p.parts:
        return {"ok": False, "error": "invalid skill id"}

    # Validate the YAML frontmatter has the required keys before
    # touching disk.
    try:
        from arail.skills_loader import parse_frontmatter
        fm = parse_frontmatter(content)
    except Exception as e:
        return {"ok": False, "error": f"frontmatter parse failed: {e}"}
    missing = [k for k in ("id", "name", "domain") if not fm.get(k)]
    if missing:
        return {
            "ok": False,
            "error": f"frontmatter missing required keys: {', '.join(missing)}",
        }
    if str(fm.get("id")) != skill_id:
        return {
            "ok": False,
            "error": f"frontmatter id={fm.get('id')!r} does not match URL id={skill_id!r}",
        }

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    activity_log.emit("pkb",
        f"Skill saved: {skill_id} ({len(content)} bytes)", "info")
    return {"ok": True, "id": skill_id, "bytes": len(content)}


@app.delete("/api/skills/{skill_id}")
async def api_skills_delete(skill_id: str):
    """Remove a skill folder. Use the pack-remove endpoint to bulk-
    remove a packed skill set; this one targets a single user-added
    skill (or any skill the user intends to drop)."""
    p = _skill_path(skill_id)
    if not p.parts or not p.exists():
        return {"ok": False, "error": f"unknown skill: {skill_id}"}
    import shutil as _shutil
    try:
        _shutil.rmtree(p.parent)
    except OSError as e:
        return {"ok": False, "error": str(e)}
    activity_log.emit("pkb", f"Skill removed: {skill_id}", "warn")
    return {"ok": True, "id": skill_id}


# ── Per-agent loadouts ───────────────────────────────────────────
# An agent's skill loadout is the `skills:` list in its AGENT.md.
# These endpoints read + write that list so the Skills tab can
# manage loadouts without making the user open the file in vim.

def _agent_md_path(agent_id: str) -> Path:
    if not agent_id or "/" in agent_id or ".." in agent_id:
        return Path()
    from arail.config import PKB_ROOT
    return PKB_ROOT / "agents" / agent_id / "AGENT.md"


@app.get("/api/agents/loadouts")
async def api_agents_loadouts():
    """Return {agent_id: {name, skills, consumes_llm, path}} for
    every builtin + forged agent that has an AGENT.md on disk."""
    from arail.agents.loader import discover
    from arail.skills_loader import parse_frontmatter
    out = {}
    for agent_id, folder, fm in discover():
        agent_md = folder / "AGENT.md"
        if not agent_md.exists():
            continue
        try:
            raw = agent_md.read_text(errors="replace")
            fm_full = parse_frontmatter(raw)
        except Exception:
            fm_full = {}
        skills = fm_full.get("skills") or []
        if not isinstance(skills, list):
            skills = []
        out[agent_id] = {
            "id": agent_id,
            "name": str(fm.get("name") or agent_id),
            "emoji": str(fm.get("emoji") or ""),
            "skills": [str(s) for s in skills],
            "consumes_llm": _truthy(fm_full.get("consumes_llm")),
            "path": str(agent_md),
        }
    return {"loadouts": out}


@app.post("/api/agents/{agent_id}/loadout")
async def api_agent_loadout_save(agent_id: str, request: Request):
    """Update an agent's `skills:` list in its AGENT.md. Preserves
    every other section of the file (we only rewrite the YAML block
    so user-edited prose underneath survives)."""
    body = await request.json()
    skills = body.get("skills") or []
    if not isinstance(skills, list):
        return {"ok": False, "error": "skills must be a list"}
    skills = [str(s).strip() for s in skills if str(s).strip()]

    p = _agent_md_path(agent_id)
    if not p.parts or not p.exists():
        return {"ok": False, "error": f"unknown agent: {agent_id}"}

    # Splice the new skills list into the existing frontmatter
    # without rewriting the body. We round-trip the frontmatter
    # through PyYAML — far more reliable than regex when the user
    # has comments, multi-line strings, or extra keys we don't
    # know about. Body section (everything after the closing `---`)
    # is preserved byte-for-byte.
    text = p.read_text(errors="replace")
    import re, yaml as _yaml  # type: ignore[import-untyped]
    fm_match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not fm_match:
        return {"ok": False, "error": "AGENT.md has no YAML frontmatter"}
    body = text[fm_match.end():]
    try:
        fm_data = _yaml.safe_load(fm_match.group(1)) or {}
        if not isinstance(fm_data, dict):
            fm_data = {}
    except _yaml.YAMLError as e:
        return {"ok": False, "error": f"AGENT.md frontmatter unparseable: {e}"}

    fm_data["skills"] = list(skills)
    new_fm = _yaml.safe_dump(
        fm_data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    p.write_text(f"---\n{new_fm}---\n{body}")
    activity_log.emit("pkb",
        f"Loadout updated: {agent_id} = [{', '.join(skills)}]", "info")
    return {"ok": True, "agent_id": agent_id, "skills": skills}


@app.get("/api/agents/list")
async def api_agents_list():
    """Return the agents the loader currently knows about."""
    from arail.agents.loader import discover
    out = []
    for agent_id, folder, fm in discover():
        out.append({
            "id": agent_id,
            "name": str(fm.get("name") or agent_id),
            "emoji": str(fm.get("emoji") or ""),
            "folder": str(folder),
        })
    return {"agents": out}


@app.post("/api/agents/forge")
async def api_agents_forge(request: Request):
    """Deploy a new agent from a Forge form submission.

    Body shape::

        {
          "name": "Owl",
          "emoji": "🦉",
          "voice": "Wise, patient, long view.",
          "tick_interval_sec": 120,
          "global_cooldown_sec": 600,
          "dream": true,
          "skills": ["observe-lab", "falsify-hypothesis"],
          "role": "research pacer"
        }

    Returns the forge deployment status dict — see ``forge.deploy``.
    """
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid JSON body"}
    from arail.agents.forge import deploy
    result = deploy(body)
    if result.get("ok"):
        activity_log.emit(
            "agents",
            f"🛠 Forged new agent: {result['agent_id']} "
            f"(hot-loaded={result['hot_loaded']}, started={result['started']})",
            "success",
            data=result,
        )
    else:
        activity_log.emit(
            "agents",
            f"Forge failed: {result.get('error')}",
            "warn",
        )
    return result


@app.get("/api/agents/forge/preview")
async def api_agents_forge_preview(name: str = "", emoji: str = "",
                                    voice: str = "", tick: int = 90,
                                    cooldown: int = 300, dream: bool = False,
                                    skills: str = ""):
    """Server-side preview of what Deploy would write.

    Takes the same fields as /api/agents/forge but via querystring
    and returns the generated AGENT.md + .py as strings — used by
    the UI for the right-panel preview when the user wants a
    canonical mirror of what the backend will generate.
    """
    from arail.agents.forge import (
        generate_agent_md, generate_agent_py, slugify, validate
    )
    skills_list = [s.strip() for s in (skills or "").split(",") if s.strip()]
    form = {
        "name": name,
        "emoji": emoji,
        "voice": voice,
        "tick_interval_sec": tick,
        "global_cooldown_sec": cooldown,
        "dream": dream,
        "skills": skills_list,
    }
    # Soft validation — preview shouldn't 400; surface errors inline.
    err = validate(form)
    try:
        agent_md = generate_agent_md(form)
        agent_py = generate_agent_py(form)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
    return {
        "agent_id": slugify(name),
        "agent_md": agent_md,
        "agent_py": agent_py,
        "validation_error": err,
    }


@app.get("/api/admin/components")
async def admin_components():
    """Read components.json and resolve current versions."""
    import re
    import subprocess as sp
    from importlib import metadata as importlib_metadata

    def _pkg_version(name: str) -> str | None:
        try:
            return importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            return None
        except Exception:
            return None

    def _neo4j_image_from_canvas_compose() -> str | None:
        compose_path = Path.cwd() / "core" / "knowledge-canvas" / "docker-compose.yml"
        if not compose_path.exists():
            return None
        try:
            lines = compose_path.read_text().splitlines()
        except Exception:
            return None

        in_neo4j = False
        for line in lines:
            if re.match(r"^\s{2}neo4j:\s*$", line):
                in_neo4j = True
                continue
            if in_neo4j and re.match(r"^\s{2}[a-zA-Z0-9_-]+:\s*$", line):
                break
            if in_neo4j:
                m = re.match(r"^\s{4}image:\s*(\S+)\s*$", line)
                if m:
                    return m.group(1)
        return None

    manifest_path = Path.cwd() / "components.json"
    out = []

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for c in manifest.get("components", []):
            ver = None
            vcmd = c.get("version_cmd")
            if vcmd:
                try:
                    r = sp.run(vcmd, shell=True, capture_output=True, text=True, timeout=10)
                    ver = r.stdout.strip().split("\n")[0] if r.returncode == 0 else None
                except Exception:
                    pass
            out.append({
                "name": c["name"],
                "type": c.get("type", ""),
                "description": c.get("description", ""),
                "version": ver or c.get("current_version") or "—",
                "source_url": c.get("source_url"),
                "changelog_url": c.get("changelog_url"),
                "image": c.get("image") or "",
                "package": c.get("package") or "",
            })

    # Canvas components are important enough to surface even when not tracked
    # in the top-level component manifest yet.
    neo4j_pkg_ver = _pkg_version("neo4j")
    lancedb_pkg_ver = _pkg_version("lancedb")
    neo4j_image = _neo4j_image_from_canvas_compose() or "neo4j:5-community"

    out.append({
        "name": "knowledge-canvas-neo4j",
        "type": "docker+python",
        "description": "Graph relationship store for Knowledge Canvas",
        "version": neo4j_pkg_ver or "package not installed",
        "source_url": "https://neo4j.com/",
        "changelog_url": "https://github.com/neo4j/neo4j/releases",
        "image": neo4j_image,
        "package": f"neo4j {neo4j_pkg_ver}" if neo4j_pkg_ver else "neo4j (missing)",
    })
    out.append({
        "name": "arail-lance-memory",
        "type": "service+python",
        "description": f"Agent workflow and memory service on :{os.getenv('LANCE_PORT', '7414')}",
        "version": lancedb_pkg_ver or "package not installed",
        "source_url": "https://github.com/lancedb/lancedb",
        "changelog_url": "https://github.com/lancedb/lancedb/releases",
        "image": "",
        "package": f"lancedb {lancedb_pkg_ver}" if lancedb_pkg_ver else "lancedb (missing)",
    })
    out.append({
        "name": "knowledge-canvas-lancedb",
        "type": "python",
        "description": "Vector index for semantic associations",
        "version": lancedb_pkg_ver or "package not installed",
        "source_url": "https://github.com/lancedb/lancedb",
        "changelog_url": "https://github.com/lancedb/lancedb/releases",
        "image": "",
        "package": f"lancedb {lancedb_pkg_ver}" if lancedb_pkg_ver else "lancedb (missing)",
    })

    return {"components": out}


@app.get("/api/admin/check-updates")
async def admin_check_updates():
    """Quick remote update check for all components."""
    mode = os.getenv("ARAIL_MODE", "airgapped")
    if mode == "airgapped":
        return {"airgapped": True, "updates_available": 0, "summary": "Airgapped — switch to Hybrid to check."}
    import subprocess as sp
    manifest_path = Path.cwd() / "components.json"
    if not manifest_path.exists():
        return {"updates_available": 0, "summary": "No components.json found."}
    manifest = json.loads(manifest_path.read_text())
    updates = 0
    names = []
    for c in manifest.get("components", []):
        ccmd = c.get("check_cmd")
        if not ccmd:
            continue
        try:
            r = sp.run(ccmd, shell=True, capture_output=True, text=True, timeout=30)
            if r.stdout.strip() and "up to date" not in r.stdout:
                updates += 1
                names.append(c["name"])
        except Exception:
            pass
    summary = f"{updates} update(s) available" + (f": {', '.join(names)}" if names else "") if updates else "All components up to date."
    return {"airgapped": False, "updates_available": updates, "summary": summary, "components": names}


@app.get("/api/system/graph")
async def system_graph():
    """Return the full system connectivity graph with live status."""
    import os, shutil, platform

    active_backend = os.getenv("MODEL_BACKEND", "auto").lower()
    if active_backend == "auto":
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            active_backend = "mlx"
        elif shutil.which("nvidia-smi"):
            active_backend = "cuda"
        else:
            active_backend = "cpu"

    nodes = [
        {"id": "portal", "label": "Portal", "group": "core", "type": "service",
         "desc": "FastAPI dashboard — SSE activity, goals, experiments",
         "status": "active", "port": 8080},
        {"id": "router", "label": "Model Router", "group": "core", "type": "service",
         "desc": f"Inference gateway — active backend: {active_backend}",
         "status": "active"},
        {"id": "activity", "label": "Activity Log", "group": "core", "type": "bus",
         "desc": f"Event bus — {len(activity_log.recent(200))} events, SSE fanout",
         "status": "active"},
        {"id": "memory", "label": "Memory Service", "group": "core", "type": "service",
         "desc": f"Agent workflow state + Lance recall on :{os.getenv('LANCE_PORT', '7414')}",
         "status": "active", "port": int(os.getenv('LANCE_PORT', '7414'))},
        {"id": "researcher", "label": "Researcher", "group": "agent", "type": "agent",
         "desc": f"Auto-research agent — {researcher.status}",
         "status": researcher.status if researcher.status != "idle" else "standby"},
        {"id": "curator", "label": "Curator", "group": "agent", "type": "agent",
         "desc": "Source vetting — proposes URLs, enforces consent",
         "status": "standby"},
        {"id": "consent", "label": "Consent Store", "group": "agent", "type": "store",
         "desc": f"{len(consent_store.list_allowed())} allowed, {len(consent_store.list_pending())} pending",
         "status": "active"},
        {"id": "goal_parser", "label": "Goal Parser", "group": "skill", "type": "skill",
         "desc": "NLP goal decomposition — domain, objectives, timeline",
         "status": "active"},
        {"id": "experiment_tracker", "label": "Experiments", "group": "skill", "type": "skill",
         "desc": f"{len(tracker.list_all())} experiments tracked",
         "status": "active"},
        {"id": "goal_store", "label": "Goal Store", "group": "skill", "type": "store",
         "desc": "Goal persistence — progress, history, reports",
         "status": "active"},
        {"id": "plugin_mgr", "label": "Plugins", "group": "plugin", "type": "service",
         "desc": f"GitHub plugin system — {len(plugin_mgr.list_plugins())} installed",
         "status": "active"},
        {"id": "pkb", "label": "Knowledge Base", "group": "core", "type": "store",
         "desc": "Personal knowledge base — sources, notes, agent findings",
         "status": "active"},
        {"id": "ttyd", "label": "Terminal", "group": "service", "type": "service",
         "desc": "ttyd WebSocket terminal", "status": "external", "port": 7681},
        {"id": "jupyter", "label": "Jupyter", "group": "service", "type": "service",
         "desc": "Notebook environment", "status": "external", "port": 8888},
    ]

    backend_labels = {
        "mlx": "MLX", "cuda": "CUDA", "cpu": "CPU",
        "openai_compat": "OpenAI-Compat", "huggingface": "HuggingFace",
        "openrouter": "OpenRouter", "claude": "Claude",
        "airllm": "AirLLM", "aerollm": "AeroLLM",
    }
    for name in BACKEND_MAP:
        is_active = name == active_backend
        locality = "local" if name in ("mlx", "cuda", "cpu") else "cloud"
        nodes.append({
            "id": f"backend_{name}", "label": backend_labels.get(name, name),
            "group": "backend", "type": "backend",
            "desc": f"{'LOCAL' if locality == 'local' else 'CLOUD'} — {'ACTIVE' if is_active else 'available'}",
            "status": "active" if is_active else "available",
            "locality": locality,
        })

    edges = [
        {"source": "portal", "target": "activity", "label": "SSE stream", "type": "data"},
        {"source": "portal", "target": "memory", "label": "workflow queries", "type": "data"},
        {"source": "portal", "target": "goal_store", "label": "goal CRUD", "type": "data"},
        {"source": "portal", "target": "experiment_tracker", "label": "experiments", "type": "data"},
        {"source": "portal", "target": "consent", "label": "approve/deny", "type": "control"},
        {"source": "portal", "target": "researcher", "label": "start/stop", "type": "control"},
        {"source": "portal", "target": "plugin_mgr", "label": "install/toggle", "type": "control"},
        {"source": "portal", "target": "ttyd", "label": "iframe", "type": "embed"},
        {"source": "portal", "target": "jupyter", "label": "iframe", "type": "embed"},
        {"source": "portal", "target": "goal_parser", "label": "parse", "type": "data"},
        {"source": "researcher", "target": "router", "label": "LLM calls", "type": "data"},
        {"source": "researcher", "target": "goal_store", "label": "progress", "type": "data"},
        {"source": "researcher", "target": "experiment_tracker", "label": "experiments", "type": "data"},
        {"source": "researcher", "target": "curator", "label": "sources", "type": "control"},
        {"source": "researcher", "target": "activity", "label": "events", "type": "data"},
        {"source": "researcher", "target": "memory", "label": "workflow state", "type": "data"},
        {"source": "researcher", "target": "pkb", "label": "findings", "type": "data"},
        {"source": "portal", "target": "pkb", "label": "browse/search", "type": "data"},
        {"source": "curator", "target": "consent", "label": "proposals", "type": "control"},
        {"source": "goal_parser", "target": "goal_store", "label": "parsed goal", "type": "data"},
        {"source": "router", "target": f"backend_{active_backend}", "label": "active", "type": "active"},
    ]
    for name in BACKEND_MAP:
        if name != active_backend:
            edges.append({"source": "router", "target": f"backend_{name}", "label": "", "type": "available"})

    return {"nodes": nodes, "edges": edges}


@app.get("/api/brand")
async def api_brand():
    """Return the current brand (name, tagline, logo, version).
    Lets dashboard JS personalize UI strings without hardcoding."""
    return _BRAND.to_dict()


# ── Chat API ───────────────────────────────────────────────────────────
# A lab-aware chat channel to the local model. Every turn includes the
# full lab_brain system prompt so the model answers in terms of this
# lab's capabilities, current state, and configured intent.

_CHAT_HISTORY_LIMIT = 20
_ROUTER_CACHE = None
_ROUTER_CACHE_SIGNATURE = None
_ROUTER_CACHE_LOCK = threading.Lock()


def _router_signature() -> tuple[str | None, ...]:
    return (
        os.getenv("MODEL_BACKEND"),
        os.getenv("MODEL_NAME"),
        os.getenv("MODEL_API_BASE"),
        os.getenv("MODEL_API_KEY"),
        os.getenv("LOCAL_API_PORT"),
    )


def _get_primary_router():
    from arail.router import ModelRouter

    global _ROUTER_CACHE, _ROUTER_CACHE_SIGNATURE
    signature = _router_signature()
    with _ROUTER_CACHE_LOCK:
        if _ROUTER_CACHE is None or _ROUTER_CACHE_SIGNATURE != signature:
            _ROUTER_CACHE = ModelRouter(billing_source="ui")
            _ROUTER_CACHE_SIGNATURE = signature
    return _ROUTER_CACHE


async def _warm_primary_router() -> None:
    try:
        await asyncio.to_thread(_get_primary_router)
        activity_log.emit("chat", "Primary chat model is loaded and ready.", "info")
    except Exception as e:  # noqa: BLE001
        activity_log.emit(
            "chat",
            f"Primary chat preload skipped: {type(e).__name__}: {e}",
            "warn",
        )


def _render_messages_for_backend(messages: list[dict[str, str]], backend: Any) -> str:
    tokenizer = getattr(backend, "tokenizer", None)
    if tokenizer is None:
        model = getattr(backend, "model", None)
        tokenizer = getattr(model, "tokenizer", None)

    if tokenizer is not None and hasattr(tokenizer, "apply_chat_template"):
        try:
            model_name = str(getattr(backend, "model_name", "") or "").lower()
            kwargs = {
                "tokenize": False,
                "add_generation_prompt": True,
            }
            if "qwen" in model_name:
                kwargs["enable_thinking"] = False
            rendered = tokenizer.apply_chat_template(
                messages,
                **kwargs,
            )
            if isinstance(rendered, str) and rendered.strip():
                return rendered
        except Exception:
            pass

    from arail import lab_brain

    return lab_brain.render_chat_transcript(messages)


def _clean_chat_reply(text: str) -> str:
    reply = (text or "").strip()
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
    if not reply:
        reply = "(model returned no text — try rephrasing)"
    return reply


def _build_chat_result(response: ModelResponse, *, wants_deep: bool) -> dict[str, Any]:
    reply = _clean_chat_reply(response.text or "")
    latency_sec = max(response.latency_ms / 1000.0, 0.001)
    tokens_per_sec = round(response.tokens_used / latency_sec, 1)
    cloud_cost_usd = None
    energy_cost_usd = None
    try:
        from arail.costs import cost_tracker
        last = cost_tracker.get_last_record() or {}
        cloud_cost_usd = last.get("cloud_cost_usd")
        energy_cost_usd = last.get("energy_cost_usd")
    except Exception:
        pass

    activity_log.emit("chat",
                      f"Chat turn · {response.tokens_used} tokens · "
                      f"{response.latency_ms:.0f} ms · {tokens_per_sec} t/s",
                      "info")

    return {
        "reply": reply,
        "backend": response.backend,
        "model": response.model,
        "latency_ms": response.latency_ms,
        "tokens_used": response.tokens_used,
        "tokens_per_sec": tokens_per_sec,
        "cloud_cost_usd": cloud_cost_usd,
        "energy_cost_usd": energy_cost_usd,
        "deep": bool(wants_deep),
        "error": None,
    }


_RUNTIME_BACKEND_CACHE: dict[tuple[str, str], Any] = {}


def _get_runtime_backend(runtime: str, model_id: str):
    """Build (or fetch from cache) a one-off OpenAICompatBackend that
    points at a specific local runtime — Ollama on :11434, the lab's
    own MLX OpenAI server on :11435, etc.

    Lets the chat tab's model gallery actually route a send through
    the runtime that owns the chosen model, instead of always
    falling back to the configured ``MODEL_BACKEND``.
    """
    cache_key = (runtime, model_id)
    cached = _RUNTIME_BACKEND_CACHE.get(cache_key)
    if cached is not None:
        return cached

    runtime_bases = {
        "ollama":      f"http://127.0.0.1:{os.getenv('OLLAMA_PORT', '11434')}/v1",
        "mlx-openai":  f"http://127.0.0.1:{os.getenv('MLX_OPENAI_PORT', '11435')}/v1",
        # Future: lmstudio, vllm, lmdeploy, etc. Same shape.
    }
    base = runtime_bases.get(runtime)
    if base is None:
        raise ValueError(f"unknown runtime: {runtime}")

    from arail.router.backends import OpenAICompatBackend
    be = OpenAICompatBackend.__new__(OpenAICompatBackend)
    import requests as _req
    be._session = _req.Session()
    be.base_url = base
    be.model_name = model_id
    be.api_key = "not-needed"   # local runtimes ignore auth
    # Mark for telemetry / log clarity.
    be.backend_name = f"{runtime}:openai_compat"
    _RUNTIME_BACKEND_CACHE[cache_key] = be
    return be


def _prepare_chat_context(
    *,
    message: str,
    history: list,
    backend_override: str | None,
    model_override: str | None,
    runtime_override: str | None = None,
) -> dict[str, Any]:
    from arail import lab_brain

    if not isinstance(history, list):
        history = []
    history = history[-_CHAT_HISTORY_LIMIT:]
    messages = lab_brain.build_chat_messages(message, history)

    optional_backend_name = str(backend_override or "").strip().lower() or None
    wants_deep = optional_backend_name in _OPTIONAL_CHAT_BACKEND_CONFIG
    deep_backend = None
    if wants_deep:
        try:
            assert optional_backend_name is not None
            deep_backend = _get_optional_chat_backend(optional_backend_name)
        except Exception as e:  # noqa: BLE001
            activity_log.emit(
                "chat",
                f"{optional_backend_name} init failed: {type(e).__name__}: {e}",
                "warn",
            )
            return {"error_result": _optional_backend_error_result(optional_backend_name, e)}

    # Per-message runtime override — when the chat tab's model
    # gallery picks a model from a runtime that ISN'T the configured
    # MODEL_BACKEND (e.g. user picks an Ollama-installed model while
    # MODEL_BACKEND=mlx), build a transient OpenAI-compat backend
    # pointed at the right runtime URL. Lets every locally-installed
    # model actually be routable from the same chat box.
    runtime_backend = None
    runtime_choice = (runtime_override or "").strip().lower() or None
    chosen_model = (model_override or "").strip() or None
    if runtime_choice and chosen_model and runtime_choice in ("ollama", "mlx-openai"):
        try:
            runtime_backend = _get_runtime_backend(runtime_choice, chosen_model)
        except Exception as e:  # noqa: BLE001
            activity_log.emit(
                "chat",
                f"Runtime override failed ({runtime_choice}/{chosen_model}): "
                f"{type(e).__name__}: {e}",
                "warn",
            )
            runtime_backend = None

    router = None
    if deep_backend is None and runtime_backend is None:
        try:
            router = _get_primary_router()
        except Exception as e:  # noqa: BLE001
            activity_log.emit("chat",
                              f"Router unavailable: {type(e).__name__}: {e}",
                              "error")
            return {
                "error_result": {
                    "reply": (
                        "The local model router isn't available yet. Run "
                        "`./arail setup` to install the backend for your "
                        "hardware, or set MODEL_BACKEND in `.env` to point at "
                        "an OpenAI-compatible local server (LM Studio, Ollama, "
                        "NVIDIA NIM)."
                    ),
                    "backend": None,
                    "error": str(e),
                }
            }

    override_model = (model_override or "").strip() or None
    if deep_backend is not None:
        active_backend = deep_backend
    elif runtime_backend is not None:
        active_backend = runtime_backend
    else:
        assert router is not None
        active_backend = router._backend
    prompt = _render_messages_for_backend(messages, active_backend)

    previous_model = None
    if override_model and hasattr(active_backend, "model_name"):
        if override_model != active_backend.model_name:
            previous_model = active_backend.model_name
            active_backend.model_name = override_model

    return {
        "router": router,
        "deep_backend": deep_backend,
        "runtime_backend": runtime_backend,
        "active_backend": active_backend,
        "previous_model": previous_model,
        "prompt": prompt,
        "optional_backend_name": optional_backend_name,
        "wants_deep": wants_deep,
    }


def _restore_chat_context(context: dict[str, Any]) -> None:
    active_backend = context.get("active_backend")
    previous_model = context.get("previous_model")
    if (
        previous_model is not None
        and active_backend is not None
        and hasattr(active_backend, "model_name")
    ):
        active_backend.model_name = previous_model


async def _stream_sync_iterator(iterator: Iterator[Any]) -> AsyncIterator[Any]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue()
    sentinel = object()

    def _worker() -> None:
        try:
            for item in iterator:
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)

    threading.Thread(target=_worker, daemon=True).start()

    while True:
        item = await queue.get()
        if item is sentinel:
            break
        if isinstance(item, Exception):
            raise item
        yield item


async def _run_chat_completion_stream(
    *,
    message: str,
    history: list,
    backend_override: str | None,
    model_override: str | None,
    temperature: float,
    top_p: float | None,
    max_tokens: int,
    runtime_override: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    context = _prepare_chat_context(
        message=message,
        history=history,
        backend_override=backend_override,
        model_override=model_override,
        runtime_override=runtime_override,
    )
    error_result = context.get("error_result")
    if error_result is not None:
        yield {"type": "final", **error_result}
        return

    wants_deep = bool(context["wants_deep"])
    optional_backend_name = context.get("optional_backend_name")
    prompt = str(context["prompt"])
    deep_backend = context.get("deep_backend")
    router = context.get("router")
    active_backend = context.get("active_backend")

    yield {
        "type": "start",
        "backend": getattr(active_backend, "backend_name", None) or getattr(router, "backend_name", None),
        "model": getattr(active_backend, "model_name", None),
        "deep": wants_deep,
    }

    try:
        if deep_backend is not None:
            response = await asyncio.to_thread(
                deep_backend.complete,
                prompt,
                max_tokens,
                temperature,
                top_p,
            )
            from arail.costs import cost_tracker
            cost_tracker.track(
                backend=response.backend,
                model=response.model,
                tokens_in=max(len(prompt) // 4, 1),
                tokens_out=response.tokens_used,
                latency_ms=response.latency_ms,
                source="ui",
            )
            if response.backend in ("airllm", "aerollm"):
                _record_aerollm_bench(
                    model=response.model,
                    tokens_out=response.tokens_used,
                    latency_ms=response.latency_ms,
                    prompt_chars=len(prompt),
                    max_tokens=max_tokens,
                )
            clean_reply = _clean_chat_reply(response.text)
            if clean_reply:
                yield {"type": "delta", "delta": clean_reply}
            yield {"type": "final", **_build_chat_result(response, wants_deep=wants_deep)}
            return

        final_response: ModelResponse | None = None
        accumulated = ""
        runtime_backend = context.get("runtime_backend") if isinstance(context, dict) else None
        if runtime_backend is not None:
            # Runtime override: OpenAICompatBackend doesn't expose
            # token streaming, so we do a single complete() on a
            # worker thread and emit the whole reply as one delta.
            # Keeps the UI happy (it expects deltas + final) without
            # forcing per-runtime streaming bridges.
            response = await asyncio.to_thread(
                runtime_backend.complete,
                prompt, max_tokens, temperature, top_p,
            )
            from arail.costs import cost_tracker
            cost_tracker.track(
                backend=response.backend, model=response.model,
                tokens_in=max(len(prompt) // 4, 1),
                tokens_out=response.tokens_used,
                latency_ms=response.latency_ms, source="ui",
            )
            clean_reply = _clean_chat_reply(response.text)
            if clean_reply:
                yield {"type": "delta", "delta": clean_reply}
            yield {"type": "final", **_build_chat_result(response, wants_deep=wants_deep)}
            return

        if router is None:
            yield {
                "type": "final",
                "reply": "The model router is not available for streaming.",
                "backend": None,
                "error": "router unavailable",
            }
            return
        async for item in _stream_sync_iterator(
            router.stream_complete(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )
        ):
            if isinstance(item, ModelResponse):
                final_response = item
                continue
            delta = str(item or "")
            if not delta:
                continue
            accumulated += delta
            yield {"type": "delta", "delta": delta}

        if final_response is None:
            final_response = ModelResponse(
                text=accumulated,
                model=str(getattr(active_backend, "model_name", "unknown")),
                tokens_used=max(len(accumulated.split()), 0),
                backend=str(getattr(router, "backend_name", "unknown")),
                latency_ms=0.0,
                cost_usd=0.0,
            )

        yield {"type": "final", **_build_chat_result(final_response, wants_deep=wants_deep)}
    except Exception as e:  # noqa: BLE001
        activity_log.emit("chat",
                          f"Inference failed: {type(e).__name__}: {str(e)[:120]}",
                          "error")
        yield {
            "type": "final",
            "reply": f"Inference failed: {e}",
            "backend": (
                getattr(deep_backend, "backend_name", optional_backend_name)
                if wants_deep
                else getattr(router, "backend_name", None)
            ),
            "error": str(e),
        }
    finally:
        _restore_chat_context(context)


async def _run_chat_completion(
    *,
    message: str,
    history: list,
    backend_override: str | None,
    model_override: str | None,
    temperature: float,
    top_p: float | None,
    max_tokens: int,
    runtime_override: str | None = None,
) -> dict:
    """Shared core of /api/chat and /api/teacher/ask.

    Returns the same dict the /api/chat endpoint emits so both surfaces
    look identical to the UI layer: {reply, backend, model, latency_ms,
    tokens_used, tokens_per_sec, cloud_cost_usd, energy_cost_usd,
    deep, error}. On failure the dict carries a user-readable ``reply``
    plus an ``error`` string — callers never need to catch."""
    context = _prepare_chat_context(
        message=message,
        history=history,
        backend_override=backend_override,
        model_override=model_override,
        runtime_override=runtime_override,
    )
    error_result = context.get("error_result")
    if error_result is not None:
        return error_result

    wants_deep = bool(context["wants_deep"])
    optional_backend_name = context.get("optional_backend_name")
    deep_backend = context.get("deep_backend")
    runtime_backend = context.get("runtime_backend")
    router = context.get("router")
    prompt = str(context["prompt"])

    try:
        if deep_backend is not None:
            import asyncio as _aio
            response = await _aio.to_thread(
                deep_backend.complete,
                prompt, max_tokens, temperature, top_p,
            )
            from arail.costs import cost_tracker
            cost_tracker.track(
                backend=response.backend,
                model=response.model,
                tokens_in=max(len(prompt) // 4, 1),
                tokens_out=response.tokens_used,
                latency_ms=response.latency_ms,
                source="ui",
            )
            if response.backend in ("airllm", "aerollm"):
                _record_aerollm_bench(
                    model=response.model,
                    tokens_out=response.tokens_used,
                    latency_ms=response.latency_ms,
                    prompt_chars=len(prompt),
                    max_tokens=max_tokens,
                )
        elif runtime_backend is not None:
            # User picked a model from a non-default runtime
            # (e.g. an Ollama model while MODEL_BACKEND=mlx). Run
            # the OpenAI-compat call on a worker thread — urllib /
            # requests is blocking.
            import asyncio as _aio
            response = await _aio.to_thread(
                runtime_backend.complete,
                prompt, max_tokens, temperature, top_p,
            )
            from arail.costs import cost_tracker
            cost_tracker.track(
                backend=response.backend,
                model=response.model,
                tokens_in=max(len(prompt) // 4, 1),
                tokens_out=response.tokens_used,
                latency_ms=response.latency_ms,
                source="ui",
            )
        else:
            assert router is not None
            response = router.complete(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )
    except Exception as e:  # noqa: BLE001
        activity_log.emit("chat",
                          f"Inference failed: {type(e).__name__}: {str(e)[:120]}",
                          "error")
        return {
            "reply": f"Inference failed: {e}",
            "backend": (
                getattr(deep_backend, "backend_name", optional_backend_name)
                if wants_deep
                else getattr(router, "backend_name", None)
            ),
            "error": str(e),
        }
    finally:
        _restore_chat_context(context)

    return _build_chat_result(response, wants_deep=wants_deep)


@app.post("/api/chat")
async def api_chat(request: Request):
    """Send one user message to the local model with full lab context.

    Request JSON:
        {
          "message": "What commands can I run?",
          "history": [{"role": "user"|"assistant", "content": "..."}],
          "backend": "aerollm" (optional),
          "model": "model-name" (optional, network backends only),
          "temperature": 0.7, "top_p": 0.9, "max_tokens": 512
        }

    Response JSON: see ``_run_chat_completion`` for shape. Errors are
    returned as a well-formed dict with ``error`` set — never raised."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = (body.get("message") or "").strip()
    if not message:
        return {"error": "message required"}

    tp_raw = body.get("top_p")
    try:
        top_p = float(tp_raw) if tp_raw is not None and tp_raw != "" else None
    except (TypeError, ValueError):
        top_p = None

    return await _run_chat_completion(
        message=message,
        history=body.get("history") or [],
        backend_override=body.get("backend"),
        model_override=body.get("model"),
        temperature=float(body.get("temperature") or 0.7),
        top_p=top_p,
        max_tokens=int(body.get("max_tokens") or 512),
        runtime_override=body.get("runtime"),
    )


@app.post("/api/chat/stream")
async def api_chat_stream(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = (body.get("message") or "").strip()
    if not message:
        async def _empty() -> AsyncIterator[str]:
            yield json.dumps({"type": "final", "error": "message required"}) + "\n"
        return StreamingResponse(_empty(), media_type="application/x-ndjson")

    tp_raw = body.get("top_p")
    try:
        top_p = float(tp_raw) if tp_raw is not None and tp_raw != "" else None
    except (TypeError, ValueError):
        top_p = None

    async def _generate() -> AsyncIterator[str]:
        async for event in _run_chat_completion_stream(
            message=message,
            history=body.get("history") or [],
            backend_override=body.get("backend"),
            model_override=body.get("model"),
            temperature=float(body.get("temperature") or 0.7),
            top_p=top_p,
            max_tokens=int(body.get("max_tokens") or 512),
            runtime_override=body.get("runtime"),
        ):
            yield json.dumps(event, default=str) + "\n"

    return StreamingResponse(
        _generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Optional heavy-backend cache — AirLLM and AeroLLM both need slow,
# disk-heavy model init. Cache whichever one the user picks so later
# chat turns reuse the loaded instance.
_OPTIONAL_CHAT_BACKEND_CACHE: dict[str, Any] = {}

_OPTIONAL_CHAT_BACKEND_CONFIG: dict[str, dict[str, str]] = {
    "airllm": {
        "label": "AirLLM",
        "class_name": "AirLLMBackend",
        "install_command": "pip install airllm",
        "model_env": "AIRLLM_MODEL",
        "default_model": "meta-llama/Llama-3.1-70B",
    },
    "aerollm": {
        "label": "AeroLLM",
        "class_name": "AeroLLMBackend",
        "install_command": (
            "cd aerollm/crates/aero-api && maturin develop --release"
        ),
        "model_env": "AEROLLM_MODEL",
        "default_model": "Qwen2.5-7B-Instruct",
    },
}


def _get_optional_chat_backend(name: str):
    config = _OPTIONAL_CHAT_BACKEND_CONFIG.get(name)
    if config is None:
        raise ValueError(f"Unknown optional chat backend: {name}")
    backend = _OPTIONAL_CHAT_BACKEND_CACHE.get(name)
    if backend is None:
        from arail.router import backends as router_backends

        backend_cls = getattr(router_backends, config["class_name"])
        backend = backend_cls()
        backend.backend_name = name
        _OPTIONAL_CHAT_BACKEND_CACHE[name] = backend
    return backend


def _optional_backend_error_result(name: str | None, error: Exception) -> dict[str, Any]:
    backend_name = name or "optional-backend"
    config = _OPTIONAL_CHAT_BACKEND_CONFIG.get(backend_name, {})
    label = config.get("label", backend_name)
    model_env = config.get("model_env", "MODEL_NAME")
    default_model = config.get("default_model", "meta-llama/Llama-3.1-70B")
    model_name = os.getenv(model_env, default_model)
    gated_hint = ""
    if model_name.lower().startswith("meta-llama/"):
        gated_hint = (
            " Accept the model license on Hugging Face first, then run "
            "huggingface-cli login or export HF_TOKEN before downloading it."
        )
    return {
        "reply": (
            f"{label} isn't ready on this lab. Install it "
            f"(`{config.get('install_command', 'pip install ' + backend_name)}`) "
            f"and ensure {model_env} in .env points at a downloaded model."
            f"{gated_hint}\n\nError: {error}"
        ),
        "backend": backend_name,
        "error": str(error),
    }


# ── AeroLLM bench capture ───────────────────────────────────────
# Every deep-call through AeroLLM appends one JSON line to
# lab/data/aerollm-bench.jsonl. The /api/aerollm/bench endpoint
# aggregates by model so the dashboard can show "on your machine,
# X tokens/min averaged over N calls." This is the proof-ground
# for any AeroLLM optimizations — before/after numbers land here.

def _aerollm_bench_file() -> Path:
    from arail.config import DATA_DIR
    return DATA_DIR / "aerollm-bench.jsonl"


def _record_aerollm_bench(*, model: str, tokens_out: int, latency_ms: float,
                          prompt_chars: int, max_tokens: int) -> None:
    """Append one bench record. Never raises — a bench-log failure
    shouldn't break a user's chat reply."""
    try:
        from datetime import datetime, timezone
        path = _aerollm_bench_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Include hardware hint so benches from different machines
        # stay comparable when this file gets synced between labs.
        import platform
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "tokens_out": int(tokens_out or 0),
            "latency_ms": float(latency_ms or 0),
            "tokens_per_sec": round((tokens_out or 0) / max(latency_ms / 1000, 0.001), 2),
            "prompt_chars": int(prompt_chars or 0),
            "max_tokens": int(max_tokens or 0),
            "platform": platform.platform(),
            "cpu": platform.processor() or platform.machine(),
        }
        with open(path, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception:
        pass


@app.get("/api/aerollm/bench")
async def api_aerollm_bench():
    """Return aggregated AeroLLM throughput stats per model.

    Shape::

        {
          "bench": {
                        "meta-llama/Llama-3.1-70B": {
              "runs": 4,
              "avg_tokens_per_sec": 0.17,
              "avg_tokens_per_min": 10.2,
              "median_latency_ms": 582340,
              "total_tokens": 248,
              "last_ts": "2026-04-18T14:02:11Z"
            }
          },
          "total_runs": 4,
          "platform": "Darwin 25.4.0 arm64"
        }
    """
    path = _aerollm_bench_file()
    if not path.exists():
        return {"bench": {}, "total_runs": 0, "platform": None}

    import platform, statistics
    by_model: dict[str, list[dict]] = {}
    try:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            model = r.get("model") or "unknown"
            by_model.setdefault(model, []).append(r)
    except OSError:
        return {"bench": {}, "total_runs": 0, "platform": None}

    out: dict[str, Any] = {}
    total = 0
    for model, rows in by_model.items():
        total += len(rows)
        tps = [r.get("tokens_per_sec", 0) for r in rows if r.get("tokens_per_sec")]
        lat = [r.get("latency_ms", 0) for r in rows if r.get("latency_ms")]
        avg_tps = round(sum(tps) / len(tps), 3) if tps else 0
        out[model] = {
            "runs": len(rows),
            "avg_tokens_per_sec": avg_tps,
            "avg_tokens_per_min": round(avg_tps * 60, 1),
            "median_latency_ms": round(statistics.median(lat), 0) if lat else 0,
            "total_tokens": sum(int(r.get("tokens_out") or 0) for r in rows),
            "last_ts": rows[-1].get("ts"),
        }

    return {
        "bench": out,
        "total_runs": total,
        "platform": platform.platform(),
    }


@app.get("/api/chat/models")
async def api_chat_models():
    """Return the model catalog for the current backend.

    For OpenAI-compatible backends (LM Studio, Ollama, NVIDIA NIM,
    OpenRouter), we query the server's ``/v1/models`` endpoint and
    list every model it advertises. For single-model backends
    (MLX, llama.cpp, AeroLLM, Claude, HF Inference), we return just
    the configured ``MODEL_NAME`` so the dropdown still renders.

    The dashboard Tuning row uses this to populate its Model picker.
    """
    try:
        router = _get_primary_router()
    except Exception as e:  # noqa: BLE001
        return {"backend": None, "current": None, "models": [], "error": str(e)}

    backend_name = router.backend_name
    be = router._backend
    current = getattr(be, "model_name", None) or os.getenv("MODEL_NAME", "default")
    models: list[str] = []

    # Only these backends have a useful /models listing today.
    if backend_name == "openai_compat":
        try:
            import requests
            base = getattr(be, "base_url", "").rstrip("/")
            key = getattr(be, "api_key", "not-needed")
            r = requests.get(
                f"{base}/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=5,
            )
            if r.status_code == 200:
                data = r.json()
                # OpenAI shape: {data: [{id, ...}, ...]}. Ollama uses
                # the same shape. LM Studio too.
                models = [m.get("id") for m in data.get("data", []) if m.get("id")]
        except Exception:
            models = []
    elif backend_name == "openrouter":
        try:
            import requests
            key = getattr(be, "api_key", "")
            r = requests.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=5,
            )
            if r.status_code == 200:
                data = r.json()
                models = [m.get("id") for m in data.get("data", []) if m.get("id")]
        except Exception:
            models = []

    # Always include the currently-loaded model — even if /models
    # listed it, keeping it first signals "you're using this one."
    if current and current not in models:
        models.insert(0, current)
    if not models and current:
        models = [current]

    # For single-model local backends, scan the on-disk models dir
    # so the help block under the dropdown can tell the user:
    # "here's where they live, here's what's already installed, and
    # here's the command to add more."
    local_models: list[str] = []
    install_hint: dict | None = None
    if backend_name in ("mlx", "cpu", "airllm", "aerollm", "cuda"):
        models_dir = Path(os.getenv("ARAIL_MODELS_DIR", "lab/models"))
        if models_dir.exists():
            try:
                local_models = sorted(
                    p.name for p in models_dir.iterdir()
                    if p.is_dir()
                    and not p.name.startswith(".")
                    and not p.name.startswith("_")
                    # Skip cache dirs (aerollm_cache, hf_cache, etc.) —
                    # they're shards, not loadable models.
                    and "_cache" not in p.name
                )
            except OSError:
                local_models = []

        # Backend-specific "download a new one" example. MLX uses
        # mlx-community/ repos; CPU uses GGUF; CUDA uses full-precision
        # Hugging Face weights. The hint surfaces in the dashboard.
        if backend_name == "mlx":
            example = (
                "huggingface-cli download mlx-community/Llama-3.2-3B-Instruct-4bit "
                f"--local-dir {models_dir}/Llama-3.2-3B-Instruct-4bit"
            )
        elif backend_name == "cpu":
            example = (
                "huggingface-cli download Qwen/Qwen3-1.7B-GGUF "
                f"--local-dir {models_dir}/Qwen3-1.7B-GGUF"
            )
        elif backend_name == "cuda":
            example = (
                "huggingface-cli download Qwen/Qwen3-8B "
                f"--local-dir {models_dir}/Qwen3-8B"
            )
        elif backend_name == "airllm":
            example = (
                "huggingface-cli download meta-llama/Llama-3.1-70B "
                f"--local-dir {models_dir}/Llama-3.1-70B --local-dir-use-symlinks False"
            )
        else:  # aerollm
            example = (
                "huggingface-cli download meta-llama/Llama-3.1-70B "
                f"--local-dir {models_dir}/Llama-3.1-70B --local-dir-use-symlinks False"
            )

        install_hint = {
            "dir": str(models_dir),
            "example_command": example,
            "docs_anchor": "sources/seeds/model-building/03-huggingface-models.md",
            "restart_note": (
                "After downloading, set MODEL_NAME in .env to match the "
                "folder name, then ./arail restart. Live in-session swap "
                "isn't supported on local backends — the model has to be "
                "loaded into memory, which takes seconds to minutes."
            ),
        }

    # Deep-model info — independent of the active backend. Tells
    # the UI what giant model is wired up behind the "Deep model"
    # toggle. Separate field because users can flip that toggle
    # regardless of which primary backend they're on.
    #
    # AirLLM is today's active deep backend (max-tier install). AeroLLM
    # is declared but dormant until it's stable; when it ships, the
    # default below flips back.
    air_model_name = os.getenv("AIRLLM_MODEL", "meta-llama/Llama-3.1-70B")
    deep_model_name = air_model_name
    # Look up the spec sheet so the Frontier chip hover can show
    # strengths, benchmarks, and license at a glance. Registry lives
    # in src/arail/model_specs.py — users edit it to add new models.
    from arail.model_specs import lookup as _spec_lookup
    spec = _spec_lookup(deep_model_name)

    deep_info = {
        "model": deep_model_name,
        # Whether the active deep backend (airllm) is importable. When
        # False, the UI can swap the toggle for an install hint.
        "installed": _is_airllm_installed(),
        # Rough size hint the UI can render in the chip. We extract
        # a parameter count from the model name when present
        # (e.g. "Qwen3-235B-A22B" → "235B"); the user-entered
        # AIRLLM_MODEL decides what shows.
        "param_hint": _extract_param_hint(deep_model_name),
        # Spec sheet — populated from the registry. Null when the
        # configured model isn't known; the UI shows a "click to
        # document this model" placeholder in that case.
        "spec": spec,
        # Server-side default for the dashboard deep toggle. The UI
        # still lets the browser override this after first render.
        "default_enabled": os.getenv("ARAIL_CHAT_DEEP_DEFAULT", "false").lower() == "true",
        # Meta Llama and similar repos require a HF login/token before
        # download. Surface the caveat so the dashboard can show it in
        # install/help copy instead of failing generically.
        "gated": deep_model_name.lower().startswith("meta-llama/"),
    }

    if deep_info["gated"]:
        deep_info["auth_hint"] = (
            "Accept the Hugging Face license for this model, then run "
            "huggingface-cli login or export HF_TOKEN before downloading."
        )

    aero_model_name = os.getenv("AEROLLM_MODEL", "zai-org/GLM-5.1")
    optional_backends = [
        {
            "id": "airllm",
            "label": "AirLLM",
            "model": air_model_name,
            "installed": _is_airllm_installed(),
            "param_hint": _extract_param_hint(air_model_name),
            "gated": air_model_name.lower().startswith("meta-llama/"),
            "install_command": "pip install airllm",
            "description": "Active deep-chat backend — layer-streaming for 70B+ local models (max tier).",
        },
        {
            "id": "aerollm",
            "label": "AeroLLM",
            "model": aero_model_name,
            "installed": _is_aerollm_installed(),
            "param_hint": _extract_param_hint(aero_model_name),
            "gated": aero_model_name.lower().startswith("meta-llama/"),
            "install_command": (
                "pip install "
                + os.getenv("AEROLLM_PACKAGE", "git+https://github.com/cdarnell/aerollm@main")
            ),
            "description": "Future deep-chat backend (Arail's Rust runtime). Dormant until stable.",
        },
    ]
    for entry in optional_backends:
        if entry["gated"]:
            entry["auth_hint"] = (
                "Accept the Hugging Face license for this model, then run "
                "huggingface-cli login or export HF_TOKEN before downloading."
            )

    default_optional_backend = _default_teacher_backend()

    # Unified gallery payload — every locally-installed model across
    # MLX (in-process + OpenAI server) + Ollama, plus the curated
    # catalog with installed_state. Powers the chat tab's model
    # gallery (replaces the active-backend-only dropdown so users
    # see models from EVERY runtime they have running).
    try:
        from arail.chat import gallery_view
        gallery = gallery_view()
    except Exception as e:  # noqa: BLE001
        gallery = {"installed": [], "catalog": [], "runtime_counts": {},
                   "error": f"{type(e).__name__}: {e}"}

    return {
        "backend": backend_name,
        "current": current,
        "models": models,
        "switchable": backend_name in ("openai_compat", "openrouter"),
        "local_models": local_models,
        "install_hint": install_hint,
        "optional_backends": optional_backends,
        "default_optional_backend": default_optional_backend,
        "deep": deep_info,
        # New (chat model gallery + cross-runtime selector).
        "gallery": gallery,
    }


def _is_aerollm_installed() -> bool:
    """aerollm is optional — check without importing since the import
    itself is heavy (drags torch)."""
    import importlib.util
    return importlib.util.find_spec("aerollm") is not None


def _is_airllm_installed() -> bool:
    import importlib.util
    return importlib.util.find_spec("airllm") is not None


def _default_teacher_backend() -> str:
    return "airllm" if _is_airllm_installed() else "aerollm"


def _extract_param_hint(model_name: str) -> str:
    """Parse '235B', '70B', '754B' etc. out of a HF repo name."""
    import re as _re
    match = _re.search(r"(\d+(?:\.\d+)?)([BMK])\b", model_name, _re.IGNORECASE)
    if match:
        return f"{match.group(1)}{match.group(2).upper()}"
    return ""


@app.get("/api/chat/system-prompt")
async def api_chat_system_prompt():
    """Return the currently-rendered system prompt.

    Useful for debugging, for transparency ("what does the model know?"),
    and for the upcoming lab-tutor feature where the user can inspect and
    edit the prompt before sending a goal.
    """
    from arail import lab_brain
    return {
        "prompt": lab_brain.build_system_prompt(
            include_capabilities=True,
            include_state=True,
        ),
    }


@app.get("/api/system/health")
async def system_health():
    """Return live system specs, resource usage, and service health."""
    import importlib.util
    import os, sys, shutil, platform

    # CPU
    cpu_count = os.cpu_count() or 0

    # Memory
    try:
        psutil = __import__("psutil")
        mem = psutil.virtual_memory()
        ram_total_gb = round(mem.total / (1024**3), 1)
        ram_used_gb = round(mem.used / (1024**3), 1)
        ram_pct = mem.percent
        disk = psutil.disk_usage(str(Path.cwd()))
        disk_total_gb = round(disk.total / (1024**3), 1)
        disk_free_gb = round(disk.free / (1024**3), 1)
        disk_pct = disk.percent
    except ImportError:
        # Fallback without psutil
        ram_total_gb = 0
        ram_used_gb = 0
        ram_pct = 0
        disk_total_gb = 0
        disk_free_gb = 0
        disk_pct = 0
        if platform.system() == "Darwin":
            try:
                import subprocess
                ram_total_gb = round(int(subprocess.check_output(
                    ["sysctl", "-n", "hw.memsize"]).strip()) / (1024**3), 1)
                df_out = subprocess.check_output(["df", "-g", "."]).decode().split("\n")[1].split()
                disk_total_gb = int(df_out[1])
                disk_free_gb = int(df_out[3])
                disk_pct = round((1 - disk_free_gb / disk_total_gb) * 100, 1) if disk_total_gb else 0
            except Exception:
                pass

    # Active backend
    active_backend = os.getenv("MODEL_BACKEND", "auto").lower()
    model_name = os.getenv("MODEL_NAME", "none")

    # GPU
    gpu_info = None
    if shutil.which("nvidia-smi"):
        try:
            import subprocess
            name = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                timeout=5).decode().strip().split("\n")[0]
            vram = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                timeout=5).decode().strip().split("\n")[0]
            gpu_info = {"name": name, "vram_mb": int(vram)}
        except Exception:
            pass

    # Spec tier
    tier = "minimum"
    deep_enabled = os.getenv("AEROLLM_RESEARCH", "false").lower() == "true"
    if deep_enabled:
        tier = "deep"
    elif ram_total_gb >= 16 and disk_free_gb >= 40:
        tier = "full"
    elif ram_total_gb >= 8 and disk_free_gb >= 20:
        tier = "standard"

    # Python
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    bind = os.getenv("BIND_ADDR", "127.0.0.1")
    notebook_port = int(os.getenv("NOTEBOOK_PORT", "8888"))
    ttyd_port = int(os.getenv("TTYD_PORT", "7681"))
    ollama_port = int(os.getenv("OLLAMA_PORT", "11434"))
    lance_port = int(os.getenv("LANCE_PORT", "7414"))
    marimo_port = int(os.getenv("MARIMO_PORT", "2718"))
    open_notebook_port = int(os.getenv("OPEN_NOTEBOOK_PORT", "8502"))
    neo4j_bolt_port = int(os.getenv("NEO4J_BOLT_PORT", "7687"))

    portal_up, ttyd_up, notebook_up, ollama_up, lance_up, marimo_up, open_notebook_up, neo4j_up = await asyncio.gather(
        _port_open(bind, int(os.getenv("PORTAL_PORT", "8080"))),
        _port_open(bind, ttyd_port),
        _port_open(bind, notebook_port),
        _port_open(bind, ollama_port),
        _port_open(bind, lance_port),
        _port_open(bind, marimo_port),
        _port_open(bind, open_notebook_port),
        _port_open(bind, neo4j_bolt_port),
    )

    # ── Local-inference detection ────────────────────────────────
    # Surfaces what's actually serving an OpenAI-compatible API on
    # this machine right now. Powers the Chat tab's "My Machine"
    # tile so the user sees Ollama:11434 + MLX:11435 etc. instead of
    # a generic "Local — no key needed."
    #
    # Ports come from common defaults; LAB_* env overrides take
    # precedence so a user running on non-standard ports gets
    # accurate detection.
    mlx_openai_port = int(os.getenv("MLX_OPENAI_PORT", "11435"))
    lmstudio_port = int(os.getenv("LMSTUDIO_PORT", "1234"))
    vllm_port = int(os.getenv("VLLM_PORT", "8000"))
    lmdeploy_port = int(os.getenv("LMDEPLOY_PORT", "23333"))
    tgi_port = int(os.getenv("TGI_PORT", "8080"))    # HF text-generation-inference; clashes with portal default — only counts when on a non-portal port
    textgen_webui_port = int(os.getenv("TEXTGEN_WEBUI_PORT", "5000"))

    # Two-stage detection: (1) is anything listening, (2) does it
    # actually speak the OpenAI-compat protocol? Stage 2 prevents
    # false positives from unrelated services (OrbStack on :8000,
    # macOS ControlCenter on :5000, etc.).
    async def _probe_openai_compat(host: str, port: int, path: str = "/v1/models") -> bool:
        """True iff GET <path> returns a JSON body with a `data`
        or `models` array. Tight timeout so the health endpoint
        stays snappy.

        Runs urllib in a worker thread (not the event loop) so the
        gather() actually achieves concurrency — urlopen is blocking.
        """
        if not await _port_open(host, port):
            return False

        def _do_probe() -> bool:
            try:
                import json as _json, urllib.request as _ureq
                req = _ureq.Request(f"http://{host}:{port}{path}", method="GET")
                with _ureq.urlopen(req, timeout=3.0) as resp:
                    if resp.status >= 400:
                        return False
                    data = _json.loads(resp.read())
                # Common shapes: OpenAI-compat /v1/models returns
                # {"data": [...]}; HF text-generation-inference's
                # /info uses {"models": [...]}.
                return isinstance(data, dict) and any(
                    isinstance(data.get(k), list) for k in ("data", "models")
                )
            except Exception:
                return False

        return await asyncio.to_thread(_do_probe)

    portal_self = int(os.getenv("PORTAL_PORT", "8080"))
    # Skip the TGI probe when its port matches the lab portal — we
    # can't probe ourselves with /v1/models (it'll 404), and even if
    # we could the result wouldn't mean what the user thinks.
    tgi_probe = (
        asyncio.sleep(0, result=False)
        if tgi_port == portal_self
        else _probe_openai_compat(bind, tgi_port, "/info")
    )

    mlx_up, lmstudio_up, vllm_up, lmdeploy_up, tgi_up, textgen_up = await asyncio.gather(
        _probe_openai_compat(bind, mlx_openai_port),
        _probe_openai_compat(bind, lmstudio_port),
        _probe_openai_compat(bind, vllm_port),
        _probe_openai_compat(bind, lmdeploy_port),
        tgi_probe,
        _probe_openai_compat(bind, textgen_webui_port),
    )

    # Resolve which runtime backs the lab's primary chat path. The
    # MODEL_BACKEND env var picks the in-process backend (mlx, cuda,
    # cpu via the router); the OpenAI-compat endpoints below are
    # detection-only — useful when the user wants to point Custom
    # Endpoint at one of them.
    primary_label_map = {
        "mlx": "MLX (in-process via mlx_lm)",
        "cuda": "vLLM / CUDA (in-process)",
        "cpu": "llama.cpp (in-process)",
        "auto": "auto-detect",
    }
    primary_backend = {
        "tech": primary_label_map.get(active_backend, active_backend),
        "model": model_name if model_name and model_name != "none" else None,
        "in_process": True,
        "port": None,
    }

    detected_endpoints: list[dict[str, Any]] = []
    for tech, port, up, openai_path in (
        ("Ollama", ollama_port, ollama_up, "/v1"),
        ("MLX OpenAI server", mlx_openai_port, mlx_up, "/v1"),
        ("LM Studio", lmstudio_port, lmstudio_up, "/v1"),
        ("vLLM", vllm_port, vllm_up, "/v1"),
        ("LMDeploy", lmdeploy_port, lmdeploy_up, "/v1"),
        ("HF text-generation-inference", tgi_port, tgi_up, "/"),
        ("text-generation-webui", textgen_webui_port, textgen_up, "/v1"),
    ):
        if up:
            detected_endpoints.append({
                "tech": tech,
                "port": port,
                "url": f"http://{bind}:{port}{openai_path}",
            })

    local_inference = {
        "primary": primary_backend,
        "endpoints": detected_endpoints,
        "host": bind,
    }

    docker_ok = _docker_available()
    activity_file = Path.cwd() / "lab" / "data" / "activity.jsonl"
    workflow_file = Path.cwd() / "lab" / "data" / "agent_workflows.json"
    current_goal = goal_store.get_current()
    current_model_path = os.getenv("ARAIL_MODELS_DIR", str(Path.cwd() / "models"))
    from arail.config import DATA_DIR, PKB_ROOT

    def add_check(
        check_id: str,
        name: str,
        ok: bool,
        detail: str,
        *,
        required: bool = True,
        category: str = "service",
    ) -> dict[str, Any]:
        return {
            "id": check_id,
            "name": name,
            "ok": ok,
            "detail": detail,
            "required": required,
            "category": category,
        }

    service_checks = [
        add_check("portal", "Portal HTTP", portal_up, f"http://{bind}:{os.getenv('PORTAL_PORT', '8080')}", category="service"),
        add_check("activity_log", "Activity Log", activity_file.exists(), str(activity_file), category="storage"),
        add_check("pkb_root", "Knowledge Base Root", PKB_ROOT.exists(), str(PKB_ROOT), category="storage"),
        add_check("lab_data", "Lab Data Directory", DATA_DIR.exists(), str(DATA_DIR), category="storage"),
        add_check("model_backend", "Model Backend Selected", bool(active_backend and active_backend != "auto"), active_backend, category="config"),
        add_check("model_name", "Model Name Configured", bool(model_name and model_name != "none"), model_name or "unset", category="config"),
        add_check("models_dir", "Models Directory", Path(current_model_path).exists(), current_model_path, category="storage"),
        add_check("goal_store", "Goal Store", current_goal is not None or (DATA_DIR / "goals").exists(), str(DATA_DIR / 'goals'), category="storage"),
        add_check("ttyd", "ttyd Terminal", ttyd_up, f"port {ttyd_port}", required=False, category="service"),
        add_check("notebook", "Notebook", notebook_up, f"port {notebook_port}", required=False, category="service"),
        add_check("docker", "Docker Engine", docker_ok, "compose-backed services", required=False, category="service"),
        add_check("marimo", "Marimo", marimo_up and _container_running("arail-marimo"), f"port {marimo_port}", required=False, category="service"),
        add_check("open_notebook", "Open Notebook", open_notebook_up and _container_running("arail-open-notebook"), f"port {open_notebook_port}", required=False, category="service"),
        add_check("ollama_binary", "Ollama Installed", shutil.which("ollama") is not None, "ollama CLI", required=False, category="dependency"),
        add_check("ollama_api", "Ollama API", ollama_up, f"port {ollama_port}", required=False, category="service"),
        add_check("agent_workflows", "Agent Workflow Store", workflow_file.exists(), str(workflow_file), required=False, category="storage"),
        add_check("lance_service", "Lance Memory Service", lance_up, f"port {lance_port}", required=False, category="service"),
        add_check("kc_frontend", "Knowledge Canvas Frontend", KC_FRONTEND_DIST_DIR.exists() or KC_FRONTEND_DIR.exists(), str(KC_FRONTEND_DIST_DIR if KC_FRONTEND_DIST_DIR.exists() else KC_FRONTEND_DIR), required=False, category="association"),
        add_check("kc_backend", "Knowledge Canvas Store", _knowledge_canvas_store is not None or (knowledge_canvas_app is not None and hasattr(knowledge_canvas_app.state, "store")), "mounted at /knowledge-canvas", required=False, category="association"),
        add_check("lancedb", "LanceDB Package", importlib.util.find_spec("lancedb") is not None, os.getenv("LANCE_PATH", "./lab/data/lance"), required=False, category="association"),
        add_check("neo4j_pkg", "Neo4j Driver", importlib.util.find_spec("neo4j") is not None, os.getenv("NEO4J_URI", "bolt://localhost:7687"), required=False, category="association"),
        add_check("neo4j_bolt", "Neo4j Bolt", neo4j_up, f"port {neo4j_bolt_port}", required=False, category="association"),
    ]

    required_checks = [c for c in service_checks if c["required"]]
    passing_required = sum(1 for c in required_checks if c["ok"])
    passing_total = sum(1 for c in service_checks if c["ok"])

    services = {
        "portal": portal_up,
        "ttyd": ttyd_up,
        "notebook": notebook_up,
        "lance-memory": lance_up,
        "marimo": marimo_up and _container_running("arail-marimo"),
        "open-notebook": open_notebook_up and _container_running("arail-open-notebook"),
        "ollama": ollama_up,
        "knowledge-canvas": _knowledge_canvas_store is not None or (knowledge_canvas_app is not None and hasattr(knowledge_canvas_app.state, "store")),
        "neo4j": neo4j_up,
    }

    return {
        "platform": platform.system(),
        "arch": platform.machine(),
        "cpu_count": cpu_count,
        "ram_total_gb": ram_total_gb,
        "ram_used_gb": ram_used_gb,
        "ram_pct": ram_pct,
        "disk_total_gb": disk_total_gb,
        "disk_free_gb": disk_free_gb,
        "disk_pct": disk_pct,
        "python": py_version,
        "backend": active_backend,
        "model": model_name,
        "gpu": gpu_info,
        "tier": tier,
        "deep_enabled": deep_enabled,
        # Active deep backend is AirLLM today; AEROLLM_MODEL kept for the
        # eventual swap-back so the field name stays stable for the UI.
        "aerollm_model": os.getenv("AIRLLM_MODEL", os.getenv("AEROLLM_MODEL", "")),
        "services": services,
        "service_checks": service_checks,
        "health_summary": {
            "passing_required": passing_required,
            "required_total": len(required_checks),
            "passing_total": passing_total,
            "total": len(service_checks),
        },
        "mode": os.getenv("ARAIL_MODE", "airgapped"),
        "local_inference": local_inference,
    }


@app.get("/api/system/mode")
async def get_mode():
    return {"mode": os.getenv("ARAIL_MODE", "airgapped")}


@app.post("/api/system/mode")
async def set_mode(request: Request):
    """Toggle between airgapped and hybrid mode.  Writes to .env and
    updates the running process environment."""
    body = await request.json()
    new_mode = body.get("mode", "").lower()
    if new_mode not in ("airgapped", "hybrid"):
        return {"ok": False, "error": "mode must be 'airgapped' or 'hybrid'"}
    old_mode = os.getenv("ARAIL_MODE", "airgapped")
    os.environ["ARAIL_MODE"] = new_mode
    # Persist to .env
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        out, replaced = [], False
        for line in lines:
            if line.startswith("ARAIL_MODE="):
                out.append(f"ARAIL_MODE={new_mode}")
                replaced = True
            else:
                out.append(line)
        if not replaced:
            out.append(f"ARAIL_MODE={new_mode}")
        env_path.write_text("\n".join(out) + "\n")
    activity_log.emit(
        "system",
        f"Mode switched: {old_mode} → {new_mode}"
        + (" — agents can now reach the internet" if new_mode == "hybrid" else " — all network access disabled"),
        "info",
    )
    return {"ok": True, "mode": new_mode}


@app.get("/api/system/costs")
async def system_costs():
    """Return cost tracking summary — cloud-equivalent spend and energy costs."""
    from arail.costs import cost_tracker
    summary = cost_tracker.get_summary()
    # get_last_record() returns a dict (see arail.costs.CostTracker),
    # so pull fields with .get() — the history schema is stable but
    # missing keys shouldn't throw.
    last = cost_tracker.get_last_record()
    return {
        "summary": summary,
        "last_record": {
            "backend": last.get("backend"),
            "model_class": last.get("model_class"),
            "cloud_cost_usd": last.get("cloud_cost_usd"),
            "energy_cost_usd": last.get("energy_cost_usd"),
            "tokens_in": last.get("tokens_in"),
            "tokens_out": last.get("tokens_out"),
        } if last else None,
    }


@app.get("/api/addons/status")
async def addons_status():
    """Probe optional compose-based add-ons.

    Marimo and Open Notebook moved to /api/notebooks/status when the
    /notebooks picker landed — this endpoint stays as an empty-but-live
    contract for future non-notebook add-ons (ComfyUI, vector DBs, etc.).
    """
    return {"addons": []}


@app.post("/api/system/destroy")
async def system_destroy():
    """Schedule a local lab destroy from inside the running environment."""
    script_path = Path.cwd() / "arail"
    if not script_path.exists():
        return {"error": "arail dispatcher not found."}

    activity_log.emit("system", "Lab destroy requested. Scheduling teardown.", "warn")

    launcher = (
        "import subprocess, time;"
        "time.sleep(2);"
        f"subprocess.run(['bash', {str(script_path)!r}, 'reset', 'destroy', '--yes'], check=False)"
    )
    subprocess.Popen(
        [sys.executable, "-c", launcher],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        cwd=str(Path.cwd()),
        env=os.environ.copy(),
    )
    return {"status": "destroy-scheduled"}


# ── PKB (Personal Knowledge Base) API ──────────────────────────────────
# Legacy /api/pkm/* routes are aliased below for one release of backwards
# compatibility — they delegate to the new handlers and emit a deprecation
# note on the activity log.

from arail.pkb import (
    browse as pkb_browse,
    search as pkb_search,
    ingest as pkb_ingest,
    compile_index as pkb_compile,
    write_agent_research as pkb_write_research,
)


@app.get("/knowledge", response_class=HTMLResponse)
async def knowledge_page(request: Request):
    data = pkb_browse()
    current_goal = goal_store.get_current()
    return templates.TemplateResponse(request, "knowledge.html", {
        "pkb": data,
        "pkm": data,
        "mode": os.getenv("ARAIL_MODE", "airgapped"),
        "current_goal": current_goal,
    })


# ── Browser Agent API ────────────────────────────────────────────────

@app.post("/api/browse")
async def browse_url_endpoint(request: Request):
    """Browse a URL via agent-browser, capture screenshot + text."""
    from arail.agents.browser import browse_url
    body = await request.json()
    url = body.get("url", "").strip()
    if not url:
        return {"success": False, "error": "No URL provided"}
    result = browse_url(url)
    return result


@app.post("/api/browse/chat")
async def browse_chat_endpoint(request: Request):
    """Natural-language browser task via agent-browser chat."""
    from arail.agents.browser import chat as ab_chat
    body = await request.json()
    instruction = body.get("instruction", "").strip()
    if not instruction:
        return {"success": False, "error": "No instruction provided"}
    result = ab_chat(instruction)
    return result


@app.get("/api/browse/suggestions")
async def browse_suggestions():
    """Generate goal-driven browse suggestions from credible sources."""
    from arail.agents.browser import generate_suggestions
    current = goal_store.get_current()
    if not current:
        return {"suggestions": [], "message": "Set a goal first to get targeted suggestions."}
    goal_text = current.get("goal_text", "")
    domain = current.get("parsed", {}).get("domain", "general")
    suggestions = generate_suggestions(goal_text, domain)
    return {
        "suggestions": suggestions,
        "goal": goal_text,
        "mode": os.getenv("ARAIL_MODE", "airgapped"),
    }


@app.get("/api/browse/file")
async def browse_file(path: str = ""):
    """Serve a browser agent capture (screenshot or extract)."""
    from fastapi.responses import FileResponse, JSONResponse
    if not path:
        return JSONResponse({"error": "path required"}, status_code=400)
    target = Path(path)
    # Must be inside the browser data dir
    browser_dir = DATA_DIR / "browser"
    try:
        target.resolve().relative_to(browser_dir.resolve())
    except ValueError:
        return JSONResponse({"error": "invalid path"}, status_code=403)
    if not target.exists() or not target.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    import mimetypes
    mt = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    return FileResponse(str(target), media_type=mt)


@app.get("/api/pkb/browse")
async def api_pkb_browse():
    return pkb_browse()


@app.get("/api/pkb/search")
async def api_pkb_search(q: str = ""):
    if not q.strip():
        return []
    return pkb_search(q.strip())


@app.post("/api/pkb/ingest")
async def api_pkb_ingest():
    result = pkb_ingest()
    if result["moved"] or result["urls_fetched"]:
        activity_log.emit("pkb",
            f"Ingested {result['moved']} file(s), {result['urls_fetched']} URL(s)",
            "success")
    return result


@app.post("/api/pkb/compile")
async def api_pkb_compile():
    result = pkb_compile()
    activity_log.emit("pkb",
        f"Index compiled — {result['total']} items, {len(result['tags'])} tags",
        "info")
    return result


@app.get("/api/pkb/seeds")
async def api_pkb_seeds():
    """List starter packs + installed status.

    Drives the dashboard Knowledge hero + /knowledge Install button.
    """
    from arail.pkb_seed import list_packs
    return {"packs": list_packs()}


@app.post("/api/pkb/seed")
async def api_pkb_seed(request: Request):
    """Install (or re-install) a starter pack.

    Body: ``{"pack": "model-building", "force": false}``.
    Idempotent unless ``force=true``; missing files are filled in,
    user-edited files stay put (they only get overwritten on force).
    """
    from arail.pkb_seed import install_pack
    try:
        body = await request.json()
    except Exception:
        body = {}
    pack = body.get("pack", "")
    force = bool(body.get("force", False))
    result = install_pack(pack, force=force)
    if result.get("ok"):
        activity_log.emit("pkb",
            f"Seed pack '{pack}' installed — {result['written']} file(s) written, "
            f"{result['skipped']} kept",
            "info")
    return result


@app.delete("/api/pkb/seeds")
async def api_pkb_seeds_remove(pack: str = "model-building"):
    """Remove an installed starter pack.

    Wipes only ``lab/pkb/sources/seeds/<pack>/*.md`` — never user
    content. Idempotent. Used by the Knowledge tab's 🗑 button on
    the starter-pack tile so users can clear the lab's bootstrapping
    primers once they no longer need them.
    """
    from arail.pkb_seed import remove_pack
    result = remove_pack(pack)
    if result.get("ok"):
        activity_log.emit("pkb",
            f"Seed pack '{pack}' removed — {result['removed']} file(s) deleted",
            "info")
    return result


@app.post("/api/pkb/upload-url")
async def api_pkb_upload_url(request: Request):
    """Append a URL to sources/bookmarks.md.

    The existing ingest pipeline accepts URLs via ``inbox/links.txt``;
    this is the one-shot HTTP equivalent the Knowledge ingest-hero
    "URL" tile calls when a user types a link.
    """
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid JSON"}
    url = (body.get("url") or "").strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return {"ok": False, "error": "not a valid http(s) URL"}
    note = (body.get("note") or "").strip()

    from arail.pkb import _pkb_root
    from datetime import datetime, timezone
    root = _pkb_root()
    bookmarks = root / "sources" / "bookmarks.md"
    bookmarks.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    line = f"- [{stamp}] {url}"
    if note:
        line += f" — {note}"
    line += "\n"
    try:
        if bookmarks.exists():
            existing = bookmarks.read_text()
            if url in existing:
                return {"ok": True, "duplicate": True, "url": url}
            bookmarks.write_text(existing.rstrip("\n") + "\n" + line)
        else:
            bookmarks.write_text(f"# Bookmarks\n\n{line}")
    except OSError as e:
        return {"ok": False, "error": str(e)}
    activity_log.emit("pkb", f"Bookmark added: {url}", "info")
    return {"ok": True, "url": url}


@app.get("/api/pkb/recent")
async def api_pkb_recent(n: int = 8):
    """Return the N most recently modified files across the PKB.

    Drives the dashboard Knowledge hero's "Recently added" list.
    """
    from arail.pkb import _pkb_root
    root = _pkb_root()
    if not root.exists():
        return {"recent": []}

    n = max(1, min(50, n))
    candidates: list[tuple[float, Path]] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name.startswith(".") or p.name.startswith("_"):
            continue
        # Skip the wiki cache dir — it's derived, not content.
        if ".wiki-cache" in p.parts:
            continue
        try:
            candidates.append((p.stat().st_mtime, p))
        except OSError:
            continue

    candidates.sort(key=lambda t: t[0], reverse=True)
    out = []
    for mtime, p in candidates[:n]:
        try:
            rel = p.relative_to(root)
            out.append({
                "path": str(rel),
                "name": p.name,
                "section": rel.parts[0] if rel.parts else "",
                "mtime": mtime,
                "size": p.stat().st_size,
            })
        except (OSError, ValueError):
            continue
    return {"recent": out}


@app.get("/api/pkb/file")
async def api_pkb_file(path: str = ""):
    """Read a file from the PKB (relative to pkb root). Returns text content."""
    from arail.pkb import _pkb_root
    root = _pkb_root()
    # Sanitize: no traversal
    clean = Path(path).as_posix()
    if ".." in clean or clean.startswith("/"):
        return {"error": "Invalid path"}
    target = root / clean
    if not target.exists() or not target.is_file():
        return {"error": "File not found"}
    if not str(target.resolve()).startswith(str(root.resolve())):
        return {"error": "Access denied"}
    try:
        content = target.read_text(errors="replace")
        return {"path": clean, "content": content, "size": target.stat().st_size}
    except OSError:
        return {"error": "Could not read file"}


def _safe_pkb_path(rel: str) -> Path | None:
    """Resolve ``rel`` under the PKB root, rejecting traversal."""
    from arail.pkb import _pkb_root
    root = _pkb_root()
    clean = Path(rel).as_posix()
    if ".." in clean or clean.startswith("/"):
        return None
    target = root / clean
    try:
        resolved = target.resolve()
    except OSError:
        return None
    if not str(resolved).startswith(str(root.resolve())):
        return None
    return target


@app.get("/api/pkb/raw")
async def api_pkb_raw(path: str = ""):
    """Serve a PKB file as raw bytes with the correct Content-Type.

    Used by the knowledge viewer to render images (PNG/JPG/…) and PDFs
    inline. Text files fall through to the existing ``/api/pkb/file``
    JSON endpoint, so raw is strictly for binary + image surfaces.

    Path is sanitized the same way every other PKB endpoint does it
    (no traversal, must resolve inside the PKB root).
    """
    import mimetypes
    from fastapi.responses import FileResponse, JSONResponse

    if not path:
        return JSONResponse({"error": "path required"}, status_code=400)
    target = _safe_pkb_path(path)
    if target is None:
        return JSONResponse({"error": "invalid path"}, status_code=400)
    if not target.exists() or not target.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)

    media_type, _ = mimetypes.guess_type(target.name)
    if not media_type:
        media_type = "application/octet-stream"
    return FileResponse(
        target,
        media_type=media_type,
        filename=target.name,
        headers={
            # Short cache so edits appear on refresh; long enough to
            # avoid re-fetching on every scroll.
            "Cache-Control": "private, max-age=60",
        },
    )


@app.put("/api/pkb/file")
async def api_pkb_file_save(request: Request):
    """Save (or create) a text file under the PKB root.

    Body: ``{"path": "notes/foo.md", "content": "...new body..."}``
    Returns: ``{"path", "size", "bytes_written"}`` or ``{"error"}``
    """
    try:
        body = await request.json()
    except Exception:
        return {"error": "invalid JSON body"}
    path = (body.get("path") or "").strip()
    content = body.get("content")
    if not path:
        return {"error": "path required"}
    if content is None:
        return {"error": "content required"}
    target = _safe_pkb_path(path)
    if target is None:
        return {"error": "invalid path"}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        size = target.stat().st_size
    except OSError as e:
        return {"error": f"write failed: {e}"}

    activity_log.emit("pkb", f"Saved {path} ({size} bytes)", "success")

    # Trigger a debounced wiki rebuild so the edit shows up in search +
    # backlinks without the user having to click Rebuild.
    try:
        from arail import wiki
        wiki.schedule_rebuild()
    except Exception:
        pass

    return {"path": path, "size": size, "bytes_written": len(content)}


@app.delete("/api/pkb/file")
async def api_pkb_file_delete(path: str = ""):
    """Delete a file under the PKB root. No directory removal — files only."""
    if not path:
        return {"error": "path required"}
    target = _safe_pkb_path(path)
    if target is None:
        return {"error": "invalid path"}
    if not target.exists():
        return {"error": "not found"}
    if not target.is_file():
        return {"error": "not a file"}
    try:
        target.unlink()
    except OSError as e:
        return {"error": f"delete failed: {e}"}
    activity_log.emit("pkb", f"Deleted {path}", "warn")
    try:
        from arail import wiki
        wiki.schedule_rebuild()
    except Exception:
        pass
    return {"path": path, "deleted": True}


@app.post("/api/pkb/upload")
async def api_pkb_upload(request: Request):
    """Accept multipart file uploads and drop them into ``lab/pkb/inbox/``.

    Form fields:
      * ``files``: one or more file parts (multipart/form-data)
      * ``auto_ingest``: ``"true"`` (default) runs ``pkb.ingest()`` after
        the files land so they get sorted into ``sources/`` immediately.

    Returns ``{uploaded: N, paths: [...], ingest: {moved, errors}}``.
    """
    from arail.pkb import _pkb_root, ingest as run_ingest
    root = _pkb_root()
    inbox = root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    try:
        form = await request.form()
    except Exception as e:
        return {"error": f"invalid multipart body: {e}"}

    files = form.getlist("files") if hasattr(form, "getlist") else []
    if not files:
        # starlette's FormData keeps all entries — collect anything
        # that smells like a file.
        files = [v for v in form.values() if hasattr(v, "filename")]
    if not files:
        return {"error": "no files in request"}

    auto_ingest = str(form.get("auto_ingest", "true")).lower() != "false"

    saved: list[str] = []
    for upload in files:
        name = getattr(upload, "filename", None)
        if not name:
            continue
        # Strip any directory components from the client side — we never
        # let the browser pick the destination directory.
        safe_name = Path(name).name
        if not safe_name or safe_name.startswith("."):
            continue
        # De-dupe by appending a numeric suffix if the file already exists.
        dest = inbox / safe_name
        i = 1
        stem, suffix = Path(safe_name).stem, Path(safe_name).suffix
        while dest.exists():
            dest = inbox / f"{stem}-{i}{suffix}"
            i += 1
        try:
            data = await upload.read()
            dest.write_bytes(data)
            saved.append(dest.relative_to(root).as_posix())
        except (OSError, ValueError) as e:
            activity_log.emit("pkb", f"Upload failed ({safe_name}): {e}", "error")

    if not saved:
        return {"error": "no valid files saved"}

    activity_log.emit("pkb",
                      f"Uploaded {len(saved)} file(s) to inbox/",
                      "success")

    result: dict[str, Any] = {"uploaded": len(saved), "paths": saved}
    if auto_ingest:
        try:
            ingest_result = run_ingest()
            result["ingest"] = ingest_result
            if ingest_result.get("moved"):
                activity_log.emit("pkb",
                                  f"Auto-ingested {ingest_result['moved']} "
                                  f"file(s) from inbox → sources",
                                  "success")
        except Exception as e:
            result["ingest_error"] = str(e)
    try:
        from arail import wiki
        wiki.schedule_rebuild()
    except Exception:
        pass
    return result


# ── Legacy /api/pkm/* aliases (deprecated, kept for one release) ──────

@app.get("/api/pkm/browse")
async def api_pkm_browse_legacy():
    return await api_pkb_browse()


@app.get("/api/pkm/search")
async def api_pkm_search_legacy(q: str = ""):
    return await api_pkb_search(q=q)


@app.post("/api/pkm/ingest")
async def api_pkm_ingest_legacy():
    return await api_pkb_ingest()


@app.post("/api/pkm/compile")
async def api_pkm_compile_legacy():
    return await api_pkb_compile()


@app.get("/api/pkm/file")
async def api_pkm_file_legacy(path: str = ""):
    return await api_pkb_file(path=path)


# ═══════════════════════════════════════════════════════════════════════
# /tuning — single-page view for the research models.
#
# The page shows Baseline vs Champion, a full bench history with git
# context, and controls that fire the autoresearch loop for either
# backend (AeroLLM CUDA or AeroLLM MLX). Every endpoint accepts a
# ?backend=aerollm|mlx query param; default is "aerollm".
#
#   GET  /api/tuning/config                  — hydrated tuning config
#   GET  /api/tuning/runs                    — bench history + git SHA
#   POST /api/tuning/baseline                — measure current HEAD
#   POST /api/tuning/autoresearch/start      — kick off the loop
#   GET  /api/tuning/autoresearch/status     — poll loop state
#   POST /api/tuning/autoresearch/start_forever
#   POST /api/tuning/autoresearch/stop
#
# Safety note: the POST /autoresearch/* endpoints refuse unless
# ARAIL_AUTORESEARCH_ENABLED is set in the environment. This keeps
# an accidental click from making commits.
# ═══════════════════════════════════════════════════════════════════════

_VALID_BACKENDS = {"aerollm", "mlx"}


def _normalize_backend(backend: str | None) -> str:
    b = (backend or "aerollm").lower()
    if b not in _VALID_BACKENDS:
        b = "aerollm"
    return b


@app.get("/tuning", response_class=HTMLResponse)
async def tuning_page(request: Request):
    aerollm_model = os.getenv("AEROLLM_MODEL", "")
    airllm_model = os.getenv("AIRLLM_MODEL", "meta-llama/Llama-3.1-70B")
    # Blueprint default: AirLLM is the only visible deep backend. Flip
    # LAB_SHOW_AEROLLM=1 in .env to bring the AeroLLM MLX + CUDA tabs
    # back (one env-var toggle for the operator who's ready to run
    # AeroLLM alongside or in place of AirLLM).
    show_aerollm = os.getenv("LAB_SHOW_AEROLLM", "false").lower() in ("1", "true", "yes")
    return templates.TemplateResponse(request, "tuning.html", {
        "aerollm_model": aerollm_model,
        "airllm_model": airllm_model,
        "show_aerollm": show_aerollm,
    })


@app.get("/api/tuning/config")
async def api_tuning_config(backend: str = "aerollm"):
    """Return the hydrated tuning config for the selected backend.
    Safe to poll."""
    from arail.experiments.autoresearch import _config_path
    from arail.experiments.tuning import load_tuning
    b = _normalize_backend(backend)
    try:
        cfg = load_tuning(_config_path(b))
    except FileNotFoundError:
        return {"error": f"tuning config missing for backend={b}"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "backend": b,
        "research_model": {
            "name": cfg.research_model.name,
            "precision": cfg.research_model.precision,
            "expected_disk_gb": cfg.research_model.expected_disk_gb,
            "family": cfg.research_model.family,
            "active_params_b": cfg.research_model.active_params_b,
            "total_params_b": cfg.research_model.total_params_b,
            "huggingface_id": cfg.research_model.huggingface_id,
        },
        "small_models": cfg.small_models,
        "baseline_commit": cfg.baseline_commit,
        "baseline_metrics": cfg.baseline_metrics,
        "baseline_prompt": cfg.baseline_prompt,
        "baseline_max_tokens": cfg.baseline_max_tokens,
        "knobs": {
            n: {
                "current": k.current,
                "type": k.schema_type,
                "choices": k.choices,
                "min": k.min_value,
                "max": k.max_value,
                "rationale": k.rationale,
            }
            for n, k in cfg.knobs.items()
        },
        # Frontier strip — 670B-750B class "doesn't fit any single
        # GPU" targets. Only populated for the MLX backend; the
        # CUDA AeroLLM config leaves this empty.
        "frontier_models": [
            {
                "name": fm.name,
                "huggingface_id": fm.huggingface_id,
                "family": fm.family,
                "active_params_b": fm.active_params_b,
                "total_params_b": fm.total_params_b,
                "precision": fm.precision,
                "expected_disk_gb": fm.expected_disk_gb,
                "streaming_required": fm.streaming_required,
                "gpu_fit": dict(fm.gpu_fit),
                "rationale": fm.rationale,
            }
            for fm in cfg.frontier_models
        ],
        "frontier_baselines": dict(cfg.frontier_baselines),
    }


@app.get("/api/tuning/runs")
async def api_tuning_runs(backend: str = "aerollm", limit: int = 200):
    """Return recent bench rows with git context for the selected
    backend. Enriches each row with a `diff_url` pointing at GitHub
    if a remote is configured."""
    from arail.experiments.bench import load_runs
    from arail.experiments.git_ops import diff_url
    b = _normalize_backend(backend)
    if b == "mlx":
        from arail.experiments.mlx_backend import mlx_bench_file
        rows = load_runs(limit=max(1, min(limit, 2000)), path=mlx_bench_file())
    else:
        rows = load_runs(limit=max(1, min(limit, 2000)))
    for r in rows:
        sha = r.get("git_sha")
        if sha:
            r["diff_url"] = diff_url(sha)
    return {"backend": b, "runs": rows, "count": len(rows)}


@app.post("/api/tuning/baseline")
async def api_tuning_baseline(backend: str = "aerollm"):
    """Run the benchmark `bench_runs_per_config` times on the current
    HEAD and persist the median into the backend's tuning config as
    the new baseline. Runs synchronously in a worker thread — expect
    a long response for big models. The page shows a spinner during this.

    We allow this without the autoresearch env flag because it
    doesn't create branches or new commits, just a baseline snapshot."""
    from arail.experiments.autoresearch import run_autoresearch
    b = _normalize_backend(backend)

    def _baseline_only():
        return run_autoresearch(
            backend=b, require_env_flag=False, candidates=[]
        )
    result = await asyncio.to_thread(_baseline_only)
    return result.to_dict()


@app.post("/api/tuning/autoresearch/start")
async def api_tuning_autoresearch_start(backend: str = "aerollm"):
    """Kick off the full autoresearch loop in a background task for
    the selected backend. Returns immediately; poll /status?backend=
    for progress."""
    from arail.experiments.autoresearch import (
        current_state, run_autoresearch,
    )
    b = _normalize_backend(backend)
    state = current_state(b)
    if state.phase in ("baseline", "variant"):
        return {"ok": False, "error": "loop already running",
                "state": state.to_dict()}

    # Preflight the safety rail at the endpoint so the UI gets a
    # clear "no" instead of a silent background error.
    if not os.getenv("ARAIL_AUTORESEARCH_ENABLED"):
        return {
            "ok": False,
            "error": (
                "ARAIL_AUTORESEARCH_ENABLED is not set. Export it "
                "(e.g. in .env) to arm the loop — this flag exists "
                "so an accidental click can't make commits."
            ),
        }

    async def _bg():
        await asyncio.to_thread(run_autoresearch, backend=b)
    asyncio.create_task(_bg())
    return {"ok": True, "state": current_state(b).to_dict()}


@app.get("/api/tuning/autoresearch/status")
async def api_tuning_autoresearch_status(backend: str = "aerollm"):
    from arail.experiments.autoresearch import current_state
    b = _normalize_backend(backend)
    return current_state(b).to_dict()


@app.post("/api/tuning/autoresearch/start_forever")
async def api_tuning_autoresearch_start_forever(backend: str = "aerollm"):
    """Kick off the continuous supervisor for the selected backend —
    sweeps every candidate, pauses, sweeps again, forever, until /stop
    is called. Returns immediately; poll /status for progress +
    pass_number."""
    from arail.experiments.autoresearch import (
        current_state, run_autoresearch_forever,
    )
    b = _normalize_backend(backend)
    state = current_state(b)
    if state.phase in ("baseline", "variant") or state.continuous:
        return {"ok": False, "error": "loop already running",
                "state": state.to_dict()}
    if not os.getenv("ARAIL_AUTORESEARCH_ENABLED"):
        return {
            "ok": False,
            "error": (
                "ARAIL_AUTORESEARCH_ENABLED is not set. Export it "
                "(e.g. in .env) to arm the loop — this flag exists "
                "so an accidental click can't make commits."
            ),
        }

    async def _bg():
        await asyncio.to_thread(run_autoresearch_forever, backend=b)
    asyncio.create_task(_bg())
    return {"ok": True, "state": current_state(b).to_dict()}


@app.post("/api/tuning/autoresearch/stop")
async def api_tuning_autoresearch_stop(backend: str = "aerollm"):
    """Signal the continuous supervisor for the selected backend to
    stop after the current pass. Safe to call whether or not a loop
    is running."""
    from arail.experiments.autoresearch import current_state, request_stop
    b = _normalize_backend(backend)
    request_stop(b)
    return {"ok": True, "state": current_state(b).to_dict()}


@app.get("/api/tuning/autoresearch/schedule")
async def api_tuning_autoresearch_schedule_get():
    """Return the persisted schedule + live status (allowed_now, next
    open time). Safe to poll; cheap (one JSON read from disk)."""
    from arail.experiments.autoresearch import load_schedule, schedule_status
    sched = load_schedule()
    return {"schedule": sched, "status": schedule_status(sched)}


@app.post("/api/tuning/autoresearch/schedule")
async def api_tuning_autoresearch_schedule_set(request: Request):
    """Update the schedule. Body shape:
        {"mode": "anytime"|"window"|"paused",
         "window_start": "HH:MM", "window_end": "HH:MM"}
    Invalid values are coerced to defaults rather than rejected so the
    UI never has to choreograph error handling."""
    from arail.experiments.autoresearch import save_schedule, schedule_status
    try:
        body = await request.json()
    except Exception:
        body = {}
    sched = save_schedule(body or {})
    return {"schedule": sched, "status": schedule_status(sched)}


# ═══════════════════════════════════════════════════════════════════════
# /api/perf/summary — projected → measured swap for the /tuning page.
#
# Reads the latest JSONL written by aerollm's scripts/perf/run.py and
# reduces it to a per-(model, workload) airllm-vs-aerollm shape that
# the tuning.html "AirLLM vs AeroLLM" cards consume.
#
# Result location: $AEROLLM_PERF_RESULTS_DIR if set, otherwise the
# sibling aerollm checkout (../aerollm/scripts/perf/results/). Missing
# dir or no measurements → rows=[] with a `reason` so the page keeps
# showing the projected numbers.
#
# Schema contract: scripts/perf/schema.md in the aerollm repo.
# ═══════════════════════════════════════════════════════════════════════

import platform as _platform


def _perf_results_dir() -> Path:
    env = os.getenv("AEROLLM_PERF_RESULTS_DIR")
    if env:
        return Path(env).expanduser()
    # arail/src/arail/portal/app.py → arail/ is parents[3]; aerollm
    # lives as a sibling checkout.
    arail_root = Path(__file__).resolve().parents[3]
    return arail_root / "aerollm" / "scripts" / "perf" / "results"


def _detect_perf_hw_id() -> str:
    if _platform.system() == "Darwin" and "arm" in _platform.machine().lower():
        return "m3_max"
    return "rtx_4090_gen4"


def _latest_perf_jsonl(results_dir: Path, hw_id: str) -> Path | None:
    if not results_dir.is_dir():
        return None
    # Filenames look like: 2026-04-25T170311Z-m3_max.jsonl
    matches = sorted(results_dir.glob(f"*/*-{hw_id}.jsonl"))
    return matches[-1] if matches else None


def _reduce_perf_rows(jsonl_path: Path, model_id: str | None) -> dict:
    """Reduce a JSONL run record to {rows: [{workload_id, airllm, aerollm, ratio}]}.

    Stub rows (errors contains 'stub') are treated as missing — the
    page keeps the projected number for that cell rather than rendering
    a fake zero.
    """
    by_cell: dict[tuple[str, str, str], dict] = {}
    git_sha = None
    as_of = None
    seen_models: list[str] = []
    with jsonl_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            git_sha = git_sha or row.get("git_sha")
            as_of = as_of or row.get("timestamp_utc")
            mid = (row.get("model") or {}).get("id")
            if mid and mid not in seen_models:
                seen_models.append(mid)
            eid = (row.get("engine") or {}).get("id")
            wid = (row.get("workload") or {}).get("id")
            if not (mid and eid and wid):
                continue
            by_cell[(mid, wid, eid)] = row

    chosen_model = model_id or (seen_models[0] if seen_models else None)
    if not chosen_model:
        return {
            "rows": [],
            "model_id": None,
            "as_of": as_of,
            "git_sha": git_sha,
            "reason": "no_model_in_file",
        }

    workload_ids = ["single_stream", "batch_64", "batch_128", "spec_decode"]
    # primary_metric mapping mirrors matrix.yaml; aggregate for batch,
    # p50 for single-stream/spec.
    primary = {
        "single_stream": "tok_per_sec_p50",
        "batch_64": "tok_per_sec_aggregate",
        "batch_128": "tok_per_sec_aggregate",
        "spec_decode": "tok_per_sec_p50",
    }

    def _metric(cell: dict | None, wid: str) -> float | None:
        if not cell:
            return None
        if any("stub" in (e or "") for e in (cell.get("errors") or [])):
            return None
        m = cell.get("metrics") or {}
        v = m.get(primary[wid])
        return float(v) if isinstance(v, (int, float)) else None

    rows = []
    for wid in workload_ids:
        air = _metric(by_cell.get((chosen_model, wid, "airllm")), wid)
        aero = _metric(by_cell.get((chosen_model, wid, "aerollm")), wid)
        if air is None and aero is None:
            continue
        ratio = (aero / air) if (air and aero and air > 0) else None
        rows.append({
            "workload_id": wid,
            "airllm": air,
            "aerollm": aero,
            "ratio": ratio,
        })

    return {
        "rows": rows,
        "model_id": chosen_model,
        "as_of": as_of,
        "git_sha": git_sha,
        "reason": "ok" if rows else "stub_only",
    }


@app.get("/api/perf/summary")
async def api_perf_summary(hardware: str | None = None, model: str | None = None):
    """Return the latest measured AirLLM vs AeroLLM numbers for the
    /tuning page. Empty rows = no measurements yet → page keeps the
    projected text. Safe to poll."""
    hw_id = hardware or _detect_perf_hw_id()
    results_dir = _perf_results_dir()
    base = {
        "schema_version": 1,
        "hardware_id": hw_id,
        "model_id": model,
        "rows": [],
        "as_of": None,
        "git_sha": None,
    }
    latest = _latest_perf_jsonl(results_dir, hw_id)
    if latest is None:
        base["reason"] = (
            "no_results_dir" if not results_dir.is_dir() else "no_files"
        )
        base["results_dir"] = str(results_dir)
        return base
    summary = _reduce_perf_rows(latest, model)
    base.update(summary)
    base["source_file"] = str(latest)
    return base


# ═══════════════════════════════════════════════════════════════════════
# /teacher — AeroLLM-backed deep consultation surface.
#
# Every Q&A routes through AeroLLM (multi-minute answers from a frontier
# model) and auto-saves to lab/pkb/teacher/<ts>.md so wisdom compounds
# across sessions. The page is deliberately slow and calm — see
# templates/teacher.html for the UX.
#
#   GET  /teacher                 — page
#   POST /api/teacher/ask         — one question; returns answer + saved_to
#   GET  /api/teacher/history     — recent consultations from PKB
# ═══════════════════════════════════════════════════════════════════════

@app.get("/teacher")
async def teacher_page(request: Request):
    # /teacher now aliases the unified Chat surface.
    return RedirectResponse(url="/chat", status_code=307)


def _save_teacher_result(message: str, result: dict[str, Any]) -> dict[str, Any]:
    if result.get("error") or not result.get("reply"):
        return result

    saved = dict(result)
    try:
        from arail.pkb import write_teacher_qa

        path = write_teacher_qa(
            message, saved["reply"], saved.get("model") or "aerollm",
        )
        try:
            saved["saved_to"] = str(path.relative_to(Path.cwd().resolve()))
        except ValueError:
            saved["saved_to"] = str(path)
    except Exception as exc:  # noqa: BLE001
        activity_log.emit(
            "teacher",
            f"PKB save failed: {type(exc).__name__}: {exc}",
            "warn",
        )
        saved["saved_to"] = None
    return saved


@app.post("/api/teacher/ask")
async def api_teacher_ask(request: Request):
    """One consultation with the Deep Teacher. Forces backend=aerollm so
    the user never accidentally hits the fast path from this surface.
    Saves the Q&A to PKB on success."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = (body.get("message") or "").strip()
    if not message:
        return {"error": "message required", "reply": ""}

    result = await _run_chat_completion(
        message=message,
        history=body.get("history") or [],
        backend_override=body.get("backend") or _default_teacher_backend(),
        model_override=body.get("model"),
        temperature=0.7,
        top_p=None,
        max_tokens=int(body.get("max_tokens") or 1024),
    )
    return _save_teacher_result(message, result)


@app.post("/api/teacher/stream")
async def api_teacher_stream(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = (body.get("message") or "").strip()
    if not message:
        async def _empty() -> AsyncIterator[str]:
            yield json.dumps(
                {"type": "final", "error": "message required", "reply": ""}
            ) + "\n"
        return StreamingResponse(_empty(), media_type="application/x-ndjson")

    async def _generate() -> AsyncIterator[str]:
        async for event in _run_chat_completion_stream(
            message=message,
            history=body.get("history") or [],
            backend_override=body.get("backend") or _default_teacher_backend(),
            model_override=body.get("model"),
            temperature=0.7,
            top_p=None,
            max_tokens=int(body.get("max_tokens") or 1024),
        ):
            if event.get("type") == "final":
                event = _save_teacher_result(message, event)
            yield json.dumps(event, default=str) + "\n"

    return StreamingResponse(
        _generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/teacher/history")
async def api_teacher_history(limit: int = 25):
    """Return recent Teacher consultations from lab/pkb/teacher/, newest
    first. Files are small (one Q&A each) and there will rarely be more
    than a few dozen, so we just read them all and sort."""
    from arail.pkb import _pkb_root
    teacher_dir = _pkb_root() / "teacher"
    items: list[dict] = []
    if teacher_dir.is_dir():
        paths = sorted(teacher_dir.glob("*.md"), reverse=True)[
            : max(1, min(limit, 200))
        ]
        for p in paths:
            try:
                text = p.read_text()
            except Exception:
                continue
            # Parse the frontmatter + "## Question" / "## Answer" sections
            # that write_teacher_qa produces. Keep it lenient in case a
            # user hand-edited the file.
            model = ""
            ts = ""
            q_body = ""
            a_body = ""
            if text.startswith("---\n"):
                end = text.find("\n---\n", 4)
                if end > 0:
                    fm = text[4:end]
                    for line in fm.splitlines():
                        if line.startswith("title:"):
                            ts = line.split(":", 1)[1].strip()
                    text_body = text[end + 5 :]
                else:
                    text_body = text
            else:
                text_body = text
            for line in text_body.splitlines()[:4]:
                if line.lower().startswith("**model:**"):
                    model = line.split("**", 2)[-1].strip(" *:")
                if line.lower().startswith("**asked:**"):
                    ts = line.split("**", 2)[-1].strip(" *:")
            q_idx = text_body.find("## Question")
            a_idx = text_body.find("## Answer")
            if q_idx >= 0 and a_idx > q_idx:
                q_body = text_body[q_idx + len("## Question") : a_idx].strip()
                a_body = text_body[a_idx + len("## Answer") :].strip()
            items.append({
                "ts": ts or p.stem,
                "model": model or "—",
                "question": q_body,
                "answer": a_body,
                "path": str(p),
            })
    return {"items": items, "count": len(items)}
