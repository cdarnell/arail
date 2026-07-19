"""Superskill manifest generation for arail-launched nucleus builds.

The orchestrator requires ``superskill_manifest_path`` to resolve under its
``configs/`` tree, so generated manifests are written to
``$NUCLEUS_CONFIGS_DIR/arail-generated/<run_id>.yaml`` and submitted as the
relative path ``configs/arail-generated/<run_id>.yaml``.

Nucleus loads manifests via ``yaml.safe_load`` into plain dicts (unknown
top-level keys are tolerated), so arail-specific fields — the MoE/dense
architecture request among them — ride in an ``arail_extensions`` block.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict

RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# Teacher model ids per build mode (mirrors nucleus configs/*.yaml usage).
ANTHROPIC_TIER1 = "claude-opus-4-8"
ANTHROPIC_TIER2 = "claude-haiku-4-5"


def nucleus_configs_dir() -> Path:
    configured = os.getenv("NUCLEUS_CONFIGS_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path("~/ProJects/qukaizen-nucleus/configs").expanduser()


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id or ""):
        raise ValueError(
            "run_id must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    return run_id


def build_manifest(*, run_id: str, mode: str, spec: Dict[str, Any],
                   domain: str, subdomains: list[str],
                   student_model: str) -> Dict[str, Any]:
    """mode: local | anthropix | hybrid (dry_run is a start-flag, not a mode)."""
    if mode == "anthropix":
        teacher1, teacher2 = ANTHROPIC_TIER1, ANTHROPIC_TIER2
    elif mode == "hybrid":
        # Local bulk generation, Anthropic escalation on failure hotspots.
        teacher1, teacher2 = "local-teacher", ANTHROPIC_TIER2
    else:
        teacher1, teacher2 = "local-teacher", "local-teacher"

    return {
        "schema_version": "1.0",
        "name": f"ARAIL build {run_id}",
        "id": run_id,
        "mode": 1,
        "domain": {
            "name": domain,
            "description": f"ARAIL-launched build for domain '{domain}'.",
            "subdomains": subdomains or [domain],
        },
        "deployment_profile": "commodity",
        "models": {
            "teacher_tier1": teacher1,
            "teacher_tier2": teacher2,
            "student": student_model,
        },
        "kice": {"layers": {f"l{i}_{n}": True for i, n in enumerate(
            ["rare_concepts", "edge_cases", "historical_conflicts",
             "subsystem_interactions", "nuanced_reasoning",
             "ambiguity_detection", "tacit_knowledge"], start=1)}},
        "arail_extensions": {
            "launched_by": "arail-model-building-tab",
            "build_mode": mode,
            "architecture": spec.get("arch", "dense"),
            "moe": spec.get("moe"),
            "params_b": spec.get("params_b"),
            "precision": spec.get("precision"),
            "method": spec.get("method"),
            "seq_len": spec.get("seq_len"),
            "dataset_source": spec.get("dataset_source"),
            "dataset_tokens_est": spec.get("dataset_tokens_est"),
        },
    }


def write_manifest(run_id: str, manifest: Dict[str, Any]) -> tuple[Path, str]:
    """Write under nucleus configs/; return (abs_path, orchestrator-relative)."""
    import yaml
    validate_run_id(run_id)
    out_dir = nucleus_configs_dir() / "arail-generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run_id}.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return path, f"configs/arail-generated/{run_id}.yaml"
