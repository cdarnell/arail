---
title: scheduler module
section: docs
tags: [python, module]
aliases: [scheduler, scheduler.py]
source: src/oglab/scheduler.py
generated: 2026-04-15T00:51:55Z
---

# scheduler module

**Source:** `src/oglab/scheduler.py`

OGLab scheduler — time windows + a global halt flag.

Two concepts:

1. **Window** — active / heavy / idle, derived from `LAB_ACTIVE_HOURS`
   and `LAB_HEAVY_HOURS` in the environment. Default: active 08:00-22:00,
   heavy 22:00-08:00 (so the GPU hammers while you sleep).
2. **Halt flag** — a process-wide boolean that agents poll. Setting it
   via :func:`halt_all_jobs` cancels in-flight work without tearing down
   the portal itself (that's :func:`oglab stop`).

The scheduler is deliberately simple: no cron, no DAG, no wake-up
callbacks. Agents are responsible for calling :func:`current_window`
and :func:`jobs_halted` at their own tick points.

## Classes

### `HourRange`

**Methods:**

- `contains(self, now)`

## Functions

### `current_window(now)`

Return the current window. Heavy takes precedence over active
when ranges overlap; anything outside both is 'idle'.

### `window_label(w)`

Human-friendly label for the dashboard mode indicator.

### `startup_delay_seconds()`

How long agents should wait on boot before their first tick.

### `jobs_halted()`

### `halt_all_jobs()`

Flip the halt flag. Agents poll this and abort their current tick.

### `resume_all_jobs()`

### `state()`

Serializable snapshot for the portal's /api/jobs/state endpoint.
