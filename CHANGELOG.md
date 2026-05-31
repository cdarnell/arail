# Changelog

All notable changes to ARAIL are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed (2026-05-31 clean-setup on macOS)

- **ai-eng now installs on a clean macOS box.** GNU `timeout(1)` is absent on
  stock macOS (it ships as `gtimeout` only after `brew install coreutils`), so
  every `timeout 900 ollama pull …` in the ai-eng install ladder failed
  instantly and setup finished with **no model installed** — breaking the
  "everyone gets ai-eng on first setup" promise for both `minimalist` and
  `maximus` tiers. Added a portable `_arail_timeout` shim that uses `timeout`,
  falls back to `gtimeout`, and (when neither exists) runs the fetch uncapped
  with a one-time warning rather than failing closed. Covered by
  `tests/setup_ladder/test_timeout_shim.py`.

### Changed (2026-05-30 re-base to 1.5B Apache-2.0)

- **ai-eng re-based onto Qwen2.5-1.5B-Instruct (Apache-2.0).** The previous
  base (Qwen2.5-3B-Instruct) was under the Qwen Research License
  (research/non-commercial), a legal conflict with ARAIL's MIT fork/redistribute
  thesis. The new base (Qwen2.5-1.5B-Instruct) is Apache-2.0 — fully
  compatible with MIT redistribution. The license blocker is cleared.
  Confirmed SPDX: `Apache-2.0` (HuggingFace API: `license:apache-2.0`).

- **ai-eng branding: 3B → 1.5B everywhere.** All user-facing and
  operator-facing strings updated: README, CLAUDE.md, pyproject.toml,
  models_catalog.yaml, docs/INSTALL.md, scripts/setup.sh, Modelfile.preview
  SYSTEM prompt, package_ai_eng.sh scaffold (now a shim; see Consolidated note below).

- **Preview base: `qwen2.5:7b` → `qwen2.5:1.5b`.** The last-resort preview
  net now pulls the 1.5B base (OOM-friendlier: ~1 GB vs ~5 GB). Aligns the
  fallback with the real production base. The `FROM` line in
  `Modelfile.preview` is updated accordingly.

- **NOTICE rewritten.** Single-section attribution for Qwen2.5-1.5B-Instruct,
  Apache-2.0. Removed the Qwen Research License non-commercial restriction
  language — it no longer applies. Redistribution section now cites
  Apache-2.0 obligations only (retain copyright/attribution + license text +
  NOTICE). The dual-section layout (3B + 7B) collapses to one entry since
  production and preview bases are now the same model family and license.

- **HF repo, GitHub release tag, and GGUF filename: `ai-eng-3b-*` → `ai-eng-1.5b-*`.**
  `pyproject.toml ai_eng_hf_repo`, `ai_eng_gh_url`, catalog `install` command,
  setup.sh defaults, and package_ai_eng.sh output names all updated (package_ai_eng.sh
  subsequently consolidated into build_ai_eng.sh publish — see 2026-05-31 entry).

### Changed

- **Maximus deep-model slot → `__TODO_DEEP_MODEL__` sentinel.** The
  Llama-3.1-70B (minimalist) and Llama-3.1-405B (maximus) AirLLM defaults
  are deprecated — they are the wrong weight class for 36 GB Apple Silicon
  (OOM or crawl on a fresh clone). The `airllm_minimalist`, `airllm_maximus`,
  and `airllm` keys in `pyproject.toml` now hold the sentinel value. Operators
  who want AirLLM layer-streaming set `AIRLLM_MODEL` explicitly in `.env`.
  Until a concrete deep model is configured, deep mode surfaces a friendly
  "configure your deep model" notice — no download, no OOM.

- **Maximus tier copy rewritten for hardware honesty.** The "Frontier-scale
  local inference, full bench" promise has been replaced with honest framing:
  the maximus tier gives you the heaviest model that runs *well* on your
  machine, with cloud frontier models one click away via the Compute Source
  pivot. The tuning page hero copy and `pyproject.toml` tier description are
  updated to match.

### Added

- **ai-eng is now self-hosted (HuggingFace primary, GitHub Release mirror).**
  Setup runs a mirror fallback ladder instead of probing the unavailable
  `ollama.ai/qukaizen/` namespace:
  1. `ollama pull hf.co/qukaizen/ai-eng-1.5b-gguf:Q4_K_M` (Ollama-native; digest
     verified by Ollama).
  2. GitHub Release HTTPS download with `sha256` verification (fail-closed
     until a real digest is pinned in `pyproject.toml ai_eng_sha256`).
  3. Optional qukaizen.com CDN mirror (set `ARAIL_AI_ENG_CDN_URL`).
  4. Last-resort preview net (existing Modelfile.preview path) until the GGUF
     is uploaded. Re-running setup after upload skips the preview net.
  All URLs/quant/digest are env-overridable (`ARAIL_AI_ENG_HF_REPO`,
  `ARAIL_AI_ENG_QUANT`, `ARAIL_AI_ENG_GH_URL`, `ARAIL_AI_ENG_CDN_URL`,
  `ARAIL_AI_ENG_SHA256`). Forks rebrand by overriding env or editing
  `pyproject.toml` — no code edits required.

- **`scripts/package_ai_eng.sh`** — developer-side scaffold that documents
  and (where tools are present) automates: LoRA merge → GGUF conversion at
  a chosen quant → emit Modelfile + NOTICE → print sha256 → print exact
  upload commands for HuggingFace / GitHub / CDN. Upload steps are
  `# TODO(manual):` blocks; no credentials are embedded; missing inputs
  print the manual steps and exit nonzero.
  **Consolidated (2026-05-31):** The scaffold body has been replaced with a thin
  deprecation shim that forwards to `scripts/build_ai_eng.sh publish`. The
  unique scaffold value (NOTICE-beside-GGUF, full sha256 + pyproject-pinning
  guidance, self-hosted upload TODO blocks, quant-tagged GGUF filename) has
  been absorbed into `build_ai_eng.py _run_publish`. See CONSOLIDATION.md.

- **`scripts/check_ai_eng_artifact.sh`** — probes the self-hosted GGUF
  (HF + GitHub, HEAD request, 8 s timeout). Exit 0 = live; exit 1 = not yet
  uploaded. Gates follow-up ticket 2b (remove Modelfile.preview + preview
  net once artifact is confirmed live).

- **`NOTICE` file** at the repo root — records the Qwen2.5-1.5B-Instruct
  (Apache-2.0) base-model license obligations (updated 2026-05-30 from the
  original 3B Qwen Research License to 1.5B Apache-2.0). States that the
  redistributed ai-eng GGUF derivative must carry this attribution on its
  HuggingFace model card and GitHub release. `LICENSE` gains a one-line
  pointer to `NOTICE`.

- **Qwen lineage moved to `NOTICE`.** Removed from user-facing copy
  (README, CLAUDE.md, catalog ai-eng description, Modelfile.preview SYSTEM
  prompt, pyproject comment, INSTALL.md). The sole permitted internal
  reference is `FROM qwen2.5:1.5b` in `Modelfile.preview` (required for the
  preview net Modelfile; class-c per ARCHITECTURE.md WC#3).

---

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

- **`ai-eng`** is the new default — a 1.5B-parameter Opus-4.7-derived AI
  engineering expert from QuKaiZen's Project Nucleus. Self-hosted GGUF
  (`hf.co/qukaizen/ai-eng-1.5b-gguf` primary, GitHub Release mirror as
  fallback).
- During the gap before the 1.5B GGUF is uploaded to the self-hosted
  hosts, setup transparently falls back to `qwen2.5:1.5b` with the AI
  Engineer persona Modelfile (`models/ai-eng/Modelfile.preview`). Once
  the GGUF is live, re-running setup picks it up automatically.
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
- Self-hosted ai-eng 1.5B GGUF may not yet be uploaded at release time —
  preview base (`qwen2.5:1.5b`) is used in the interim and the swap is
  automatic once the GGUF is live on HuggingFace or the GitHub Release
  mirror.
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
