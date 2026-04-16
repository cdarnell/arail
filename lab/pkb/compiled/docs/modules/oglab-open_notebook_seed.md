---
title: open_notebook_seed module
section: docs
tags: [python, module]
aliases: [open_notebook_seed, open_notebook_seed.py]
source: src/oglab/open_notebook_seed.py
generated: 2026-04-16T11:07:31Z
---

# open_notebook_seed module

**Source:** `src/oglab/open_notebook_seed.py`

Seed Open Notebook with lab content on first boot.

Reads the PKB (research reports, experiments, docs) and creates
pre-populated notebooks so users see value immediately — not a blank
slate.  Idempotent: skips seeding if notebooks already exist.

Called from the portal after ``docker compose up`` finishes.

## Functions

### `seed(port)`

Main entry point.  Returns a summary dict.
