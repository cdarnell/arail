---
title: app module
section: docs
tags: [python, module]
aliases: [app, app.py]
source: src/oglab/portal/app.py
generated: 2026-04-19T13:28:23Z
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

### `notebooks_page(request)`

Picker page — three cards (Jupyter / Marimo / Open Notebook).

All state is pulled client-side from /api/notebooks/status, so this
route is a pure template render.

### `notebooks_status()`

One-shot liveness probe for every notebook surface.

Drives the picker page's status dots. Checks:
  - Jupyter: ``jupyter`` binary on PATH + TCP probe on NOTEBOOK_PORT.
  - Marimo: Docker available + oglab-marimo container running.
  - Open Notebook: Docker available + oglab-open-notebook container running.

### `marimo_page(request)`

3-state Marimo page: docker missing / not running / running.

When running, shows the Marimo iframe with the token baked into the
URL (same ``?access_token=<OGLAB_PASSWORD>`` contract Marimo itself
prints on startup). When not running, shows a one-click Start button
that calls /api/marimo/start.

### `marimo_start()`

Bring up the Marimo container via docker compose.

### `marimo_stop()`

Tear down the Marimo container.

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

### `research_files()`

List the research program files + any human-authored notes.

``files`` = the two curated contract files (program.md, prepare.py).
``notes`` = every other markdown file dropped under
lab/pkb/research/ — humans can leave references, observations,
cost budgets, and the researcher reads them via the wiki.

### `research_file(name)`

Read a research file.

Accepts the two curated files (prepare.py, program.md) OR any
.md note that lives directly under lab/pkb/research/. Rejects
anything with a path separator to prevent traversal.

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

### `admin_page(request)`

Lab administration — services, components, updates, help.

### `agents_page(request)`

Agent Control Center — monitor, instruct, and inspect all agents.

### `agents_status()`

Aggregated status of all three agents.

### `agents_prompts(agent, limit)`

Return recent prompt-trace events for the Prompt Inspector.

### `agents_instruct(request)`

Send an ad-hoc instruction to an agent.

### `api_skills_list()`

Return every installed skill so the Forge can show toggles.

### `api_agents_list()`

Return the agents the loader currently knows about.

### `api_agents_forge(request)`

Deploy a new agent from a Forge form submission.

Body shape::

    {
      "name": "Owl",
      "emoji": "🦉",
      "voice": "Wise, patient, long view.",
      "tick_interval_sec": 120,
      "global_cooldown_sec": 600,
      "dream": true,
      "skills": ["observe-lab", "falsify-hypothesis"],
      "role": "research pacer"
    }

Returns the forge deployment status dict — see ``forge.deploy``.

### `api_agents_forge_preview(name, emoji, voice, tick, cooldown, dream, skills)`

Server-side preview of what Deploy would write.

Takes the same fields as /api/agents/forge but via querystring
and returns the generated AGENT.md + .py as strings — used by
the UI for the right-panel preview when the user wants a
canonical mirror of what the backend will generate.

### `admin_components()`

Read components.json and resolve current versions.

### `admin_check_updates()`

Quick remote update check for all components.

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
      "history": [{"role": "user"|"assistant", "content": "..."}],
      "backend": "aerollm" (optional),
      "model": "model-name" (optional, network backends only),
      "temperature": 0.7, "top_p": 0.9, "max_tokens": 512
    }

Response JSON: see ``_run_chat_completion`` for shape. Errors are
returned as a well-formed dict with ``error`` set — never raised.

### `api_aerollm_bench()`

Return aggregated AeroLLM throughput stats per model.

Shape::

    {
      "bench": {
        "Qwen/Qwen3-235B-A22B": {
          "runs": 4,
          "avg_tokens_per_sec": 0.17,
          "avg_tokens_per_min": 10.2,
          "median_latency_ms": 582340,
          "total_tokens": 248,
          "last_ts": "2026-04-18T14:02:11Z"
        }
      },
      "total_runs": 4,
      "platform": "Darwin 25.4.0 arm64"
    }

### `api_chat_models()`

Return the model catalog for the current backend.

For OpenAI-compatible backends (LM Studio, Ollama, NVIDIA NIM,
OpenRouter), we query the server's ``/v1/models`` endpoint and
list every model it advertises. For single-model backends
(MLX, llama.cpp, AeroLLM, Claude, HF Inference), we return just
the configured ``MODEL_NAME`` so the dropdown still renders.

The dashboard Tuning row uses this to populate its Model picker.

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

Probe optional compose-based add-ons.

Marimo and Open Notebook moved to /api/notebooks/status when the
/notebooks picker landed — this endpoint stays as an empty-but-live
contract for future non-notebook add-ons (ComfyUI, vector DBs, etc.).

### `system_destroy()`

Schedule a local lab destroy from inside the running environment.

### `knowledge_page(request)`

### `browse_url_endpoint(request)`

Browse a URL via agent-browser, capture screenshot + text.

### `browse_chat_endpoint(request)`

Natural-language browser task via agent-browser chat.

### `browse_suggestions()`

Generate goal-driven browse suggestions from credible sources.

### `browse_file(path)`

Serve a browser agent capture (screenshot or extract).

### `api_pkb_browse()`

### `api_pkb_search(q)`

### `api_pkb_ingest()`

### `api_pkb_compile()`

### `api_pkb_seeds()`

List starter packs + installed status.

Drives the dashboard Knowledge hero + /knowledge Install button.

### `api_pkb_seed(request)`

Install (or re-install) a starter pack.

Body: ``{"pack": "model-building", "force": false}``.
Idempotent unless ``force=true``; missing files are filled in,
user-edited files stay put (they only get overwritten on force).

### `api_pkb_upload_url(request)`

Append a URL to sources/bookmarks.md.

The existing ingest pipeline accepts URLs via ``inbox/links.txt``;
this is the one-shot HTTP equivalent the Knowledge ingest-hero
"URL" tile calls when a user types a link.

### `api_pkb_recent(n)`

Return the N most recently modified files across the PKB.

Drives the dashboard Knowledge hero's "Recently added" list.

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

### `tuning_page(request)`

### `api_tuning_config(backend)`

Return the hydrated tuning config for the selected backend.
Safe to poll.

### `api_tuning_runs(backend, limit)`

Return recent bench rows with git context for the selected
backend. Enriches each row with a `diff_url` pointing at GitHub
if a remote is configured.

### `api_tuning_baseline(backend)`

Run the benchmark `bench_runs_per_config` times on the current
HEAD and persist the median into the backend's tuning config as
the new baseline. Runs synchronously in a worker thread — expect
a long response for big models. The page shows a spinner during this.

We allow this without the autoresearch env flag because it
doesn't create branches or new commits, just a baseline snapshot.

### `api_tuning_autoresearch_start(backend)`

Kick off the full autoresearch loop in a background task for
the selected backend. Returns immediately; poll /status?backend=
for progress.

### `api_tuning_autoresearch_status(backend)`

### `api_tuning_autoresearch_start_forever(backend)`

Kick off the continuous supervisor for the selected backend —
sweeps every candidate, pauses, sweeps again, forever, until /stop
is called. Returns immediately; poll /status for progress +
pass_number.

### `api_tuning_autoresearch_stop(backend)`

Signal the continuous supervisor for the selected backend to
stop after the current pass. Safe to call whether or not a loop
is running.

### `api_tuning_autoresearch_schedule_get()`

Return the persisted schedule + live status (allowed_now, next
open time). Safe to poll; cheap (one JSON read from disk).

### `api_tuning_autoresearch_schedule_set(request)`

Update the schedule. Body shape:
    {"mode": "anytime"|"window"|"paused",
     "window_start": "HH:MM", "window_end": "HH:MM"}
Invalid values are coerced to defaults rather than rejected so the
UI never has to choreograph error handling.

### `teacher_page(request)`

### `api_teacher_ask(request)`

One consultation with the Deep Teacher. Forces backend=aerollm so
the user never accidentally hits the fast path from this surface.
Saves the Q&A to PKB on success.

### `api_teacher_history(limit)`

Return recent Teacher consultations from lab/pkb/teacher/, newest
first. Files are small (one Q&A each) and there will rarely be more
than a few dozen, so we just read them all and sort.
