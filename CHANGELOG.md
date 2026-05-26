# Changelog

All notable changes to ARAIL are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **`aerollm-api` declared as an install dependency** on Apple Silicon
  (2026-05-25). The `AeroLLMBackend` in [`src/arail/router/backends.py`](src/arail/router/backends.py)
  has shipped since v1.0.0, but the wheel was never pulled in by `pip` —
  users had to build it manually with `maturin develop`. With aeroLLM
  publishing `aerollm-api 0.1.0rc2` to PyPI (the first wheel with the
  native Qwen3-MoE backend, the `score()` teacher-forcing API, and the
  honest decode-tokens/sec metric), the dep can be declared properly.

  Wired in two extras:
  - `maximus` (and the legacy `max` alias) — fulfills the existing tier
    description ("Adds AeroLLM as the deep-mode runtime"); the dep was
    missing.
  - `aero` — granular extra so the runtime can be added to a minimalist
    install without pulling JupyterLab + LangChain.

  Platform-gated to `sys_platform == 'darwin' and platform_machine == 'arm64'`
  per PEP 508 markers — the published wheel is `macosx_11_0_arm64` only
  (CUDA backend is scaffolded but not built; ADR 0006). On Linux/x86
  hosts the dep is silently skipped and `AeroLLMBackend` raises a clear
  `ImportError` (with build instructions) if a user invokes it.

  Closes the consumer side of aeroLLM's "ARAIL chat path via published
  wheel" GA gate. After `pip install -e ".[maximus]"`, `aerollm` is a
  live backend choice with no manual build step.

## [1.0.0] — 2026-05-17

The first stable release of ARAIL. A learn-by-doing AI research lab
you can clone, set up in 12 minutes, and run on a laptop.

### Tiers (renamed)

- **Minimalist** (default) — Dashboard, Chat, Autoresearch, Knowledge
  Base, Agents, Docs. Ships `ai-eng` as the only local model.
- **Maximus** — Everything in Minimalist + Admin, Notebooks,
  LangChain/LangGraph, Anthropic SDK, full cloud catalog. Adds AeroLLM
  as the deep-mode runtime.
- Tiers were previously called `min`/`max`. Existing `.env` values are
  auto-migrated with a deprecation warning; the compat shim is removed
  in v1.1.0.
- Upgrade with `./arailctl upgrade maximus`; downgrade with
  `./arailctl upgrade minimalist` (hides the extra tabs without
  uninstalling packages).

### Default model

- **`ai-eng`** is the new default — a 3B-parameter Opus-4.7-derived AI
  engineering expert from QuKaiZen's Project Nucleus.
- During the gap before QuKaiZen publishes the 3B weights, setup
  transparently falls back to `qwen2.5:7b` with the AI Engineer persona
  Modelfile (`models/ai-eng/Modelfile.preview`). Once
  `qukaizen/ai-eng:3b` is available on Ollama, re-running setup picks it
  up automatically via `models/ai-eng/Modelfile.production`.
- **No other models auto-install.** The chat catalog (~20 entries) stays
  as a browse-and-pull gallery — only `ai-eng` is `tier: recommended`;
  everything else is `tier: optional` or `tier: flagship`.

### Deep backends

- **AeroLLM** is the Maximus deep-mode runtime. Apple Silicon: native.
  CUDA hosts: AeroLLM is preferred when its CUDA backend lands; until
  then AirLLM serves as a fallback (with a clear log notice). Set
  `ARAIL_FORCE_AEROLLM=1` to disable the fallback.
- **AirLLM is now opt-in.** Removed from the default install path in
  both tiers. Power users on CUDA/Linux who want layer-streaming
  inference for 70B/405B models can enable it with
  `ARAIL_INSTALL_AIRLLM=1 ./arailctl setup`.
- Minimalist tier installs NO deep backend by default — chat with
  ai-eng works fine without one. The deep backend is a Maximus
  escalation.

### Surfaces

- All Minimalist surfaces (Dashboard, Chat, Autoresearch, Knowledge
  Base, Agents) are stable.
- Maximus adds Admin, Notebooks, Tuning, Plugins, Terminal.
- Compute Source pivot in Chat: switch between My Machine and any cloud
  provider with one click. Tokens stored 0600 in `lab/data/secrets.env`,
  git-ignored, never echoed.

### Security

- `LAB_MODE=airgapped` remains the default. All cloud egress blocked;
  audit log in `lab/data/airgap_audit.jsonl`.
- Set `LAB_MODE=hybrid` to enable cloud providers.

### Other improvements

- Energy cost tracking now uses `max(latency_energy, token_energy)` so
  layer-streaming backends are no longer undercounted
  (`src/arail/costs.py`).
- Dashboard meter bars: CSS polish + expandable experiments
  (`src/arail/portal/templates/dashboard.html`).
- Docs frontmatter schema migration across
  `lab/pkb/compiled/docs/guides/`.
- README typo fix: `minamalist`/`maximum` → `Minimalist`/`Maximus`.

### Known limitations

- AeroLLM CUDA backend not yet shipped. CUDA Maximus hosts fall back
  to AirLLM with a clear warning until AeroLLM CUDA lands.
- `qukaizen/ai-eng:3b` may not yet be on the public Ollama registry at
  release time — preview base (`qwen2.5:7b`) is used in the interim and
  the swap is automatic once the production tag publishes.
- `/ready` and `/version` standard-compliance endpoints not implemented
  (`/health` and `/api/system/health` cover the diagnostic surface).
- One TODO in `src/arail/router/backends.py` for runtime profiling —
  non-blocking, scheduled for v1.1.0.

### Removed

- AirLLM from default install path — opt-in via
  `ARAIL_INSTALL_AIRLLM=1`.
- Auto-pull of Qwen3-8B / Llama-3.1-70B / Llama-3.1-405B starter
  models — the catalog lists them for on-demand install.
- Legacy `models/ai-engineer/` directory — replaced by
  `models/ai-eng/Modelfile.{production,preview}`.

### Migration guide

- **From a pre-1.0 install**: pull, then re-run `./arailctl setup`. The
  compat shim handles `LAB_TIER=min`/`LAB_TIER=max` automatically. The
  old `ai-engineer` Ollama model is left in place (remove manually with
  `ollama rm ai-engineer` once the new `ai-eng` works).
- **Existing forks** that read `[tool.arail.tiers].min` /
  `[tool.arail.models].airllm_min` from `pyproject.toml`: the
  `minimalist` / `airllm_minimalist` keys are now canonical, with the
  old keys kept as aliases for one release.

[1.0.0]: https://github.com/qukaizen/arail/releases/tag/v1.0.0
