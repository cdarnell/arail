---
title: __init__ module
section: docs
tags: [python, module]
aliases: [__init__, __init__.py]
source: src/oglab/skills/experiment_tracker/__init__.py
generated: 2026-04-15T00:51:55Z
---

# __init__ module

**Source:** `src/oglab/skills/experiment_tracker/__init__.py`

Experiment Tracker — hypothesis → test → result lifecycle.

## Classes

### `ExperimentTracker`

**Methods:**

- `__init__(self, experiments_dir)`
- `create(self, hypothesis, methodology, variables, duration_days, metrics, domain)`
- `start(self, exp_id)`
- `observe(self, exp_id, observation, data)`
- `complete(self, exp_id, results, conclusion, success)`
- `list_all(self, status)`
