---
title: goals module
section: docs
tags: [python, module]
aliases: [goals, goals.py]
source: src/oglab/goals.py
generated: 2026-04-15T11:48:11Z
---

# goals module

**Source:** `src/oglab/goals.py`

GoalStore — persists the user's current goal and history.

## Classes

### `GoalStore`

Manages the active goal and archives old ones.

**Methods:**

- `__init__(self)`
- `set_goal(self, parsed_goal)`
    - Set a new active goal.  Archives the previous one.
- `get_current(self)`
- `update_current(self, updates)`
- `link_experiment(self, exp_id)`
- `add_finding(self, finding)`
- `set_report(self, report)`
- `update_progress(self, progress)`
- `list_history(self)`
