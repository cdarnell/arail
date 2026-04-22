---
title: .env.example (configuration reference)
section: docs
tags: [configuration, env, reference]
aliases: [env-vars, configuration]
source: .env.example
generated: 2026-04-22T01:03:30Z
---

# Configuration reference

Auto-generated from `.env.example`. Copy that file to `.env` and edit the values you need; the lab reads env vars at startup via `python-dotenv`.

### `LAB_NAME`

BRAND — make this lab your own. Every user-facing string (portal title, dashboard logo, activity log, status banner, wiki landing page) reads LAB_NAME at runtime. The Python package stays `oglab` so imports and the ./oglab CLI don't change, but everything the user *sees* can be rebranded with one .env edit. `./oglab setup` prompts for these on first run.

**Default:** `OGLab`

### `LAB_SHORT_NAME`

**Default:** `oglab`

### `LAB_TAGLINE`

**Default:** `"AI Lab Blueprint"`

### `OGLAB_MODE`

MODE: "airgapped" (default) or "hybrid" airgapped = local models only, zero network calls hybrid    = local first, cloud fallback allowed

**Default:** `airgapped`

### `MODEL_BACKEND`

MODEL BACKEND `./oglab setup` detects your hardware and overwrites this line with the matching backend (mlx | cuda | cpu). Ships as "cpu" so a user who pokes at imports before running setup gets a working fallback, not a KeyError. Options: mlx | cuda | cpu | airllm | aerollm | openai_compat | huggingface | openrouter | claude

**Default:** `cpu`

### `MODEL_NAME`

Model to load (varies by backend) MLX:   mlx-community/Qwen3-8B-4bit CUDA:  Qwen/Qwen3-8B CPU:   Qwen/Qwen3-8B-GGUF  (quantized via llama.cpp)

**Default:** `mlx-community/Qwen3-8B-4bit`

### `LOCAL_API_PORT`

Local inference port (for vLLM / llama.cpp server)

**Default:** `8000`

### `LAB_THEME`

LAB THEME — the lab's north-star research area. Appears in the dashboard Mission Objective card as permanent context above whatever specific goal is active. Swap it to reframe the whole lab's focus.  Default theme: make SSD-hosted model inference faster. AeroLLM is the reference implementation — every experiment either improves its throughput, reduces its memory footprint, or extends what models it can host.

**Default:** `"Making SSD-hosted model inference faster — frontier open-weight models on laptop hardware"`

### `LAB_ACTIVE_HOURS`

SCHEDULER — when the lab does light vs heavy work. active hours → SLM only, stays responsive for interactive use heavy  hours → AeroLLM experiments + full GPU burn Ranges are 24h local time. Heavy takes precedence when ranges overlap. LAB_STARTUP_DELAY_SEC is the courtesy delay on boot before the researcher's first tick, so the UI loads clean before agents start working. Set by `./oglab setup` — uncomment + edit here to override.

**Default:** `08:00-22:00`

### `LAB_HEAVY_HOURS`

**Default:** `22:00-08:00`

### `LAB_STARTUP_DELAY_SEC`

**Default:** `300`

### `LAB_PIP`

PERSONALITY AGENTS — enable / disable individual agents.  Each agent checks its env var on startup. Set to off/0/false/no to disable. Omit the var entirely (or set to any other value) to enable.  LAB_PIP        — Pip, the lab buddy. Observes and comments warmly. LAB_SRE        — SRE Watch, the crash monitor. Surfaces errors and recurrences. LAB_SRE_INTERVAL_SEC   — how often SRE ticks (default: 120) LAB_SRE_COOLDOWN_SEC   — global cooldown between alerts (default: 180)

**Default:** `on`

### `LAB_SRE`

**Default:** `on`

### `LAB_WIKI_AUTO_REBUILD`

WIKI — documentation-as-code auto-rebuild behavior.  The researcher agent and dashboard can trigger wiki recompiles. Agents typically fire several PKB writes in a row during a run, so rebuilds are debounced: the first request schedules a task, subsequent requests reset the timer, and the actual compile happens once the agent quiets down for LAB_WIKI_REBUILD_DEBOUNCE_SEC seconds.  Set LAB_WIKI_AUTO_REBUILD=false to disable auto-rebuilds entirely — the wiki only refreshes when you click Rebuild on the dashboard or run `./oglab wiki build` manually.

**Default:** `true`

### `LAB_WIKI_REBUILD_DEBOUNCE_SEC`

**Default:** `30`

### `AIRLLM_MODEL`

AIRLLM — optional layer-streaming baseline  The dashboard Deep route selector can send one message through AirLLM without switching MODEL_BACKEND for the rest of the lab.

**Default:** `meta-llama/Llama-3.1-70B`

### `AIRLLM_COMPRESSION`

**Default:** `4bit        # Options: 4bit | 8bit | none`

### `AIRLLM_MAX_LENGTH`

**Default:** `512`

### `AIRLLM_PACKAGE`

**Default:** `airllm`

### `AEROLLM_MODEL`

AEROLLM — frontier models, multi-threaded prefetched layer streaming  AeroLLM streams transformer blocks from disk with a prefetch worker that overlaps the next block's load against the current block's compute — aerodynamic, so simultaneous prompts share each layer pass instead of serializing on disk bandwidth. That's how a MacBook chats with a 235B+ model. Throughput is tokens-per-minute at that scale, not per-second — but the model itself is frontier-class, and concurrency scales near-linearly with prompt count.  Dashboard has a Deep route toggle on the chat card. It can route one message through AirLLM or AeroLLM without switching MODEL_BACKEND. Hover the FRONTIER chip in the chat card header for an AeroLLM Spec Sheet with strengths + benchmark comparisons (registry lives at src/oglab/model_specs.py — edit to add more models).  Default AeroLLM model is GLM-5.1. It is a large open-weight Z.ai/ Zhipu-family model that fits the frontier AeroLLM path better than the smaller Llama 70B default used by AirLLM.  Source: https://github.com/cdarnell/aerollm

**Default:** `zai-org/GLM-5.1`

### `AEROLLM_COMPRESSION`

**Default:** `4bit       # Options: 4bit | 8bit | none`

### `AEROLLM_MAX_LENGTH`

**Default:** `512`

### `AEROLLM_RESEARCH`

**Default:** `true          # Auto-use AeroLLM for deep research tasks`

### `OGLAB_CHAT_DEEP_DEFAULT`

**Default:** `false  # If true, the dashboard Deep route toggle starts on unless the browser already stored a preference`

### `AEROLLM_PACKAGE`

Install source. `./oglab setup` pip-installs this. AeroLLM has no PyPI release yet; installation is from the git URL below. Override to point at a branch or a local editable checkout during dev.

**Default:** `git+https://github.com/cdarnell/aerollm@main`

### `ENERGY_RATE_KWH`

COST TRACKING Simulates what equivalent cloud API calls would cost. Local energy cost = watts × time × rate.

**Default:** `0.13           # USD per kWh — US national average`

### `SIM_BILL_MONTHLY_BASE_USD`

Billing simulator knobs (dashboard spend meter): simulated spend = subscription (accrued) + billed usage overage billed usage per call = max(min_call, raw_cloud_cost * multiplier) agent calls get an extra multiplier to represent orchestration overhead.

**Default:** `20`

### `SIM_BILL_USAGE_MULTIPLIER`

**Default:** `2.0`

### `SIM_BILL_AGENT_USAGE_MULTIPLIER`

**Default:** `1.25`

### `SIM_BILL_MIN_CALL_USD`

**Default:** `0.002`

### `SIM_BILL_INCLUDE_SUBSCRIPTION`

**Default:** `true`

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
