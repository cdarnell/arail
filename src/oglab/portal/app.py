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
    return templates.TemplateResponse(request, "terminal.html")


@app.get("/notebook", response_class=HTMLResponse)
async def notebook_page(request: Request):
    return templates.TemplateResponse(request, "notebook.html")


@app.get("/plugins", response_class=HTMLResponse)
async def plugins_page(request: Request):
    plugins = plugin_mgr.list_plugins()
    return templates.TemplateResponse(request, "plugins.html", {
        "plugins": plugins,
    })


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


@app.get("/api/research/status")
async def research_status():
    current = goal_store.get_current()
    return {
        "status": researcher.status,
        "progress": current["progress"] if current else 0,
        "report": current.get("report") if current else None,
    }


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

    try:
        response = router.complete(
            prompt,
            max_tokens=int(body.get("max_tokens") or 512),
            temperature=float(body.get("temperature") or 0.7),
        )
    except Exception as e:  # noqa: BLE001
        activity_log.emit("chat",
                          f"Inference failed: {type(e).__name__}: {str(e)[:120]}",
                          "error")
        return {
            "reply": f"Inference failed: {e}",
            "backend": router.backend_name,
            "error": str(e),
        }

    reply = (response.text or "").strip()
    if not reply:
        reply = "(model returned no text — try rephrasing)"

    activity_log.emit("chat",
                      f"Chat turn ({response.tokens_used} tokens, "
                      f"{response.latency_ms:.0f} ms)",
                      "info")

    return {
        "reply": reply,
        "backend": response.backend,
        "model": response.model,
        "latency_ms": response.latency_ms,
        "tokens_used": response.tokens_used,
        "error": None,
    }


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
    }


@app.get("/api/system/costs")
async def system_costs():
    """Return cost tracking summary — cloud-equivalent spend and energy costs."""
    from oglab.costs import cost_tracker
    summary = cost_tracker.get_summary()
    last = cost_tracker.get_last_record()
    return {
        "summary": summary,
        "last_record": {
            "backend": last.backend,
            "model_class": last.model_class,
            "cloud_cost_usd": last.cloud_cost_usd,
            "energy_cost_usd": last.energy_cost_usd,
            "tokens_in": last.tokens_in,
            "tokens_out": last.tokens_out,
        } if last else None,
    }


@app.get("/api/addons/status")
async def addons_status():
    """Probe optional compose-based add-ons (Marimo, Open Notebook).

    Returns a list of add-ons with a live flag — the dashboard uses this to
    light up chips when the services are running. TCP connect only; we never
    hit the actual HTTP endpoints.
    """
    bind = os.getenv("BIND_ADDR", "127.0.0.1")
    addons = [
        {
            "id": "marimo",
            "name": "Marimo",
            "tagline": "reactive notebook — experiment",
            "port": int(os.getenv("MARIMO_PORT", "2718")),
            "url": f"http://{bind}:{os.getenv('MARIMO_PORT', '2718')}",
        },
        {
            "id": "open-notebook",
            "name": "Open Notebook",
            "tagline": "NotebookLM alternative — curate",
            "port": int(os.getenv("OPEN_NOTEBOOK_PORT", "8502")),
            "url": f"http://{bind}:{os.getenv('OPEN_NOTEBOOK_PORT', '8502')}",
        },
    ]

    async def _alive(port: int) -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(bind, port), timeout=0.3
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            return False

    results = await asyncio.gather(*(_alive(a["port"]) for a in addons))
    for addon, alive in zip(addons, results):
        addon["alive"] = alive
    return {"addons": addons}


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
    return templates.TemplateResponse(request, "knowledge.html", {
        "pkb": data,
        # Legacy context key so the existing template doesn't need to change
        # in this commit; knowledge.html will be updated in a follow-up.
        "pkm": data,
    })


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
