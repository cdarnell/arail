"""OGLab Portal — local web dashboard served at oglab.local."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

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

_BRAND = load_brand()

app = FastAPI(title=_BRAND.name, docs_url="/api/docs")
app.include_router(wiki_router)

PORTAL_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=PORTAL_DIR / "static"), name="static")
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
    intent_name = os.getenv("LAB_INTENT_NAME", "AI Engineer")
    activity_log.emit("system",
                      f"{_BRAND.name} portal started — {intent_name} lab.",
                      "success")

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
    return templates.TemplateResponse(request, "graph.html")


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
    return templates.TemplateResponse(request, "agents.html", {})


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
    import subprocess as sp
    manifest_path = Path.cwd() / "components.json"
    if not manifest_path.exists():
        return {"components": []}
    manifest = json.loads(manifest_path.read_text())
    out = []
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
        "openrouter": "OpenRouter", "claude": "Claude", "airllm": "AirLLM",
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


@app.post("/api/chat")
async def api_chat(request: Request):
    """Send one user message to the local model with full lab context.

    Request JSON:
        {
          "message": "What commands can I run?",
          "history": [{"role": "user"|"assistant", "content": "..."}]
        }

    Response JSON:
        {
          "reply": "…",
          "backend": "mlx",
          "latency_ms": 245.3,
          "tokens_used": 118,
          "error": null
        }
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = (body.get("message") or "").strip()
    history = body.get("history") or []
    if not message:
        return {"error": "message required"}
    if not isinstance(history, list):
        history = []
    # Keep history bounded so token cost stays predictable.
    history = history[-_CHAT_HISTORY_LIMIT:]

    from oglab import lab_brain
    from oglab.router import ModelRouter

    prompt = lab_brain.build_chat_prompt(message, history)

    # Deep-backend override — lets the user opt into AirLLM for one
    # message without flipping MODEL_BACKEND in .env. First call
    # takes minutes (model loads layer-by-layer from disk); we cache
    # the instance so subsequent "deep" calls reuse it.
    wants_deep = str(body.get("backend") or "").strip().lower() == "airllm"
    deep_backend = None
    if wants_deep:
        try:
            deep_backend = _get_deep_backend()
        except Exception as e:  # noqa: BLE001
            activity_log.emit(
                "chat",
                f"AirLLM init failed: {type(e).__name__}: {e}",
                "warn",
            )
            return {
                "reply": (
                    "AirLLM isn't ready on this lab. Install it "
                    "(`pip install airllm`) and ensure AIRLLM_MODEL in "
                    f".env points at a downloaded model.\n\nError: {e}"
                ),
                "backend": "airllm",
                "error": str(e),
            }

    try:
        router = ModelRouter()
    except Exception as e:  # noqa: BLE001
        activity_log.emit("chat",
                          f"Router unavailable: {type(e).__name__}: {e}",
                          "error")
        return {
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

    # Per-request model override — lets the dashboard Tuning row pick
    # a different model without a portal restart. Single-model backends
    # (MLX, llama.cpp, AirLLM) ignore it; network backends (openai_compat,
    # openrouter, huggingface, claude) temporarily swap `model_name`
    # for the duration of one call.
    override_model = (body.get("model") or "").strip() or None
    previous_model = None
    active_backend = deep_backend if deep_backend is not None else router._backend
    if override_model and hasattr(active_backend, "model_name"):
        if override_model != active_backend.model_name:
            previous_model = active_backend.model_name
            active_backend.model_name = override_model

    # top_p is optional — only sent when a preset explicitly sets it or
    # the user flips an advanced slider. Backends silently drop it when
    # they don't support it.
    tp_raw = body.get("top_p")
    try:
        top_p = float(tp_raw) if tp_raw is not None and tp_raw != "" else None
    except (TypeError, ValueError):
        top_p = None

    max_tokens = int(body.get("max_tokens") or 512)
    temperature = float(body.get("temperature") or 0.7)

    try:
        # When wants_deep, bypass the router and call AirLLM directly
        # so we don't tangle the MLX instance with the AirLLM one.
        # Cost tracker still records (via the same pathway below).
        if deep_backend is not None:
            import asyncio as _aio
            response = await _aio.to_thread(
                deep_backend.complete,
                prompt, max_tokens, temperature, top_p,
            )
            # AirLLM path bypasses router.complete() which is where
            # cost tracking normally happens — track manually so the
            # dashboard meter stays accurate.
            from oglab.costs import cost_tracker
            cost_tracker.track(
                backend=response.backend,
                model=response.model,
                tokens_in=max(len(prompt) // 4, 1),
                tokens_out=response.tokens_used,
                latency_ms=response.latency_ms,
            )
        else:
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
            "backend": (deep_backend.backend_name if wants_deep
                        else router.backend_name),
            "error": str(e),
        }
    finally:
        # Restore the original model on every exit path — success,
        # exception, return — so the override is truly per-call.
        if previous_model is not None and hasattr(active_backend, "model_name"):
            active_backend.model_name = previous_model

    reply = (response.text or "").strip()
    if not reply:
        reply = "(model returned no text — try rephrasing)"

    # Metrics — surface what the reply cost so the UI can show it.
    # The cost tracker just updated its history; pull the record we
    # just wrote rather than recomputing.
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


# Deep-backend cache — AirLLM init loads the whole model layer-by-
# layer from disk (expensive). Cache the instance so subsequent
# "deep" chat calls reuse it. Lazy: never instantiated unless the
# user actually opts in via the UI.
_DEEP_BACKEND_CACHE = None


def _get_deep_backend():
    global _DEEP_BACKEND_CACHE
    if _DEEP_BACKEND_CACHE is None:
        from oglab.router.backends import AirLLMBackend
        _DEEP_BACKEND_CACHE = AirLLMBackend()
        # Give the AirLLM instance the same interface as other
        # backends so cost tracking + error handling above treat it
        # uniformly.
        _DEEP_BACKEND_CACHE.backend_name = "airllm"
    return _DEEP_BACKEND_CACHE


@app.get("/api/chat/models")
async def api_chat_models():
    """Return the model catalog for the current backend.

    For OpenAI-compatible backends (LM Studio, Ollama, NVIDIA NIM,
    OpenRouter), we query the server's ``/v1/models`` endpoint and
    list every model it advertises. For single-model backends
    (MLX, llama.cpp, AirLLM, Claude, HF Inference), we return just
    the configured ``MODEL_NAME`` so the dropdown still renders.

    The dashboard Tuning row uses this to populate its Model picker.
    """
    from oglab.router import ModelRouter
    try:
        router = ModelRouter()
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
    if backend_name in ("mlx", "cpu", "airllm", "cuda"):
        models_dir = Path(os.getenv("OGLAB_MODELS_DIR", "lab/models"))
        if models_dir.exists():
            try:
                local_models = sorted(
                    p.name for p in models_dir.iterdir()
                    if p.is_dir()
                    and not p.name.startswith(".")
                    and not p.name.startswith("_")
                    # Skip cache dirs (airllm_cache, hf_cache, etc.) —
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
        else:  # airllm
            example = (
                "huggingface-cli download Qwen/Qwen3-235B-A22B "
                f"--local-dir {models_dir}/Qwen3-235B-A22B"
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
    deep_model_name = os.getenv("AIRLLM_MODEL", "Qwen/Qwen3-235B-A22B")
    # Look up the spec sheet so the Frontier chip hover can show
    # strengths, benchmarks, and license at a glance. Registry lives
    # in src/oglab/model_specs.py — users edit it to add new models.
    from oglab.model_specs import lookup as _spec_lookup
    spec = _spec_lookup(deep_model_name)

    deep_info = {
        "model": deep_model_name,
        # Whether the airllm package is importable. When False, the
        # UI can swap the toggle for an install hint.
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
    }

    return {
        "backend": backend_name,
        "current": current,
        "models": models,
        "switchable": backend_name in ("openai_compat", "openrouter"),
        "local_models": local_models,
        "install_hint": install_hint,
        "deep": deep_info,
    }


def _is_airllm_installed() -> bool:
    """airllm is optional — check without importing since the import
    itself is heavy (drags torch)."""
    import importlib.util
    return importlib.util.find_spec("airllm") is not None


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
    deep_enabled = os.getenv("AIRLLM_RESEARCH", "false").lower() == "true"
    if deep_enabled:
        tier = "deep"
    elif ram_total_gb >= 16 and disk_free_gb >= 40:
        tier = "full"
    elif ram_total_gb >= 8 and disk_free_gb >= 20:
        tier = "standard"

    # Python
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    # Services status  (quick check via ports)
    import socket
    def port_open(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except (OSError, ConnectionRefusedError):
            return False

    services = {
        "portal": True,  # we're running
        "ttyd": port_open(int(os.getenv("TTYD_PORT", "7681"))),
        "jupyter": port_open(int(os.getenv("JUPYTER_PORT", "8888"))),
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
        "airllm_model": os.getenv("AIRLLM_MODEL", ""),
        "services": services,
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
