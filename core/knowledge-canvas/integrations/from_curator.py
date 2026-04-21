"""
Integration hook for the existing Data Curator skill.

Approach: we don't force a rewrite of data_curator.py. Instead, this
module exposes one function — `pipe_to_canvas(curator_output)` — that
takes whatever the curator already returns and writes it into the
canvas. Existing curator code stays untouched; forks opt in with one
line.

Expected shape of curator output (matches current core/data-curator
implementation):
    {
        "goal": {...parsed goal...},
        "sources": [
            {"name": "USDA NASS Quickstats", "type": "rest_api", "url": ...,
             "description": ..., "available_data": [...], ...},
            ...
        ],
        "domain": "farming",
    }

Usage in existing curator code:

    # core/data-curator/data_curator.py
    from core.knowledge_canvas.integrations.from_curator import pipe_to_canvas

    def curate(goal):
        result = existing_curator_logic(goal)
        pipe_to_canvas(result)      # <-- one line
        return result
"""
from typing import Any

from core.knowledge_canvas.client import canvas


def pipe_to_canvas(curator_output: dict[str, Any]) -> dict[str, int]:
    """
    Pipe curator output into the canvas. Returns counts:
      {"ingested": N, "linked": M, "failed": K}

    Links the goal (as a markdown-kind source) to every ingested source
    via MOTIVATES edges so the canvas shows what sources were pulled
    *for* which goal.
    """
    domain = curator_output.get("domain", "unknown")
    sources = curator_output.get("sources", []) or []
    goal = curator_output.get("goal") or {}

    ingested = 0
    failed = 0
    linked = 0

    # Ingest the goal itself first, so we have a target for MOTIVATES edges
    goal_text = _goal_to_text(goal)
    goal_uri = f"goal::{domain}::{goal.get('id') or abs(hash(goal_text)) & 0xffffffff:x}"
    goal_result = canvas.ingest({
        "kind": "markdown",
        "title": f"Goal: {_goal_title(goal)}",
        "uri": goal_uri,
        "body_excerpt": goal_text,
        "tags": [domain, "goal"] + (goal.get("tags") or []),
        "domain": domain,
        "ingested_by": "curator",
    })
    goal_id = goal_result["id"] if goal_result else None

    # Ingest each source, link it to the goal
    for s in sources:
        payload = _source_config_to_payload(s, domain)
        result = canvas.ingest(payload)
        if result:
            ingested += 1
            if goal_id:
                if canvas.link(result["id"], goal_id, rel="MOTIVATES"):
                    linked += 1
        else:
            failed += 1

    return {"ingested": ingested, "linked": linked, "failed": failed}


def _source_config_to_payload(s: dict, domain: str) -> dict:
    """Normalize a curator-style source config into a canvas ingest payload."""
    kind = "dataset" if s.get("type") in ("document_database", "local_json") else "api_snapshot"
    return {
        "kind": kind,
        "title": s.get("name") or s.get("source_name", "Untitled source"),
        "uri": s.get("url") or s.get("path") or s.get("name"),
        "body_excerpt": _describe_source(s),
        "tags": [domain] + (s.get("available_data") or [])[:5],
        "domain": domain,
        "ingested_by": "curator",
        "meta": {
            "type": s.get("type"),
            "auth_required": s.get("auth_required"),
            "available_data": s.get("available_data"),
        },
    }


def _describe_source(s: dict) -> str:
    parts = [s.get("description", "")]
    if s.get("available_data"):
        parts.append("Available: " + ", ".join(s["available_data"]))
    if s.get("historical_years"):
        parts.append(f"History: {s['historical_years']} years")
    return "\n".join(p for p in parts if p)[:4000]


def _goal_title(goal: dict) -> str:
    return (goal.get("raw_text") or goal.get("title") or goal.get("description", ""))[:80] or "Unnamed goal"


def _goal_to_text(goal: dict) -> str:
    lines = []
    if goal.get("raw_text"):
        lines.append(goal["raw_text"])
    if goal.get("success_metrics"):
        lines.append(f"Success metrics: {goal['success_metrics']}")
    if goal.get("constraints"):
        lines.append(f"Constraints: {goal['constraints']}")
    return "\n\n".join(str(l) for l in lines)[:4000]
