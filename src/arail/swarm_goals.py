"""Swarm-goal planning helpers.

Compile a user goal into a lightweight goal dossier and a reviewable
swarm execution plan. The output is deliberately plain dictionaries so
it can be persisted directly in ``GoalStore`` records and surfaced over
the portal APIs without extra serialization glue.
"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any, Iterable


_TRAVEL_KEYWORDS = {
    "trip", "travel", "flight", "flights", "hotel", "hotels", "itinerary",
    "vacation", "holiday", "route", "routes", "stay", "lodging", "japan",
    "tokyo", "kyoto", "osaka", "hokkaido", "visa", "rail", "train",
}

_RESEARCH_KEYWORDS = {
    "benchmark", "rag", "eval", "evaluation", "dataset", "model", "models",
    "inference", "training", "llm", "retrieval", "latency", "accuracy",
}

_OPS_KEYWORDS = {
    "deploy", "deployment", "incident", "uptime", "latency", "slo", "sli",
    "reliability", "capacity", "scaling", "alert", "alerts", "runbook",
}

_BASE_WORKERS: list[dict[str, Any]] = [
    {
        "id": "scout",
        "label": "Scout",
        "role": "Map the search space",
        "purpose": "Survey what options, sources, and routes matter before the lead narrows down the run.",
        "deliverable": "A compact option map with the highest-signal branches to investigate.",
        "depends_on": [],
        "kind": "research",
    },
    {
        "id": "critic",
        "label": "Critic",
        "role": "Stress-test assumptions",
        "purpose": "Surface hidden risks, contradictions, and weak assumptions before the swarm commits to a path.",
        "deliverable": "A short list of risks, open questions, and confidence gaps.",
        "depends_on": ["scout"],
        "kind": "review",
    },
]

_ARCHETYPE_WORKERS: dict[str, list[dict[str, Any]]] = {
    "travel": [
        {
            "id": "seasonality",
            "label": "Seasonality",
            "role": "Season and crowd analyst",
            "purpose": "Model the travel window, crowd pressure, weather, and event timing against the goal.",
            "deliverable": "A timing brief with favorable windows, crowd risks, and weather tradeoffs.",
            "depends_on": ["scout"],
            "kind": "analysis",
        },
        {
            "id": "routing",
            "label": "Routing",
            "role": "Transport and route planner",
            "purpose": "Turn destinations into feasible movement plans across flights, rail, and local transit.",
            "deliverable": "A route skeleton with transfer risks, travel time, and simplification opportunities.",
            "depends_on": ["scout"],
            "kind": "planning",
        },
        {
            "id": "lodging",
            "label": "Lodging",
            "role": "Stay shortlister",
            "purpose": "Match neighborhoods and lodging types to the group shape, pace, and budget constraints.",
            "deliverable": "A lodging shortlist by stop with neighborhood tradeoffs and fit notes.",
            "depends_on": ["seasonality", "routing"],
            "kind": "planning",
        },
        {
            "id": "budget",
            "label": "Budget",
            "role": "Tradeoff modeler",
            "purpose": "Frame price-sensitive decisions and show where comfort, time, and spend pull against each other.",
            "deliverable": "A budget envelope with the major cost drivers and where to splurge or save.",
            "depends_on": ["routing", "lodging"],
            "kind": "analysis",
        },
    ],
    "research": [
        {
            "id": "literature",
            "label": "Literature",
            "role": "Prior-art scout",
            "purpose": "Pull in prior art, baselines, and comparable experiments before new work starts.",
            "deliverable": "A prior-art brief with the most relevant baselines and methods.",
            "depends_on": ["scout"],
            "kind": "research",
        },
        {
            "id": "eval",
            "label": "Eval",
            "role": "Measurement designer",
            "purpose": "Turn the goal into crisp success metrics, validation criteria, and stop conditions.",
            "deliverable": "A measurement plan with metrics, thresholds, and failure modes.",
            "depends_on": ["literature"],
            "kind": "evaluation",
        },
        {
            "id": "variants",
            "label": "Variants",
            "role": "Experiment branch planner",
            "purpose": "Generate high-signal test branches instead of one monolithic experiment path.",
            "deliverable": "A ranked experiment slate with the strongest variants to try first.",
            "depends_on": ["eval"],
            "kind": "planning",
        },
        {
            "id": "synthesizer",
            "label": "Synthesizer",
            "role": "Decision packager",
            "purpose": "Turn evidence into next actions, recommended bets, and a clear call on what to do next.",
            "deliverable": "A concise decision pack with ranked next actions.",
            "depends_on": ["variants", "critic"],
            "kind": "synthesis",
        },
    ],
    "operations": [
        {
            "id": "signals",
            "label": "Signals",
            "role": "Telemetry analyst",
            "purpose": "Map the signals and observability surfaces that will prove whether the change actually worked.",
            "deliverable": "A telemetry brief with leading and lagging indicators.",
            "depends_on": ["scout"],
            "kind": "analysis",
        },
        {
            "id": "runbooks",
            "label": "Runbooks",
            "role": "Operational planner",
            "purpose": "Convert the goal into safe operational procedures, rollback points, and escalation boundaries.",
            "deliverable": "A runbook outline with rollback and escalation steps.",
            "depends_on": ["signals"],
            "kind": "planning",
        },
        {
            "id": "capacity",
            "label": "Capacity",
            "role": "Load and failure planner",
            "purpose": "Model headroom, failure domains, and where the plan will break first.",
            "deliverable": "A capacity and failure-pressure brief with the likely breaking points.",
            "depends_on": ["signals"],
            "kind": "analysis",
        },
        {
            "id": "reviewer",
            "label": "Reviewer",
            "role": "Blast-radius reviewer",
            "purpose": "Challenge the plan from the perspective of risk, reversibility, and blast radius.",
            "deliverable": "A rollback and risk memo.",
            "depends_on": ["runbooks", "capacity"],
            "kind": "review",
        },
    ],
    "general": [
        {
            "id": "mapper",
            "label": "Mapper",
            "role": "Outcome mapper",
            "purpose": "Break the goal into concrete lanes that can run in parallel without losing the main objective.",
            "deliverable": "A lane map with what to learn, decide, or produce in each branch.",
            "depends_on": ["scout"],
            "kind": "planning",
        },
        {
            "id": "evaluator",
            "label": "Evaluator",
            "role": "Success metric keeper",
            "purpose": "Translate vague success language into measurable checks and stop conditions.",
            "deliverable": "A success rubric with decision thresholds.",
            "depends_on": ["mapper"],
            "kind": "evaluation",
        },
        {
            "id": "synthesizer",
            "label": "Synthesizer",
            "role": "Decision packager",
            "purpose": "Collapse the swarm output into ranked recommendations and an operator-ready next step.",
            "deliverable": "A concise decision pack with recommended next actions.",
            "depends_on": ["evaluator", "critic"],
            "kind": "synthesis",
        },
    ],
}

_SCALE_LIMITS = {
    "compact": 3,
    "balanced": 4,
    "expanded": 6,
}


def default_swarm_scale() -> str:
    raw = os.getenv("ARAIL_SWARM_SCALE", "balanced").strip().lower()
    if raw in _SCALE_LIMITS:
        return raw
    return "balanced"


def detect_goal_archetype(goal_text: str, domain: str) -> str:
    lower = goal_text.lower()
    if any(token in lower for token in _TRAVEL_KEYWORDS):
        return "travel"
    if domain == "ml-research" or any(token in lower for token in _RESEARCH_KEYWORDS):
        return "research"
    if any(token in lower for token in _OPS_KEYWORDS):
        return "operations"
    return "general"


def compile_goal_dossier(parsed_goal: dict[str, Any]) -> dict[str, Any]:
    goal_text = str(parsed_goal.get("goal") or parsed_goal.get("primary_objective") or "").strip()
    success_metrics = parsed_goal.get("success_metrics") or {}
    constraints = _as_str_list(parsed_goal.get("constraints"))
    resources = _as_str_list(parsed_goal.get("resources_needed"))
    sub_objectives = _as_str_list(parsed_goal.get("sub_objectives"))
    entities = parsed_goal.get("extracted_entities") if isinstance(parsed_goal.get("extracted_entities"), dict) else {}
    return {
        "goal_text": goal_text,
        "domain": str(parsed_goal.get("domain") or "general"),
        "primary_objective": str(parsed_goal.get("primary_objective") or goal_text),
        "sub_objectives": sub_objectives,
        "success_metrics": success_metrics if isinstance(success_metrics, dict) else {},
        "timeline": str(parsed_goal.get("timeline") or "unspecified"),
        "constraints": constraints,
        "resources_needed": resources,
        "confidence": parsed_goal.get("confidence"),
        "entities": entities,
    }


def compile_swarm_plan(
    parsed_goal: dict[str, Any],
    *,
    scale: str | None = None,
    operator_notes: str = "",
    enabled_workers: Iterable[str] | None = None,
) -> dict[str, Any]:
    dossier = compile_goal_dossier(parsed_goal)
    goal_text = dossier["goal_text"]
    domain = dossier["domain"]
    archetype = detect_goal_archetype(goal_text, domain)
    resolved_scale = scale if scale in _SCALE_LIMITS else default_swarm_scale()
    workers = _compile_workers(archetype, resolved_scale, enabled_workers)
    worker_ids = [worker["id"] for worker in workers]

    return {
        "version": 1,
        "status": "draft",
        "execution_mode": "review_then_run",
        "scale": resolved_scale,
        "goal_archetype": archetype,
        "mission_brief": _mission_brief(dossier, archetype),
        "operator_notes": operator_notes.strip(),
        "lead": {
            "id": "researcher",
            "label": "Lead Researcher",
            "role": "Own the synthesis, coordinate workers, and deliver the final recommendation.",
        },
        "memory": {
            "primary": "lancedb",
            "backup": "json",
            "shared_collections": ["agent_workflows", "pkb"],
        },
        "workers": workers,
        "phases": _compile_phases(worker_ids, archetype),
        "review": {
            "assumptions": _infer_assumptions(dossier, archetype),
            "open_questions": _infer_questions(dossier, archetype),
            "deliverables": _deliverables(archetype),
        },
    }


def apply_swarm_plan_edits(
    plan: dict[str, Any],
    *,
    mission_brief: str | None = None,
    operator_notes: str | None = None,
    enabled_workers: Iterable[str] | None = None,
) -> dict[str, Any]:
    updated = deepcopy(plan)
    if mission_brief is not None:
        updated["mission_brief"] = mission_brief.strip()
    if operator_notes is not None:
        updated["operator_notes"] = operator_notes.strip()
    enabled = set(enabled_workers) if enabled_workers is not None else None
    if enabled is not None:
        for worker in updated.get("workers", []):
            worker_id = str(worker.get("id") or "")
            worker["enabled"] = worker_id in enabled
        active_worker_ids = [w["id"] for w in updated.get("workers", []) if w.get("enabled")]
        for phase in updated.get("phases", []):
            phase["worker_ids"] = [worker_id for worker_id in phase.get("worker_ids", []) if worker_id in active_worker_ids]
    return updated


def known_swarm_worker_ids() -> list[str]:
    seen: set[str] = set()
    worker_ids: list[str] = []
    for worker in _BASE_WORKERS:
        worker_id = str(worker.get("id") or "")
        if worker_id and worker_id not in seen:
            seen.add(worker_id)
            worker_ids.append(worker_id)
    for catalog in _ARCHETYPE_WORKERS.values():
        for worker in catalog:
            worker_id = str(worker.get("id") or "")
            if worker_id and worker_id not in seen:
                seen.add(worker_id)
                worker_ids.append(worker_id)
    return worker_ids


def _compile_workers(
    archetype: str,
    scale: str,
    enabled_workers: Iterable[str] | None,
) -> list[dict[str, Any]]:
    enabled = set(enabled_workers) if enabled_workers is not None else None
    catalog = deepcopy(_BASE_WORKERS + _ARCHETYPE_WORKERS.get(archetype, _ARCHETYPE_WORKERS["general"]))
    limit = _SCALE_LIMITS[scale]
    workers: list[dict[str, Any]] = []
    for worker in catalog[:limit]:
        worker["enabled"] = True if enabled is None else worker["id"] in enabled
        workers.append(worker)
    return workers


def _compile_phases(worker_ids: list[str], archetype: str) -> list[dict[str, Any]]:
    initial = worker_ids[:2]
    middle = worker_ids[1:-1] or worker_ids[:1]
    final = worker_ids[-2:] if len(worker_ids) > 2 else worker_ids
    return [
        {
            "id": "shape",
            "title": "Shape the objective",
            "objective": "Clarify what success looks like and which branches are worth parallel effort.",
            "worker_ids": initial,
            "done_when": "The lead has a crisp mission brief, assumptions list, and first-cut lane map.",
        },
        {
            "id": "branch",
            "title": "Run the parallel lanes",
            "objective": f"Let the {archetype} workers gather options, evidence, and tradeoffs without blocking each other.",
            "worker_ids": middle,
            "done_when": "Each enabled worker has produced a concrete deliverable the lead can compare.",
        },
        {
            "id": "challenge",
            "title": "Challenge and narrow",
            "objective": "Pressure-test the best branch, remove weak assumptions, and tighten the recommendation.",
            "worker_ids": final,
            "done_when": "The lead has a ranked answer, the risks, and the next operator move.",
        },
    ]


def _mission_brief(dossier: dict[str, Any], archetype: str) -> str:
    primary = str(dossier.get("primary_objective") or dossier.get("goal_text") or "").strip()
    timeline = str(dossier.get("timeline") or "unspecified")
    if archetype == "travel":
        return f"Plan a concrete trip recommendation for '{primary}' that balances timing, routing, stay fit, and spend."
    if archetype == "research":
        return f"Turn '{primary}' into a measurable research program with clear variants, metrics, and stop conditions."
    if archetype == "operations":
        return f"Deliver an operational plan for '{primary}' that is measurable, reversible, and safe under pressure."
    if timeline and timeline != "unspecified":
        return f"Break '{primary}' into a parallel plan the swarm can execute against the {timeline} horizon."
    return f"Break '{primary}' into parallel worker lanes, then synthesize the best answer with explicit tradeoffs."


def _infer_assumptions(dossier: dict[str, Any], archetype: str) -> list[str]:
    assumptions: list[str] = []
    if not dossier.get("constraints"):
        assumptions.append("No hard constraints were supplied yet, so the swarm will infer defaults and call them out.")
    if dossier.get("timeline") in (None, "", "unspecified"):
        assumptions.append("Timeline is still vague; recommendations should expose urgency-sensitive branches.")
    if not dossier.get("success_metrics"):
        assumptions.append("Success metrics are incomplete; the evaluator lane should sharpen them before execution drifts.")
    if archetype == "travel":
        assumptions.append("The trip plan should prioritize practicality over exhaustive option coverage.")
    elif archetype == "research":
        assumptions.append("The swarm should bias toward loops that can be measured locally with the current lab setup.")
    else:
        assumptions.append("The lead should preserve operator control and keep the answer compressible into next actions.")
    return assumptions


def _infer_questions(dossier: dict[str, Any], archetype: str) -> list[str]:
    questions: list[str] = []
    if not dossier.get("constraints"):
        questions.append("Which constraints are hard limits versus preferences?")
    if dossier.get("timeline") in (None, "", "unspecified"):
        questions.append("What time window or deadline should the swarm optimize for?")
    if not dossier.get("resources_needed"):
        questions.append("What tools, budget, or source access should the swarm assume it can use?")
    if archetype == "travel":
        questions.append("What matters most: lower travel friction, lower spend, or higher trip density?")
    elif archetype == "research":
        questions.append("Which measurement would most quickly disconfirm a bad branch?")
    elif archetype == "operations":
        questions.append("Which failure mode is least acceptable during rollout?")
    return questions


def _deliverables(archetype: str) -> list[str]:
    if archetype == "travel":
        return [
            "Recommended itinerary and route skeleton",
            "Timing and crowd-risk brief",
            "Lodging shortlist with tradeoffs",
            "Budget envelope and decision notes",
        ]
    if archetype == "research":
        return [
            "Measurement-ready research brief",
            "Ranked experiment variants",
            "Prior-art and baseline summary",
            "Operator-ready next experiment recommendation",
        ]
    if archetype == "operations":
        return [
            "Operational rollout brief",
            "Signals and telemetry checklist",
            "Risk and rollback memo",
            "Next safe operator action",
        ]
    return [
        "Lane map with ranked branches",
        "Success rubric and stop conditions",
        "Risk memo",
        "Lead recommendation with next actions",
    ]


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]