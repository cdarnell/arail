# Experiment 001: The Science of Synchronicity

Art of the Possible

This repository folder holds a high-juice, runnable baseline: a lightweight experiment
that explores "Quantum Synchronicity" through Semantic Vector Alignment. The goal is
not metaphysics but practical demonstration — measure alignment between an expressed
Intent and a simulated stream of reality, then let a Resident Mentor (or automated
loop) refine the intent to reveal repeatable coincidences.

What you'll find
- `simulation.py` — the Vibrational Correlation engine. Contains the baseline
  `INTENT_VECTOR`, a reality-stream generator, and evaluation metrics.
- `requirements.txt` — minimal Python deps for numeric and ML utilities.
- `program.md` — instructions for the Resident Mentor to run, refine, and commit
  discoveries.

Quick start

1. Create a virtual environment and install dependencies:

   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt

2. Run the experiment:

   python simulation.py

3. Iterate: adjust the `INTENT_VECTOR` or script an AutoResearch loop to improve
   the `alignment_score` and `coincidence_count`.

Why this matters

This folder is designed to be a living laboratory for AutoResearch-driven
experiments. It provides a focused sandbox where intent, measurement, and
automated refinement come together — a place for your Resident Mentor to show
real, reproducible value.

How to Read the Vibrations
--------------------------

This experiment emits structured JSON lines prefixed with `QUANTUM_METRIC:` so
that Loki can ingest them directly. Each emitted object includes the fields:

- `alignment_score`: float in [0,1], the mean similarity between `INTENT_VECTOR` and the sampled reality stream.
- `coincidence_count`: integer, how many high-confidence matches were observed (thresholded).
- `entropy`: float, a simple entropy-like measure over the similarity distribution.
- `vibrational_frequency`: float, a derived Hz value mapped heuristically from `alignment_score`.

Dashboard mapping (Grafana):

- "Current Vibrational Alignment" (Gauge / Stat): maps to `alignment_score`.
- "Synchronicity Spikes" (TimeSeries): maps to `coincidence_count` over time.
- "System Entropy vs. Intent" (Heatmap): maps to `entropy` distribution over time.

Interpretation notes:

- A rapid spike in `coincidence_count` paired with a rising `alignment_score` indicates a
   "Quantum Event" — a moment where lab intent and observed data briefly synchronize.
- `entropy` falling while `alignment_score` rises suggests the system is clearing noise and
   focusing on coherent patterns.
- `vibrational_frequency` is provided as an easy-to-read numeric proxy for alignment and
   can be used to annotate dashboards or correlate with external events.

Kubernetes & deploy
--------------------

A sample `deployment.yaml` is provided to run the experiment as a persistent pod
(`quantum-research/deployment.yaml`). It mounts the script via a `ConfigMap`, runs
in a loop emitting structured logs, and includes `linkerd.io/inject: enabled` so the
experiment will appear in service mesh observability.

To deploy (example):

1. Switch to the feature branch: `git checkout feature/quantum-baseline`
2. Apply the manifest: `kubectl apply -f quantum-research/deployment.yaml`

Notes: the container image in the manifest uses `python:3.11-slim` and installs
runtime deps at startup (`numpy` and `scikit-learn`). For production use, build
and push a dedicated image with deps preinstalled to avoid startup delays.

