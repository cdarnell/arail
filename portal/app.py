"""OGLab Portal — local web dashboard served at oglab.local."""

from __future__ import annotations

import asyncio
import json
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
from oglab.skills.goal_parser import GoalParser
from oglab.skills.experiment_tracker import ExperimentTracker

app = FastAPI(title="OGLab", docs_url="/api/docs")

PORTAL_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=PORTAL_DIR / "static"), name="static")
templates = Jinja2Templates(directory=PORTAL_DIR / "templates")

consent_store = ConsentStore()
goal_store = GoalStore()
tracker = ExperimentTracker()
parser = GoalParser()
plugin_mgr = PluginManager()


@app.on_event("startup")
async def _startup():
    activity_log.emit("system", "OGLab portal started.", "success")


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
    try:
        parsed = parser.parse(goal_text)
    except Exception:
        parsed = parser.parse_offline(goal_text)
    record = goal_store.set_goal(parsed)
    activity_log.emit("goal", f"New goal set: {goal_text}", "info")
    return record


@app.get("/api/goal")
async def get_goal():
    return goal_store.get_current()


# ── Research API ─────────────────────────────────────────────────────────

@app.post("/api/research/start")
async def research_start():
    current = goal_store.get_current()
    if not current:
        return {"error": "No active goal. Set a goal first."}
    researcher.start(current["parsed"])
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
    except KeyError:
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
