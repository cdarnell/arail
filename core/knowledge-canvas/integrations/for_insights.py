"""
Integration hook for the Insight Generator skill.

The Insight Generator reads *from* the canvas (other integrations write
to it). This module exposes helpers the Insight Generator can use to
gather multi-source context without needing to know about LanceDB or
Neo4j.

Usage:

    # core/insight-generator/insight_generator.py
    from core.knowledge_canvas.integrations.for_insights import (
        gather_evidence, cross_source_patterns,
    )

    def generate_insights(goal):
        evidence = gather_evidence(goal)
        patterns = cross_source_patterns(evidence)
        return synthesize(patterns)
"""
from typing import Any

from core.knowledge_canvas.client import canvas


def gather_evidence(
    semantic: str,
    domain: str | None = None,
    k: int = 30,
    prefer_kinds: list[str] | None = None,
) -> list[dict]:
    """
    Pull sources related to a question. Returns a list of Source dicts
    sorted by semantic score, optionally weighted toward preferred kinds
    (e.g., papers + experiment_logs when generating research insights).
    """
    results = canvas.query(semantic=semantic, domain=domain, k=k)
    if prefer_kinds:
        results.sort(
            key=lambda r: (r["kind"] in prefer_kinds, r.get("score", 0.0)),
            reverse=True,
        )
    return results


def cross_source_patterns(sources: list[dict]) -> dict[str, Any]:
    """
    Summarize coverage across source kinds. Useful for the Insight
    Generator to surface things like "this claim is backed by 3 papers
    and 2 experiments but contradicted by a USDA pull."
    """
    by_kind: dict[str, list[dict]] = {}
    by_domain: dict[str, int] = {}
    for s in sources:
        by_kind.setdefault(s["kind"], []).append(s)
        d = s.get("domain") or "unknown"
        by_domain[d] = by_domain.get(d, 0) + 1

    return {
        "total": len(sources),
        "by_kind": {k: len(v) for k, v in by_kind.items()},
        "by_domain": by_domain,
        "has_experiment_evidence": "experiment_log" in by_kind,
        "has_peer_reviewed": "paper" in by_kind,
        "has_primary_data": "api_snapshot" in by_kind or "dataset" in by_kind,
        "sources_by_kind": by_kind,
    }
