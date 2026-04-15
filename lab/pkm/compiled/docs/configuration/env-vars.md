---
title: .env.example (configuration reference)
section: docs
tags: [configuration, env, reference]
aliases: [env-vars, configuration]
source: .env.example
generated: 2026-04-15T01:06:26Z
---

# Configuration reference

Auto-generated from `.env.example`. Copy that file to `.env` and edit the values you need; the lab reads env vars at startup via `python-dotenv`.

### `OGLAB_MODE`

MODE: "airgapped" (default) or "hybrid" airgapped = local models only, zero network calls hybrid    = local first, cloud fallback allowed

**Default:** `airgapped`

### `MODEL_BACKEND`

MODEL BACKEND (auto-detected by setup.sh, but you can override) Options: mlx | cuda | cpu | airllm | openai_compat | huggingface | openrouter | claude

**Default:** `auto`

### `MODEL_NAME`

Model to load (varies by backend) MLX:   mlx-community/Qwen3-8B-4bit CUDA:  Qwen/Qwen3-8B CPU:   Qwen/Qwen3-8B-GGUF  (quantized via llama.cpp)

**Default:** `mlx-community/Qwen3-8B-4bit`

### `LOCAL_API_PORT`

Local inference port (for vLLM / llama.cpp server)

**Default:** `8000`

### `LAB_ACTIVE_HOURS`

SCHEDULER — when the lab does light vs heavy work. active hours → SLM only, stays responsive for interactive use heavy  hours → AirLLM experiments + full GPU burn Ranges are 24h local time. Heavy takes precedence when ranges overlap. LAB_STARTUP_DELAY_SEC is the courtesy delay on boot before the researcher's first tick, so the UI loads clean before agents start working. Set by `./oglab setup` — uncomment + edit here to override.

**Default:** `08:00-22:00`

### `LAB_HEAVY_HOURS`

**Default:** `22:00-08:00`

### `LAB_STARTUP_DELAY_SEC`

**Default:** `300`

### `LAB_WIKI_AUTO_REBUILD`

WIKI — documentation-as-code auto-rebuild behavior.  The researcher agent and dashboard can trigger wiki recompiles. Agents typically fire several PKM writes in a row during a run, so rebuilds are debounced: the first request schedules a task, subsequent requests reset the timer, and the actual compile happens once the agent quiets down for LAB_WIKI_REBUILD_DEBOUNCE_SEC seconds.  Set LAB_WIKI_AUTO_REBUILD=false to disable auto-rebuilds entirely — the wiki only refreshes when you click Rebuild on the dashboard or run `./oglab wiki build` manually.

**Default:** `true`

### `LAB_WIKI_REBUILD_DEBOUNCE_SEC`

**Default:** `30`

### `AIRLLM_MODEL`

AIRLLM  (deeper async work — smaller open model compressed from disk) Set MODEL_BACKEND=airllm or let the researcher agent use it automatically.

**Default:** `Qwen/Qwen3-8B`

### `AIRLLM_COMPRESSION`

**Default:** `4bit       # Options: 4bit | 8bit | none`

### `AIRLLM_MAX_LENGTH`

**Default:** `512`

### `AIRLLM_RESEARCH`

**Default:** `true           # Auto-use AirLLM for deep research tasks`

### `ENERGY_RATE_KWH`

COST TRACKING Simulates what equivalent cloud API calls would cost. Local energy cost = watts × time × rate.

**Default:** `0.13           # USD per kWh — US national average`

### `PORTAL_PORT`

SERVICE PORTS (also configurable in lab.conf)

**Default:** `8080`

### `TERMINAL_PORT`

**Default:** `7681`

### `NOTEBOOK_PORT`

**Default:** `8888`

### `IDE_PORT`

**Default:** `8443`

### `MARIMO_PORT`

ADD-ON SERVICES (opt-in, via compose/ overlays) docker compose -f compose/marimo.yml up -d docker compose -f compose/open-notebook.yml up -d

**Default:** `2718`

### `OPEN_NOTEBOOK_PORT`

**Default:** `8502`

### `OPEN_NOTEBOOK_API_PORT`

**Default:** `5055`
