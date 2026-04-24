"""prepare.py — validation substrate for the AeroLLM research goal.

This is the cheat-proof side of the research contract: the
researcher agent CANNOT modify this file. If it wants a better
throughput number, it has to write faster AeroLLM code, not
redefine what "good" means.

See program.md for the natural-language side.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

RANDOM_SEED = int(os.getenv("LAB_RESEARCH_SEED", "1337"))
DATA_DIR = Path(os.getenv("LAB_RESEARCH_DATA", "lab/research/data"))


def prepare_environment() -> Dict[str, Any]:
    """Return the evaluation environment. Idempotent."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return {
        "data_dir": DATA_DIR,
        "primary_metric": "tokens_per_minute",
        "secondary_metric": "quality_delta_vs_fp16",
        "metric_docstring": throughput_metric.__doc__,
        "random_seed": RANDOM_SEED,
        "min_runs": 3,
        "min_prompts_per_run": 10,
    }


def throughput_metric(model_name: str, duration_sec: float,
                      tokens_generated: int) -> float:
    """Measure inference throughput in tokens per minute.

    Higher is better. Captured automatically by the portal for every
    deep-model call; aggregates live at /api/aerollm/bench.
    """
    if duration_sec <= 0:
        return 0.0
    return (tokens_generated / duration_sec) * 60.0


def quality_delta_vs_fp16(before: float, after: float) -> float:
    """Absolute delta in validation score between FP16 baseline
    and the candidate quantization.

    Positive = worse (quality lost). Under 0.5% is noise; over 2%
    is user-visible. Anything in between is a judgment call for the
    research cycle.
    """
    return abs(before - after)


def check_guardrails(submission: Dict[str, Any]) -> Optional[str]:
    """Veto submissions that break the research contract."""
    # Must include at least 3 separate measurement runs.
    runs = submission.get("runs") or []
    if len(runs) < 3:
        return "need at least 3 separate runs to claim a throughput gain"
    # Must include FP16 baseline for comparison.
    if not submission.get("fp16_baseline"):
        return "missing FP16 baseline — can't measure quality delta"
    # Must pass quality gate.
    delta = submission.get("quality_delta_pct", 100)
    if delta > 0.5:
        return f"quality delta {delta}% exceeds 0.5% ship threshold"
    return None


if __name__ == "__main__":
    meta = prepare_environment()
    print(f"Primary metric: {meta['primary_metric']}")
    print(f"Secondary:      {meta['secondary_metric']}")
    print(f"Min runs:       {meta['min_runs']}")
