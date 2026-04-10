"""OGLab Portal — local web dashboard served at oglab.local."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from oglab.agents.consent import ConsentStore
from oglab.skills.goal_parser import GoalParser
from oglab.skills.experiment_tracker import ExperimentTracker

app = FastAPI(title="OGLab", docs_url="/api/docs")

PORTAL_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=PORTAL_DIR / "static"), name="static")
templates = Jinja2Templates(directory=PORTAL_DIR / "templates")

consent_store = ConsentStore()
tracker = ExperimentTracker()
parser = GoalParser()


# ── Pages ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    experiments = tracker.list_all()
    allowed_domains = consent_store.list_allowed()
    pending = consent_store.list_pending()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "experiments": experiments,
        "allowed_domains": allowed_domains,
        "pending_requests": pending,
    })


@app.get("/terminal", response_class=HTMLResponse)
async def terminal_page(request: Request):
    """Proxied ttyd terminal (WezTerm/zsh)."""
    return templates.TemplateResponse("terminal.html", {"request": request})


@app.get("/notebook", response_class=HTMLResponse)
async def notebook_page(request: Request):
    """Embedded Jupyter."""
    return templates.TemplateResponse("notebook.html", {"request": request})


# ── Goal API ─────────────────────────────────────────────────────────────

@app.post("/api/goal")
async def set_goal(request: Request):
    body = await request.json()
    goal_text = body.get("goal", "")
    try:
        parsed = parser.parse(goal_text)
    except Exception:
        parsed = parser.parse_offline(goal_text)
    return parsed


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
    return {"status": "approved"}


@app.post("/api/consent/deny")
async def deny_request(request: Request):
    body = await request.json()
    consent_store.deny(body["id"])
    return {"status": "denied"}


@app.get("/api/consent/allowlist")
async def get_allowlist():
    return consent_store.list_allowed()
