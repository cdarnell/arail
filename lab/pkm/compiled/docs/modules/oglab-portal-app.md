---
title: app module
section: docs
tags: [python, module]
aliases: [app, app.py]
source: src/oglab/portal/app.py
generated: 2026-04-15T00:51:55Z
---

# app module

**Source:** `src/oglab/portal/app.py`

OGLab Portal — local web dashboard served at oglab.local.

## Functions

### `dashboard(request)`

### `terminal_page(request)`

### `notebook_page(request)`

### `plugins_page(request)`

### `activity_stream()`

### `activity_recent(n)`

### `set_goal(request)`

### `get_goal()`

### `research_start(request)`

### `research_pause()`

### `research_resume()`

### `research_stop()`

### `research_status()`

### `jobs_state()`

### `jobs_halt()`

### `jobs_resume()`

### `list_experiments(status)`

### `create_experiment(request)`

### `install_plugin(request)`

### `list_plugins()`

### `uninstall_plugin(name)`

### `toggle_plugin(name, request)`

### `plugin_readme(name)`

### `pending_requests()`

### `approve_request(request)`

### `deny_request(request)`

### `get_allowlist()`

### `revoke_domain(request)`

### `graph_page(request)`

### `system_graph()`

Return the full system connectivity graph with live status.

### `system_health()`

Return live system specs, resource usage, and service health.

### `system_costs()`

Return cost tracking summary — cloud-equivalent spend and energy costs.

### `addons_status()`

Probe optional compose-based add-ons (Marimo, Open Notebook).

Returns a list of add-ons with a live flag — the dashboard uses this to
light up chips when the services are running. TCP connect only; we never
hit the actual HTTP endpoints.

### `system_destroy()`

Schedule a local lab destroy from inside the running environment.

### `knowledge_page(request)`

### `api_pkm_browse()`

### `api_pkm_search(q)`

### `api_pkm_ingest()`

### `api_pkm_compile()`

### `api_pkm_file(path)`

Read a file from the PKM (relative to pkm root). Returns text content.
