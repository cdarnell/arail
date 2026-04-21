"""
Canvas integration hooks for other lab skills.

Each module here adds one line to an existing skill to wire it into
the canvas:

  from_curator.py      - Data Curator writes discovered sources in
  from_experiments.py  - Experiment Tracker writes results in
  for_insights.py      - Insight Generator reads sources out

This pattern keeps the canvas opt-in per skill. If you fork the lab
and don't want the canvas, delete this directory and the `canvas.*`
calls in the skills — nothing else breaks.
"""
from core.knowledge_canvas.integrations.from_curator import pipe_to_canvas
from core.knowledge_canvas.integrations.from_experiments import pipe_experiment
from core.knowledge_canvas.integrations.for_insights import (
    gather_evidence,
    cross_source_patterns,
)

__all__ = [
    "pipe_to_canvas",
    "pipe_experiment",
    "gather_evidence",
    "cross_source_patterns",
]
