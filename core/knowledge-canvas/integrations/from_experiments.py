"""
Integration hook for the Experiment Tracker skill.

When an experiment is created, started, or completed, pipe it into the
canvas. Experiments become `experiment_log` sources and link back to
the sources that motivated them (if known) via DERIVED_FROM edges.

Usage:

    # core/experiment-tracker/experiment_tracker.py
    from core.knowledge_canvas.integrations.from_experiments import pipe_experiment

    def complete_experiment(exp_id, results):
        exp = existing_complete_logic(exp_id, results)
        pipe_experiment(exp)
        return exp
"""
from typing import Any

from core.knowledge_canvas.client import canvas


def pipe_experiment(experiment: dict[str, Any]) -> dict | None:
    """
    Push an experiment record into the canvas. Returns the ingested
    source (or None if backend unreachable — it'll replay from queue).
    """
    payload = {
        "kind": "experiment_log",
        "title": experiment.get("title") or experiment.get("hypothesis", "Experiment")[:80],
        "uri": f"experiment::{experiment['id']}",
        "body_excerpt": _summarize(experiment),
        "tags": (experiment.get("tags") or []) + ["experiment",
                  f"status:{experiment.get('status', 'unknown')}"],
        "domain": experiment.get("domain"),
        "year": _year_from(experiment.get("completed_at") or experiment.get("started_at")),
        "ingested_by": "experiment",
        "meta": {
            "status": experiment.get("status"),
            "metrics": experiment.get("metrics"),
            "goal_id": experiment.get("goal_id"),
            "started_at": experiment.get("started_at"),
            "completed_at": experiment.get("completed_at"),
        },
    }
    result = canvas.ingest(payload)
    if not result:
        return None

    # Link to source IDs the experiment cited, if provided
    for src_id in experiment.get("motivated_by_source_ids", []):
        canvas.link(result["id"], src_id, rel="DERIVED_FROM")

    # Link to the goal, if provided as a source ID
    if experiment.get("goal_source_id"):
        canvas.link(result["id"], experiment["goal_source_id"], rel="MOTIVATES")

    return result


def _summarize(exp: dict) -> str:
    parts = [
        f"Hypothesis: {exp.get('hypothesis', '')}",
        f"Method: {exp.get('methodology', '')}",
    ]
    if exp.get("results"):
        parts.append("Results: " + ", ".join(
            f"{k}={v}" for k, v in exp["results"].items()
        ))
    if exp.get("observations"):
        obs = exp["observations"]
        parts.append(f"Observations ({len(obs)}): " + "; ".join(
            str(o)[:100] for o in obs[:5]
        ))
    return "\n\n".join(parts)[:4000]


def _year_from(dt):
    if not dt:
        return None
    s = str(dt)
    return int(s[:4]) if s[:4].isdigit() else None
