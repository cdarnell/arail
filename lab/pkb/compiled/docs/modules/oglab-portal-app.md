---
title: app module
section: docs
tags: [python, module]
aliases: [app, app.py]
source: src/oglab/portal/app.py
generated: 2026-04-16T11:30:32Z
---

# app module

**Source:** `src/oglab/portal/app.py`

OGLab Portal — local web dashboard served at oglab.local.

## Functions

### `dashboard(request)`

### `terminal_page(request)`

Serve the terminal iframe if ttyd is running, otherwise show
install help so the user can get unblocked without leaving the UI.

### `notebook_page(request)`

Serve the Jupyter Lab iframe if jupyter is running, otherwise
show install help. Same three-state pattern as /terminal so the
two services feel consistent.

### `notebook_start()`

Start Jupyter Lab as a background process.

### `notebook_stop()`

Stop any Jupyter Lab process listening on the notebook port.

### `open_notebook_page(request)`

First-class page for Open Notebook — 3-state UI like terminal/notebook.

### `open_notebook_start()`

Bring up Open Notebook via docker compose, then seed with lab content.

### `open_notebook_stop()`

Tear down Open Notebook containers.

### `plugins_page(request)`

### `research_page(request)`

Research cockpit — goal + experiments + live researcher activity.

All the live state is populated client-side via /api/goal,
/api/experiments, /api/research/status, and the SSE activity stream.
The page just needs to render an empty shell.

### `activity_stream()`

### `activity_recent(n)`

### `set_goal(request)`

### `get_goal()`

### `research_start(request)`

### `research_pause()`

### `research_resume()`

### `research_stop()`

### `research_reset()`

Stop research and clear the current goal (archives it).

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

### `api_brand()`

Return the current brand (name, tagline, logo, version).
Lets dashboard JS personalize UI strings without hardcoding.

### `api_chat(request)`

Send one user message to the local model with full lab context.

Request JSON:
    {
      "message": "What commands can I run?",
      "history": [{"role": "user"|"assistant", "content": "..."}]
    }

Response JSON:
    {
      "reply": "…",
      "backend": "mlx",
      "latency_ms": 245.3,
      "tokens_used": 118,
      "error": null
    }

### `api_chat_system_prompt()`

Return the currently-rendered system prompt.

Useful for debugging, for transparency ("what does the model know?"),
and for the upcoming lab-tutor feature where the user can inspect and
edit the prompt before sending a goal.

### `system_health()`

Return live system specs, resource usage, and service health.

### `get_mode()`

### `set_mode(request)`

Toggle between airgapped and hybrid mode.  Writes to .env and
updates the running process environment.

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

### `api_pkb_browse()`

### `api_pkb_search(q)`

### `api_pkb_ingest()`

### `api_pkb_compile()`

### `api_pkb_file(path)`

Read a file from the PKB (relative to pkb root). Returns text content.

### `api_pkb_raw(path)`

Serve a PKB file as raw bytes with the correct Content-Type.

Used by the knowledge viewer to render images (PNG/JPG/…) and PDFs
inline. Text files fall through to the existing ``/api/pkb/file``
JSON endpoint, so raw is strictly for binary + image surfaces.

Path is sanitized the same way every other PKB endpoint does it
(no traversal, must resolve inside the PKB root).

### `api_pkb_file_save(request)`

Save (or create) a text file under the PKB root.

Body: ``{"path": "notes/foo.md", "content": "...new body..."}``
Returns: ``{"path", "size", "bytes_written"}`` or ``{"error"}``

### `api_pkb_file_delete(path)`

Delete a file under the PKB root. No directory removal — files only.

### `api_pkb_upload(request)`

Accept multipart file uploads and drop them into ``lab/pkb/inbox/``.

Form fields:
  * ``files``: one or more file parts (multipart/form-data)
  * ``auto_ingest``: ``"true"`` (default) runs ``pkb.ingest()`` after
    the files land so they get sorted into ``sources/`` immediately.

Returns ``{uploaded: N, paths: [...], ingest: {moved, errors}}``.

### `api_pkm_browse_legacy()`

### `api_pkm_search_legacy(q)`

### `api_pkm_ingest_legacy()`

### `api_pkm_compile_legacy()`

### `api_pkm_file_legacy(path)`
