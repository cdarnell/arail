# Changelog

All notable changes to ARAIL are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added (2026-07-28 concurrent Worlds — run more than one lab at once)

- **`./arailctl start --world <slug>`** launches a World as its OWN process,
  rooted at `lab/instances/<slug>/`, on its own portal + memory-service
  ports (allocated once, pinned forever after — `:8090`, `:8100`, …),
  sharing only the machine's model weights and the Ollama daemon. Up to
  `LAB_MAX_INSTANCES` (default 3) run side by side; a second `start` for
  a running World attaches (prints its URL, opens the browser) instead of
  respawning or silently dying. Bare `./arailctl start` with 2+ Worlds
  configured shows an interactive picker (including the root lab); with
  0 or 1 World it behaves exactly as before.
- **`./arailctl status`** now leads with a registry-driven instance table
  (`--json` for scripts, `--probe` to also check each instance is
  answering from the checkout its registry record claims — catches a
  crash-looped daemon serving stale code from a different checkout).
  Replaces four previously-disagreeing liveness checks
  (`arailctl`/`start.sh`/`status.sh`/`install-daemon.sh` each re-derived
  their own) with one predicate.
- **`./arailctl stop [--world <slug>] [--all]`** — stops one instance, all
  instances, or (with no World instances running) the root lab exactly as
  before. A plain `./arailctl stop` with 2+ instances running now refuses
  and names the roster + exact command, rather than guessing. Fixes a
  real data-loss bug: an un-scoped root-lab stop used to be able to kill a
  live World instance's portal/memory processes mid-write.
- **Per-instance isolation**: each instance's knowledge base, chat memory,
  LanceDB index, and `secrets.env` (provider API keys) are separate trees
  — never shared, never auto-copied between instances or from the root
  lab. `lab/models/` (weights) and `lab/worlds/` (the World library) stay
  shared, since duplicating multi-GB weights per World would be absurd.
- **`/worlds` and the nav World switcher** now show **Open** (not Mount)
  for a World that's already running as its own instance, and **Launch**
  (a copy-to-clipboard `./arailctl start --world <slug>` command, never a
  one-click spawn from the browser) for a World that isn't live but
  something else is already mounted in the current lab. In-place Mount is
  deprecated — announced this release, removed next.
- **`GET /api/instance`** / **`GET /api/instances`** — new read-only
  portal endpoints: self-report (which instance is this process?) and the
  registry-driven roster, used by both the CLI's liveness check and the
  new UI.

### Known gap (2026-07-28 concurrent Worlds)

- **`./arailctl reset` (`pkb`/`data`/`env`/`full`) does not touch World
  instance data.** Only the root lab's `lab/pkb/`/`lab/data/`/`.env`/
  `lab.conf` are wiped; a World instance's own `lab/instances/<slug>/`
  tree (knowledge base, chat memory, LanceDB index, `secrets.env`) is
  untouched by every reset mode. See `docs/concurrent-worlds.md`'s
  "`./arailctl reset` does NOT touch instance data — yet" section for the
  manual workaround and `sprints/BACKLOG.md` for the filed follow-up.

See `sprints/2026-07-28-concurrent-worlds/` for the full design record
(`VISION.md`, `ARCHITECTURE.md`, `BUILD_LOG.md`) and
[`docs/concurrent-worlds.md`](docs/concurrent-worlds.md) for the operator
guide.

### Added (2026-07-25 first-impression experience — one World moment, three doors)

- **`/welcome?step=world`** — the existing welcome-flow World picker is now
  independently addressable. Reachable from three doors: the browser
  cold-start flow (unchanged position), a strictly one-shot redirect for
  CLI-onboarded users who previously never saw it (`GET /` marks
  `lab/data/.world-prompt-seen` *before* redirecting — write-then-redirect
  ordering is the structural fix for the historical redirect-loop risk),
  and new in-portal "Change World" entry points (nav switcher, the `/dac`
  empty state, the dashboard nudge).
- **World-concept explainer + illustrative-examples strip** on the picker,
  teaching what a World means with generalizable examples (photography,
  biology, video games) — any example that happens to also be a real,
  mounted-catalog bundle (e.g. `video-games`) renders once as its own real
  card, never double-narrated.
- **Richer World cards**: term count, provenance tier, and category chips,
  sourced from each bundle's `manifest.json`/`spec.json` — omitted entirely
  (never a placeholder) when a bundle doesn't declare the data.
- **Honest World-picker failure states**: a failed catalog fetch, an empty
  catalog, and a refused mount (409) now render an explanatory,
  never-auto-navigating state instead of silently landing on the dashboard
  as if nothing happened.
- **Swap confirmation**: swapping into a new World from the picker now
  shows the currently-mounted World, a confirmation gate (Continue/Cancel),
  and a "what changed" summary on success, before returning home.
- **`reset pkb` fix**: no longer leaves a dangling `world-mount.json`
  pointing at a World whose staged knowledge-base pages it just deleted;
  also re-arms the one-shot World-prompt marker.
- **First-win card** on the dashboard: a one-time, dismissible pointer at
  a real measured first action (Autoresearch's staged goal, or a single
  chat message) — no fabricated numbers, points at where they get produced.

See `sprints/2026-07-25-first-impression/` for the full design and build
record (`VISION.md`, `EXPERIENCE_SPEC.md`, `ARCHITECTURE.md`,
`BUILD_LOG.md`). Live/screenshot verification against a running portal is
a documented, not-yet-done follow-up.

### Added (2026-07-18 lab persistence)

- **launchd daemon mode** (`arailctl install-daemon`/`uninstall-daemon`): portal +
  memory (+ mlx when configured) run as LaunchAgents — start at login, respawn on
  crash (KeepAlive, ThrottleInterval 15), survive terminal close; per-service logs
  under `lab/logs/`; `start/stop/restart/status` are daemon-aware; double-start is
  guarded in both directions. `start.sh` remains the dev/foreground mode.
- **Truthful model warmth.** Ollama requests carry `keep_alive`
  (`ARAIL_OLLAMA_KEEP_ALIVE`, default 2h — Tier 0 used to be evicted ~5 min after
  the last call); the registry probes `/api/ps` so `healthy("resident")` vs
  `cold("server up, model not loaded")` is honest; boot issues a real 1-token
  warm under the inference slot; the Tier 1 deep model preloads in the background
  when safe (`background_safe()` gate); new `warming` health status; 
  `arail_model_resident`/`arail_model_warming` gauges in /metrics.
- **Auto-resume research.** Run state persists on every transition; an interrupted
  run auto-resumes from its checkpoint at boot (≥0.3 reloads experiments from the
  tracker and skips completed ones; below that it honestly re-plans). A halted lab
  never auto-resumes — and the halt flag itself now persists across restarts.
  Stale "running" workflow snapshots sweep to "interrupted"; Resume revives dead
  tasks; nucleus-forgotten build runs show a visible `lost` phase.
- **Chat conversations** per `docs/conversation-memory.md`: event-log transcripts
  under `lab/pkb/conversations/` (PKB-wipe contract, `.jsonl` invariant),
  restore-on-open with a session picker, orphan turns marked `interrupted` at boot
  with partial replies preserved. Streaming survival + Tier-2 understanding remain
  roadmap (sprint doc is the design of record).
- **Durability polish.** Cost recent-history and cache/recap counters persist;
  the registry's fallback timeline rehydrates from the activity log;
  `activity.jsonl` rotates at 10MB and boots via tail-read (was unbounded +
  whole-file read); `/api/agents/instruct` now actually applies the instruction
  as the agent's active redirect (was a `queued:true` no-op).

### Fixed (2026-07-18 lab persistence)

- `reset.sh stop_services` killed ANY uvicorn on the box (bare `pgrep -f uvicorn`);
  patterns are now arail-scoped with SIGTERM → SIGKILL escalation.
- `/api/research/resume` only flipped the pause flag and could not revive a run
  whose task died with the process.

### Added (2026-07-18 unified model layer + Nucleus MODEL BUILDING tab)

- **Unified model registry (`arail.registry`).** One resolution layer for every
  tab: `resolve(task_profile)` over declared `ModelEntry` records (local /
  aerollm / gateway / anthropic / xai), per-tab overrides persisted in
  `lab/data/model_registry.json`, startup + interval health probes, and
  structured `FallbackEvent`s on the activity stream — no silent fallback,
  ever. Airgap-blocked cloud entries stay visible (greyed), never hidden.
- **AutoResearch root-cause fix.** `ollama_native` no longer inherits the LM
  Studio `localhost:1234` default when `MODEL_API_BASE` is unset — the source
  of every "LLM call failed … using heuristic fallback" ConnectionError. The
  researcher/agents now bind lazily through the registry (config changes apply
  without restart); deep steps default to aeroLLM (Tier 1), cheap sub-steps to
  the Tier 0 resident; every call logs provider, model id, latency, tokens.
- **Global model visibility.** Status-bar Models pill
  (`ai-engineer (resident) · gpt-oss-20b @ aeroLLM` with health dots) opening a
  switcher (lab-wide bindings + per-tab overrides); a persistent degradation
  banner naming the failed endpoint and the fallback in use; inline model
  chips on Autoresearch/Agents/Chat/Build showing each tab's actual model.
- **Nucleus MODEL BUILDING tab (`/build`, maximus tier).** Preflight panel
  (dataset/tokenizer/seq-len/base-checkpoint/dense-vs-MoE + expert count,
  heuristic VRAM/RAM/disk/wall-clock estimates, green/amber/red gating — red
  blocks the run without a recorded override). Build options: Local, Anthropix
  gateway (accelerated; nucleus teacher tier via the Anthropic API, gated on
  hybrid + key), Hybrid, Dry run (nucleus `dry_run`, badged SIMULATED). Run
  management with live loss/throughput, logs, pause/resume/stop/abort, and a
  Register-model action that lands graduated artifacts in the registry so they
  become selectable in every tab.

### Changed (2026-05-31 two-tier model strategy v2 — MODEL-TIERS-V2)

- **Default model → `llama-ai-eng` (Llama-3.2-1B-Instruct + AI-engineer persona, Built with Llama).**
  Setup now does `ollama pull llama3.2:1b` → `ollama create llama-ai-eng -f models/ai-eng/Modelfile.default`
  instead of the self-hosted GGUF ladder. Works on a clean machine today, no
  uploaded artifact required. The model name `llama-ai-eng` begins with "Llama"
  per the Llama 3.2 Community License naming clause.

- **Maximus deep model resolved: `ai-engineer` (Qwen2.5-7B-Instruct, Apache-2.0, 4.7 GB).**
  The `__TODO_DEEP_MODEL__` sentinel for the user-facing deep persona is now a
  concrete model: `ai-engineer` (Qwen2.5-7B + AI-engineer Modelfile.deep SYSTEM
  prompt). Offered on maximus setup (prints the install command); auto-installs
  only with `ARAIL_INSTALL_DEEP_PERSONA=1`. The AirLLM/AeroLLM frontier
  layer-streaming sentinel (`__TODO_DEEP_MODEL__`) is kept separately — the two
  deep surfaces are not conflated.

- **Self-hosted GGUF ladder demoted to dormant opt-in lane (`ARAIL_AI_ENG_SELFHOSTED=1`).**
  The HF-primary → GitHub-mirror → CDN → preview-net cascade is no longer the
  default path. It is preserved as the future Nucleus-distill lane behind the
  flag. `Modelfile.preview` and `Modelfile.production` are kept (dormant).

- **NOTICE dual-base rewrite.** Section 1: Llama-3.2-1B-Instruct, Llama 3.2
  Community License, verbatim required notice string, "Built with Llama"
  display locations, AUP reference. Section 2: Qwen2.5-7B-Instruct, Apache-2.0.
  Section 3: dormant distill lane note.

- **License bundle added (`licenses/`).**
  `licenses/LLAMA-3.2-COMMUNITY-LICENSE.txt` and
  `licenses/LLAMA-3.2-ACCEPTABLE-USE-POLICY.txt` — satisfies the Llama 3.2
  Community License §1.b.i.A (provide a copy of the agreement) and §1.b.iv
  (include the AUP).

- **Branding: 1.5B → 1B for the default; deep = 7B.** README, CLAUDE.md,
  pyproject.toml, catalog, Modelfiles, docs updated.

- **Back-compat chat resolver extended.** `_resilient_chat_default` now checks
  `["llama-ai-eng", "ai-eng:latest", "ai-engineer:latest"]` in order. Existing
  installs keep working; new installs resolve `llama-ai-eng`.

- **`build_ai_eng.py`/`.sh` dormant-lane base re-targeted to Llama-3.2-1B-Instruct.**
  Verified HF ids: `meta-llama/Llama-3.2-1B-Instruct` (HTTP 200) and
  `mlx-community/Llama-3.2-1B-Instruct-4bit` (HTTP 200).

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
