---
title: .env.example (configuration reference)
section: docs
tags: [configuration, env, reference]
aliases: [env-vars, configuration]
source: .env.example
generated: 2026-05-17T19:56:29Z
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

INSTALL TIER — set by `./arailctl setup`; determines which tabs appear.  minimalist → Dashboard, Chat, Autoresearch, Knowledge Base, Agents, Docs The everyday lab. Ships ai-eng (a 3B Opus-4.7-derived AI engineering expert from QuKaiZen's Project Nucleus) as the only default model. External providers (Claude / NVIDIA / OpenRouter / HF) still work when LAB_MODE=hybrid — they just use plain HTTP, no SDK. maximus    → + Admin, Notebooks, AeroLLM deep-mode streaming, official Anthropic SDK, LangChain + LangGraph, full cloud catalog.  Legacy `min`/`max` values are auto-migrated with a deprecation warning (compat shim removed in v1.1.0).  Upgrade later with: ./arailctl upgrade maximus

**Default:** `minimalist`

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

### `LAB_BUDDY`

PERSONALITY AGENTS (maximus tier) LAB_BUDDY — ARAIL's lab partner. Observes the lab AND offers goal- aware suggestions (techniques, reviews, runs) on a slow cadence. LAB_SRE   — crash monitor. Surfaces errors and recurrences.  Buddy tuning (optional): LAB_BUDDY_INTERVAL_SEC          — watcher tick (default 90) LAB_BUDDY_GLOBAL_COOLDOWN_SEC   — silence after any utterance (default 300) LAB_BUDDY_SUGGEST_INTERVAL_SEC  — proactive cadence (default 900 = 15 min)

**Default:** `on`

### `LAB_SRE`

**Default:** `on`

### `LAB_WIKI_AUTO_REBUILD`

WIKI — documentation-as-code auto-rebuild behavior.

**Default:** `true`

### `LAB_WIKI_REBUILD_DEBOUNCE_SEC`

**Default:** `30`

### `AIRLLM_MODEL`

AIRLLM — optional deep layer-streaming backend (opt-in as of v1.0.0). Power users on CUDA/Linux can enable with: ARAIL_INSTALL_AIRLLM=1. Not installed by default in either tier; AeroLLM is the canonical deep backend for the Maximus tier.

**Default:** `meta-llama/Llama-3.1-70B`

### `AIRLLM_COMPRESSION`

**Default:** `4bit`

### `AIRLLM_MAX_LENGTH`

**Default:** `512`

### `AIRLLM_PACKAGE`

**Default:** `airllm`

### `LAB_SHOW_AEROLLM`

AEROLLM — Arail's Rust runtime; the deep-mode backend for the Maximus tier. Apple Silicon: native. CUDA hosts: fall back to AirLLM with a notice until AeroLLM's CUDA backend ships. Switches: AEROLLM_MODEL          → directory under ARAIL_MODELS_DIR or absolute path. Default Qwen2.5-7B-4bit (~4 GB resident, fits 16 GB Macs). Operators can override in .env. AEROLLM_KV_BUDGET_PCT  → KV cache as a fraction of system RAM. 0.60 leaves headroom for portal + browser. Unset → aerollm auto-detects (80%) which is too aggressive for a box also running the lab UI. AEROLLM_DRAFT_MODEL    → optional speculative-decoding draft (path or name). AEROLLM_RING_DEPTH     → cap resident transformer-block weight slots (mlx-native only). 0 / unset → no eviction. LAB_SHOW_AEROLLM=1     → surface AeroLLM tabs on the Tuning page. AEROLLM_RESEARCH=true  → researcher agent uses AeroLLM for deep calls. ARAIL_FORCE_AEROLLM=1  → disable AirLLM fallback on CUDA (fail loud if AeroLLM CUDA backend is not yet available).

**Default:** `true`

### `AEROLLM_MODEL`

**Default:** `Qwen2.5-7B-Instruct-4bit`

### `AEROLLM_KV_BUDGET_PCT`

**Default:** `0.60`

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

ADD-ON SERVICES (opt-in, maximus tier) docker compose -f compose/marimo.yml up -d docker compose -f compose/open-notebook.yml up -d

**Default:** `2718`

### `OPEN_NOTEBOOK_PORT`

**Default:** `8502`

### `OPEN_NOTEBOOK_API_PORT`

**Default:** `5055`
