---
title: .env.example (configuration reference)
section: docs
tags: [configuration, env, reference]
aliases: [env-vars, configuration]
source: .env.example
generated: 2026-04-25T04:17:15Z
---

# Configuration reference

Auto-generated from `.env.example`. Copy that file to `.env` and edit the values you need; the lab reads env vars at startup via `python-dotenv`.

### `LAB_NAME`

BRAND — name this lab whatever you want.  Every visible surface (portal title, nav logo, activity log, status banners, setup screen, wiki landing) reads LAB_NAME at runtime. The Python package name stays `arail` so imports and the CLI don't break, but everything the operator *sees* rebrands from one .env edit.  Default is "Autoresearch AI Lab". Rename to make it yours, e.g.: LAB_NAME="Sam's AI Lab" LAB_NAME="gentoofoo's ai lab" LAB_NAME="PeanutLab"

**Default:** `"Autoresearch AI Lab"`

### `LAB_SHORT_NAME`

**Default:** `autoresearch-lab`

### `LAB_TAGLINE`

**Default:** `"A learn-by-doing AI research lab"`

### `LAB_TIER`

INSTALL TIER — set by `./arail setup`; determines which tabs appear.  min  → Dashboard, Chat, Autoresearch, Knowledge Base, Agents The everyday lab. KB runs on markdown + keyword search. External providers (Claude / NVIDIA / OpenRouter / HF) still work here when LAB_MODE=hybrid — they just use plain HTTP, no SDK. max  → + Admin, Notebooks, LanceDB vectors, AeroLLM frontier streaming, official Anthropic SDK, LangChain + LangGraph.  Upgrade later with: ./arail upgrade max

**Default:** `min`

### `LAB_MODE`

MODE: "airgapped" (default) or "hybrid" airgapped = local models only, no network calls hybrid    = local first, cloud fallback allowed (needs API keys below)

**Default:** `airgapped`

### `COMPUTE_SOURCE`

DEFAULT COMPUTE SOURCE (the Chat tab lets you pivot live without editing this)  Options: my_machine | claude | nvidia | openrouter | huggingface | custom my_machine  → local MLX / CUDA / CPU — no key needed claude      → Anthropic API          — needs ANTHROPIC_API_KEY nvidia      → NVIDIA NIM             — needs NVIDIA_API_KEY openrouter  → OpenRouter             — needs OPENROUTER_API_KEY huggingface → HF Inference API       — needs HF_TOKEN custom      → any OpenAI-compatible endpoint (set MODEL_API_BASE)

**Default:** `my_machine`

### `MODEL_BACKEND`

MODEL BACKEND (for the my_machine compute source) `./lab setup` detects your hardware and writes the matching backend. Options: mlx | cuda | cpu | airllm | aerollm | openai_compat | huggingface | openrouter | claude

**Default:** `cpu`

### `MODEL_NAME`

**Default:** `mlx-community/Qwen3-8B-4bit`

### `LOCAL_API_PORT`

**Default:** `8000`

### `LAB_INTENT`

AGENT INTENT — the domain context the researcher thinks in. Options: ai | farming | ml | business | education | health | culinary

**Default:** `ai`

### `LAB_INTENT_NAME`

**Default:** `"AI Engineer"`

### `LAB_THEME`

LAB THEME — the north-star research area. Shows in the Mission Objective card above whatever specific goal is active.

**Default:** `"Making SSD-hosted model inference faster — frontier open-weight models on laptop hardware"`

### `LAB_ACTIVE_HOURS`

SCHEDULER — when the lab does light vs heavy work. active hours → small-model chat, stays responsive heavy  hours → long-running experiments, GPU burn

**Default:** `08:00-22:00`

### `LAB_HEAVY_HOURS`

**Default:** `22:00-08:00`

### `LAB_STARTUP_DELAY_SEC`

**Default:** `300`

### `LAB_PIP`

PERSONALITY AGENTS (med/max tiers) LAB_PIP — warm lab buddy. Observes and comments. LAB_SRE — crash monitor. Surfaces errors and recurrences.

**Default:** `on`

### `LAB_SRE`

**Default:** `on`

### `LAB_WIKI_AUTO_REBUILD`

WIKI — documentation-as-code auto-rebuild behavior.

**Default:** `true`

### `LAB_WIKI_REBUILD_DEBOUNCE_SEC`

**Default:** `30`

### `AIRLLM_MODEL`

AIRLLM — the lab's deep layer-streaming backend (active in both tiers). Llama 3.1 70B by default; max-tier setup bumps this to 405B automatically. Keep AIRLLM_MODEL on a Llama-family repo — AirLLM is most reliable there.

**Default:** `meta-llama/Llama-3.1-70B`

### `AIRLLM_COMPRESSION`

**Default:** `4bit`

### `AIRLLM_MAX_LENGTH`

**Default:** `512`

### `AIRLLM_PACKAGE`

**Default:** `airllm`

### `LAB_SHOW_AEROLLM`

AEROLLM — dormant in the blueprint. The Rust runtime is in development; the AeroLLMBackend class is still wired in code so you can flip back when it's ready. Two switches: LAB_SHOW_AEROLLM=1   → expose the AeroLLM tabs on the Tuning page. AEROLLM_RESEARCH=true → the researcher uses AeroLLM for deep-thinking calls (requires the package + AEROLLM_MODEL set).

**Default:** `false`

### `AEROLLM_MODEL`

**Default:** `zai-org/GLM-5.1`

### `AEROLLM_COMPRESSION`

**Default:** `4bit`

### `AEROLLM_MAX_LENGTH`

**Default:** `512`

### `AEROLLM_RESEARCH`

**Default:** `false`

### `LAB_CHAT_DEEP_DEFAULT`

**Default:** `false`

### `ENERGY_RATE_KWH`

COST TRACKING — simulates equivalent cloud costs so you can compare.

**Default:** `0.13`

### `SIM_BILL_MONTHLY_BASE_USD`

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

SERVICE PORTS

**Default:** `8080`

### `TERMINAL_PORT`

**Default:** `7681`

### `NOTEBOOK_PORT`

**Default:** `8888`

### `IDE_PORT`

**Default:** `8443`

### `MARIMO_PORT`

ADD-ON SERVICES (opt-in, max tier) docker compose -f compose/marimo.yml up -d docker compose -f compose/open-notebook.yml up -d

**Default:** `2718`

### `OPEN_NOTEBOOK_PORT`

**Default:** `8502`

### `OPEN_NOTEBOOK_API_PORT`

**Default:** `5055`
