"""OGLab Portal — local web dashboard served at oglab.local."""

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
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from oglab.activity import activity_log
from oglab.agents.consent import ConsentStore
from oglab.goals import GoalStore
from oglab.agents.researcher import researcher
from oglab.agents.pip import pip
from oglab.plugins.manager import PluginManager
from oglab.scheduler import (halt_all_jobs, jobs_halted, resume_all_jobs,
                              startup_delay_seconds)
from oglab.scheduler import state as scheduler_state
from oglab.skills.goal_parser import GoalParser
from oglab.skills.experiment_tracker import ExperimentTracker
from oglab.router.backends import BACKEND_MAP
from oglab.portal.wiki_routes import router as wiki_router

from oglab.brand import load_brand
from oglab.router.backends import ModelResponse

_BRAND = load_brand()

app = FastAPI(title=_BRAND.name, docs_url="/api/docs")
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
# OGLab's own API surface.
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
# Expose the brand to every Jinja template — so `{{ brand.name }}` works
# everywhere without each route having to pass it explicitly.
templates.env.globals["brand"] = _BRAND

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
        from oglab.config import DATA_DIR
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
            "Welcome to OGLab. Type a goal above to begin — the researcher agent will take it from there.",
            "info")
        activity_log.emit("system",
            "Tip: Goals can be anything — 'grow peanuts in zone 7', 'build a trading bot', 'learn Rust'.",
            "info")

    # Starter-pack seeding — idempotent. On a fresh lab this populates
    # lab/pkb/sources/seeds/model-building/ with 9 curated primers so
    # the researcher + curator have something to read on their first
    # tick. On every subsequent start it's a no-op.
    try:
        from oglab.pkb_seed import seed_all_on_startup
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
        from oglab.skill_seed import ensure_starter_skills
        skill_summary = ensure_starter_skills()
        if skill_summary.get("installed"):
            activity_log.emit("pkb",
                f"Seeded starter skills: {', '.join(skill_summary['installed'])}",
                "info")
    except Exception as e:  # noqa: BLE001
        activity_log.emit("pkb",
            f"Skill seeding failed: {type(e).__name__}: {e}", "error")

    # Research program seed — the lab ships with "optimize AeroLLM"
    # pre-loaded so a fresh install has a meaningful research goal
    # the moment the portal comes up. User edits program.md to steer
    # the researcher elsewhere.
    try:
        from oglab.agents.builtin_seed import ensure_research_files
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
        from oglab.agents.loader import load_all, start_all_auto
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
            from oglab.agents.dream_daemon import dream_daemon
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


@app.get("/terminal", response_class=HTMLResponse)
async def terminal_page(request: Request):
    """Serve the terminal iframe if ttyd is running, otherwise show
    install help so the user can get unblocked without leaving the UI."""
    import shutil, platform
    ttyd_installed = shutil.which("ttyd") is not None
    ttyd_running = False
    if ttyd_installed:
        ttyd_running = await _port_open(
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
    return templates.TemplateResponse(request, "terminal.html", {
        "ttyd_installed": ttyd_installed,
        "ttyd_running": ttyd_running,
        "install_cmd": install_cmd,
    })


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
    (substring match, so ``oglab-marimo`` matches ``oglab-marimo``
    but not ``oglab-marimo-db``).
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
    return _container_running("oglab-open-notebook")


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
        return {"ok": False, "error": "OPEN_NOTEBOOK_ENCRYPTION_KEY not set — run ./oglab setup"}
    result = subprocess.run(
        ["docker", "compose", "--env-file", _repo_env_file(),
         "-f", _COMPOSE_FILE, "up", "-d"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr[-500:] if result.stderr else "unknown"}
    # Seed with lab content in the background (non-blocking)
    import threading
    from oglab.open_notebook_seed import seed as seed_onb
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
      - Marimo: Docker available + oglab-marimo container running.
      - Open Notebook: Docker available + oglab-open-notebook container running.
    """
    import shutil
    bind = os.getenv("BIND_ADDR", "127.0.0.1")
    password = os.getenv("OGLAB_PASSWORD", "oglab")
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
                "alive": mar_alive and _container_running("oglab-marimo"),
                "url_internal": "/marimo",
                "url_external": f"http://{bind}:{marimo_port}?access_token={password}",
            },
            {
                "id": "open-notebook",
                "name": "Open Notebook",
                "installed": docker_ok,
                "alive": on_alive and _container_running("oglab-open-notebook"),
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
    URL (same ``?access_token=<OGLAB_PASSWORD>`` contract Marimo itself
    prints on startup). When not running, shows a one-click Start button
    that calls /api/marimo/start.
    """
    docker_ok = _docker_available()
    running = _container_running("oglab-marimo") if docker_ok else False
    password = os.getenv("OGLAB_PASSWORD", "oglab")
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
    return record


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


# ── Jobs / Scheduler API ─────────────────────────────────────────────────
# Halt = soft emergency stop: cancels running work but keeps the portal
# and services up, unlike `./oglab stop` which tears down everything.

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
    return templates.TemplateResponse(request, "admin.html", {
        "health": health,
    })


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
    from oglab.agents.browser import EXTRACT_DIR

    # Researcher
    goal = goal_store.get_current()
    r_status = {
        "status": researcher.status,
        "progress": goal.get("progress", 0) if goal else 0,
        "experiments": len(goal.get("experiments", [])) if goal else 0,
        "current_task": None,
    }
    # Grab the last researcher event as current_task
    for ev in reversed(activity_log.recent(50)):
        if ev.get("source") == "researcher" and ev.get("level") in ("info", "success"):
            r_status["current_task"] = ev["message"][:80]
            break
    # Count tokens from prompt traces
    tok = 0
    for ev in activity_log.recent(200):
        if ev.get("source") == "researcher" and ev.get("data", {}).get("prompt_trace"):
            tok += ev["data"]["prompt_trace"].get("max_tokens", 0)
    r_status["tokens"] = tok

    # Curator
    c_status = {
        "pending": len(consent_store.list_pending()),
        "allowed": len(consent_store.list_allowed()),
    }

    # Browser
    captures = len(list(EXTRACT_DIR.glob("*.md"))) if EXTRACT_DIR.exists() else 0
    last_task = None
    for ev in reversed(activity_log.recent(50)):
        if ev.get("source") == "browser":
            last_task = ev["message"][:60]
            break
    b_status = {
        "captures": captures,
        "last_task": last_task,
    }

    return {"researcher": r_status, "curator": c_status, "browser": b_status}


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


# ── Agent Forge + skills picker endpoints ────────────────────────
# /api/skills/list feeds the Forge UI's skill multi-select.
# /api/agents/list returns everything the loader currently knows —
#   used by the Forge to prevent id collisions before Deploy.
# /api/agents/forge is the Deploy button's backend.

@app.get("/api/skills/list")
async def api_skills_list():
    """Return every installed skill so the Forge can show toggles."""
    from oglab.skills_loader import list_installed_skills
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


@app.get("/api/agents/list")
async def api_agents_list():
    """Return the agents the loader currently knows about."""
    from oglab.agents.loader import discover
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
    from oglab.agents.forge import deploy
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
    from oglab.agents.forge import (
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
    mode = os.getenv("OGLAB_MODE", "airgapped")
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
        "openrouter": "OpenRouter", "claude": "Claude", "aerollm": "AeroLLM",
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
    from oglab.router import ModelRouter

    global _ROUTER_CACHE, _ROUTER_CACHE_SIGNATURE
    signature = _router_signature()
    with _ROUTER_CACHE_LOCK:
        if _ROUTER_CACHE is None or _ROUTER_CACHE_SIGNATURE != signature:
            _ROUTER_CACHE = ModelRouter()
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

    from oglab import lab_brain

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
        from oglab.costs import cost_tracker
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


def _prepare_chat_context(
    *,
    message: str,
    history: list,
    backend_override: str | None,
    model_override: str | None,
) -> dict[str, Any]:
    from oglab import lab_brain

    if not isinstance(history, list):
        history = []
    history = history[-_CHAT_HISTORY_LIMIT:]
    messages = lab_brain.build_chat_messages(message, history)

    wants_deep = str(backend_override or "").strip().lower() == "aerollm"
    deep_backend = None
    if wants_deep:
        try:
            deep_backend = _get_deep_backend()
        except Exception as e:  # noqa: BLE001
            deep_model = os.getenv("AEROLLM_MODEL", "meta-llama/Llama-3.1-70B")
            gated_hint = ""
            if deep_model.lower().startswith("meta-llama/"):
                gated_hint = (
                    " Accept the model license on Hugging Face first, then run "
                    "huggingface-cli login or export HF_TOKEN before downloading it."
                )
            activity_log.emit(
                "chat",
                f"AeroLLM init failed: {type(e).__name__}: {e}",
                "warn",
            )
            return {
                "error_result": {
                    "reply": (
                        "AeroLLM isn't ready on this lab. Install it "
                        "(`pip install git+https://github.com/cdarnell/aerollm@main`) "
                        f"and ensure AEROLLM_MODEL in .env points at a downloaded "
                        f"model.{gated_hint}\n\nError: {e}"
                    ),
                    "backend": "aerollm",
                    "error": str(e),
                }
            }

    router = None
    if deep_backend is None:
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
                        "`./oglab setup` to install the backend for your "
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
        "active_backend": active_backend,
        "previous_model": previous_model,
        "prompt": prompt,
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
) -> AsyncIterator[dict[str, Any]]:
    context = _prepare_chat_context(
        message=message,
        history=history,
        backend_override=backend_override,
        model_override=model_override,
    )
    error_result = context.get("error_result")
    if error_result is not None:
        yield {"type": "final", **error_result}
        return

    wants_deep = bool(context["wants_deep"])
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
            from oglab.costs import cost_tracker
            cost_tracker.track(
                backend=response.backend,
                model=response.model,
                tokens_in=max(len(prompt) // 4, 1),
                tokens_out=response.tokens_used,
                latency_ms=response.latency_ms,
            )
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
                getattr(deep_backend, "backend_name", "aerollm")
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
    )
    error_result = context.get("error_result")
    if error_result is not None:
        return error_result

    wants_deep = bool(context["wants_deep"])
    deep_backend = context.get("deep_backend")
    router = context.get("router")
    prompt = str(context["prompt"])

    try:
        if deep_backend is not None:
            import asyncio as _aio
            response = await _aio.to_thread(
                deep_backend.complete,
                prompt, max_tokens, temperature, top_p,
            )
            from oglab.costs import cost_tracker
            cost_tracker.track(
                backend=response.backend,
                model=response.model,
                tokens_in=max(len(prompt) // 4, 1),
                tokens_out=response.tokens_used,
                latency_ms=response.latency_ms,
            )
            _record_aerollm_bench(
                model=response.model,
                tokens_out=response.tokens_used,
                latency_ms=response.latency_ms,
                prompt_chars=len(prompt),
                max_tokens=max_tokens,
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
                getattr(deep_backend, "backend_name", "aerollm")
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
        ):
            yield json.dumps(event, default=str) + "\n"

    return StreamingResponse(
        _generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Deep-backend cache — AeroLLM init loads the whole model layer-by-
# layer from disk (expensive). Cache the instance so subsequent
# "deep" chat calls reuse it. Lazy: never instantiated unless the
# user actually opts in via the UI.
_DEEP_BACKEND_CACHE = None


def _get_deep_backend():
    global _DEEP_BACKEND_CACHE
    if _DEEP_BACKEND_CACHE is None:
        from oglab.router.backends import AeroLLMBackend
        _DEEP_BACKEND_CACHE = AeroLLMBackend()
        # Give the AeroLLM instance the same interface as other
        # backends so cost tracking + error handling above treat it
        # uniformly.
        _DEEP_BACKEND_CACHE.backend_name = "aerollm"
    return _DEEP_BACKEND_CACHE


# ── AeroLLM bench capture ───────────────────────────────────────
# Every deep-call through AeroLLM appends one JSON line to
# lab/data/aerollm-bench.jsonl. The /api/aerollm/bench endpoint
# aggregates by model so the dashboard can show "on your machine,
# X tokens/min averaged over N calls." This is the proof-ground
# for any AeroLLM optimizations — before/after numbers land here.

def _aerollm_bench_file() -> Path:
    from oglab.config import DATA_DIR
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
    if backend_name in ("mlx", "cpu", "aerollm", "cuda"):
        models_dir = Path(os.getenv("OGLAB_MODELS_DIR", "lab/models"))
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
                "folder name, then ./oglab restart. Live in-session swap "
                "isn't supported on local backends — the model has to be "
                "loaded into memory, which takes seconds to minutes."
            ),
        }

    # Deep-model info — independent of the active backend. Tells
    # the UI what giant model is wired up behind the "Deep model"
    # toggle. Separate field because users can flip that toggle
    # regardless of which primary backend they're on.
    deep_model_name = os.getenv("AEROLLM_MODEL", "meta-llama/Llama-3.1-70B")
    # Look up the spec sheet so the Frontier chip hover can show
    # strengths, benchmarks, and license at a glance. Registry lives
    # in src/oglab/model_specs.py — users edit it to add new models.
    from oglab.model_specs import lookup as _spec_lookup
    spec = _spec_lookup(deep_model_name)

    deep_info = {
        "model": deep_model_name,
        # Whether the aerollm package is importable. When False, the
        # UI can swap the toggle for an install hint.
        "installed": _is_aerollm_installed(),
        # Rough size hint the UI can render in the chip. We extract
        # a parameter count from the model name when present
        # (e.g. "Qwen3-235B-A22B" → "235B"); the user-entered
        # AEROLLM_MODEL decides what shows.
        "param_hint": _extract_param_hint(deep_model_name),
        # Spec sheet — populated from the registry. Null when the
        # configured model isn't known; the UI shows a "click to
        # document this model" placeholder in that case.
        "spec": spec,
        # Server-side default for the dashboard deep toggle. The UI
        # still lets the browser override this after first render.
        "default_enabled": os.getenv("OGLAB_CHAT_DEEP_DEFAULT", "false").lower() == "true",
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

    return {
        "backend": backend_name,
        "current": current,
        "models": models,
        "switchable": backend_name in ("openai_compat", "openrouter"),
        "local_models": local_models,
        "install_hint": install_hint,
        "deep": deep_info,
    }


def _is_aerollm_installed() -> bool:
    """aerollm is optional — check without importing since the import
    itself is heavy (drags torch)."""
    import importlib.util
    return importlib.util.find_spec("aerollm") is not None


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
    from oglab import lab_brain
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
    marimo_port = int(os.getenv("MARIMO_PORT", "2718"))
    open_notebook_port = int(os.getenv("OPEN_NOTEBOOK_PORT", "8502"))
    neo4j_bolt_port = int(os.getenv("NEO4J_BOLT_PORT", "7687"))

    portal_up, ttyd_up, notebook_up, ollama_up, marimo_up, open_notebook_up, neo4j_up = await asyncio.gather(
        _port_open(bind, int(os.getenv("PORTAL_PORT", "8080"))),
        _port_open(bind, ttyd_port),
        _port_open(bind, notebook_port),
        _port_open(bind, ollama_port),
        _port_open(bind, marimo_port),
        _port_open(bind, open_notebook_port),
        _port_open(bind, neo4j_bolt_port),
    )

    docker_ok = _docker_available()
    activity_file = Path.cwd() / "lab" / "data" / "activity.jsonl"
    current_goal = goal_store.get_current()
    current_model_path = os.getenv("OGLAB_MODELS_DIR", str(Path.cwd() / "models"))
    from oglab.config import DATA_DIR, PKB_ROOT

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
        add_check("marimo", "Marimo", marimo_up and _container_running("oglab-marimo"), f"port {marimo_port}", required=False, category="service"),
        add_check("open_notebook", "Open Notebook", open_notebook_up and _container_running("oglab-open-notebook"), f"port {open_notebook_port}", required=False, category="service"),
        add_check("ollama_binary", "Ollama Installed", shutil.which("ollama") is not None, "ollama CLI", required=False, category="dependency"),
        add_check("ollama_api", "Ollama API", ollama_up, f"port {ollama_port}", required=False, category="service"),
        add_check("kc_frontend", "Knowledge Canvas Frontend", KC_FRONTEND_DIST_DIR.exists() or KC_FRONTEND_DIR.exists(), str(KC_FRONTEND_DIST_DIR if KC_FRONTEND_DIST_DIR.exists() else KC_FRONTEND_DIR), required=False, category="association"),
        add_check("kc_backend", "Knowledge Canvas Store", _knowledge_canvas_store is not None or (knowledge_canvas_app is not None and hasattr(knowledge_canvas_app.state, "store")), "mounted at /knowledge-canvas", required=False, category="association"),
        add_check("lancedb", "LanceDB Package", importlib.util.find_spec("lancedb") is not None, os.getenv("LANCE_PATH", "./data/lance"), required=False, category="association"),
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
        "marimo": marimo_up and _container_running("oglab-marimo"),
        "open-notebook": open_notebook_up and _container_running("oglab-open-notebook"),
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
        "aerollm_model": os.getenv("AEROLLM_MODEL", ""),
        "services": services,
        "service_checks": service_checks,
        "health_summary": {
            "passing_required": passing_required,
            "required_total": len(required_checks),
            "passing_total": passing_total,
            "total": len(service_checks),
        },
        "mode": os.getenv("OGLAB_MODE", "airgapped"),
    }


@app.get("/api/system/mode")
async def get_mode():
    return {"mode": os.getenv("OGLAB_MODE", "airgapped")}


@app.post("/api/system/mode")
async def set_mode(request: Request):
    """Toggle between airgapped and hybrid mode.  Writes to .env and
    updates the running process environment."""
    body = await request.json()
    new_mode = body.get("mode", "").lower()
    if new_mode not in ("airgapped", "hybrid"):
        return {"ok": False, "error": "mode must be 'airgapped' or 'hybrid'"}
    old_mode = os.getenv("OGLAB_MODE", "airgapped")
    os.environ["OGLAB_MODE"] = new_mode
    # Persist to .env
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        out, replaced = [], False
        for line in lines:
            if line.startswith("OGLAB_MODE="):
                out.append(f"OGLAB_MODE={new_mode}")
                replaced = True
            else:
                out.append(line)
        if not replaced:
            out.append(f"OGLAB_MODE={new_mode}")
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
    from oglab.costs import cost_tracker
    summary = cost_tracker.get_summary()
    # get_last_record() returns a dict (see oglab.costs.CostTracker),
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
    script_path = Path.cwd() / "oglab"
    if not script_path.exists():
        return {"error": "oglab dispatcher not found."}

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

from oglab.pkb import (
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
        "mode": os.getenv("OGLAB_MODE", "airgapped"),
        "current_goal": current_goal,
    })


# ── Browser Agent API ────────────────────────────────────────────────

@app.post("/api/browse")
async def browse_url_endpoint(request: Request):
    """Browse a URL via agent-browser, capture screenshot + text."""
    from oglab.agents.browser import browse_url
    body = await request.json()
    url = body.get("url", "").strip()
    if not url:
        return {"success": False, "error": "No URL provided"}
    result = browse_url(url)
    return result


@app.post("/api/browse/chat")
async def browse_chat_endpoint(request: Request):
    """Natural-language browser task via agent-browser chat."""
    from oglab.agents.browser import chat as ab_chat
    body = await request.json()
    instruction = body.get("instruction", "").strip()
    if not instruction:
        return {"success": False, "error": "No instruction provided"}
    result = ab_chat(instruction)
    return result


@app.get("/api/browse/suggestions")
async def browse_suggestions():
    """Generate goal-driven browse suggestions from credible sources."""
    from oglab.agents.browser import generate_suggestions
    current = goal_store.get_current()
    if not current:
        return {"suggestions": [], "message": "Set a goal first to get targeted suggestions."}
    goal_text = current.get("goal_text", "")
    domain = current.get("parsed", {}).get("domain", "general")
    suggestions = generate_suggestions(goal_text, domain)
    return {
        "suggestions": suggestions,
        "goal": goal_text,
        "mode": os.getenv("OGLAB_MODE", "airgapped"),
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
    from oglab.pkb_seed import list_packs
    return {"packs": list_packs()}


@app.post("/api/pkb/seed")
async def api_pkb_seed(request: Request):
    """Install (or re-install) a starter pack.

    Body: ``{"pack": "model-building", "force": false}``.
    Idempotent unless ``force=true``; missing files are filled in,
    user-edited files stay put (they only get overwritten on force).
    """
    from oglab.pkb_seed import install_pack
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

    from oglab.pkb import _pkb_root
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
    from oglab.pkb import _pkb_root
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
    from oglab.pkb import _pkb_root
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
    from oglab.pkb import _pkb_root
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
        from oglab import wiki
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
        from oglab import wiki
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
    from oglab.pkb import _pkb_root, ingest as run_ingest
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
        from oglab import wiki
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
# OGLAB_AUTORESEARCH_ENABLED is set in the environment. This keeps
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
    return templates.TemplateResponse(request, "tuning.html", {})


@app.get("/api/tuning/config")
async def api_tuning_config(backend: str = "aerollm"):
    """Return the hydrated tuning config for the selected backend.
    Safe to poll."""
    from oglab.experiments.autoresearch import _config_path
    from oglab.experiments.tuning import load_tuning
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
    from oglab.experiments.bench import load_runs
    from oglab.experiments.git_ops import diff_url
    b = _normalize_backend(backend)
    if b == "mlx":
        from oglab.experiments.mlx_backend import mlx_bench_file
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
    from oglab.experiments.autoresearch import run_autoresearch
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
    from oglab.experiments.autoresearch import (
        current_state, run_autoresearch,
    )
    b = _normalize_backend(backend)
    state = current_state(b)
    if state.phase in ("baseline", "variant"):
        return {"ok": False, "error": "loop already running",
                "state": state.to_dict()}

    # Preflight the safety rail at the endpoint so the UI gets a
    # clear "no" instead of a silent background error.
    if not os.getenv("OGLAB_AUTORESEARCH_ENABLED"):
        return {
            "ok": False,
            "error": (
                "OGLAB_AUTORESEARCH_ENABLED is not set. Export it "
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
    from oglab.experiments.autoresearch import current_state
    b = _normalize_backend(backend)
    return current_state(b).to_dict()


@app.post("/api/tuning/autoresearch/start_forever")
async def api_tuning_autoresearch_start_forever(backend: str = "aerollm"):
    """Kick off the continuous supervisor for the selected backend —
    sweeps every candidate, pauses, sweeps again, forever, until /stop
    is called. Returns immediately; poll /status for progress +
    pass_number."""
    from oglab.experiments.autoresearch import (
        current_state, run_autoresearch_forever,
    )
    b = _normalize_backend(backend)
    state = current_state(b)
    if state.phase in ("baseline", "variant") or state.continuous:
        return {"ok": False, "error": "loop already running",
                "state": state.to_dict()}
    if not os.getenv("OGLAB_AUTORESEARCH_ENABLED"):
        return {
            "ok": False,
            "error": (
                "OGLAB_AUTORESEARCH_ENABLED is not set. Export it "
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
    from oglab.experiments.autoresearch import current_state, request_stop
    b = _normalize_backend(backend)
    request_stop(b)
    return {"ok": True, "state": current_state(b).to_dict()}


@app.get("/api/tuning/autoresearch/schedule")
async def api_tuning_autoresearch_schedule_get():
    """Return the persisted schedule + live status (allowed_now, next
    open time). Safe to poll; cheap (one JSON read from disk)."""
    from oglab.experiments.autoresearch import load_schedule, schedule_status
    sched = load_schedule()
    return {"schedule": sched, "status": schedule_status(sched)}


@app.post("/api/tuning/autoresearch/schedule")
async def api_tuning_autoresearch_schedule_set(request: Request):
    """Update the schedule. Body shape:
        {"mode": "anytime"|"window"|"paused",
         "window_start": "HH:MM", "window_end": "HH:MM"}
    Invalid values are coerced to defaults rather than rejected so the
    UI never has to choreograph error handling."""
    from oglab.experiments.autoresearch import save_schedule, schedule_status
    try:
        body = await request.json()
    except Exception:
        body = {}
    sched = save_schedule(body or {})
    return {"schedule": sched, "status": schedule_status(sched)}


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

@app.get("/teacher", response_class=HTMLResponse)
async def teacher_page(request: Request):
    return templates.TemplateResponse(request, "teacher.html", {})


def _save_teacher_result(message: str, result: dict[str, Any]) -> dict[str, Any]:
    if result.get("error") or not result.get("reply"):
        return result

    saved = dict(result)
    try:
        from oglab.pkb import write_teacher_qa

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
        history=[],
        backend_override="aerollm",
        model_override=None,
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
            history=[],
            backend_override="aerollm",
            model_override=None,
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
    from oglab.pkb import _pkb_root
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
