# Build log: Model-Hosting Strategy Reframe

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) (REVISED v2, 2026-05-30)
**Started:** 2026-05-30
**Branch:** `qukaizen/arail-kv-available-budget`

## Confirmed license facts (researched before writing NOTICE)

- **Qwen/Qwen2.5-3B-Instruct** — licensed under the **Qwen Research License Agreement** (release date 2026-09-19). This is **NOT Apache-2.0**. It is a custom Alibaba Cloud research license with attribution and redistribution obligations. No SPDX identifier is in SPDX's canonical list for this license; we record it as "Qwen Research License" with upstream URL.
- **Qwen/Qwen2.5-7B-Instruct** (the preview base) — licensed under **Apache-2.0**. Attribution is required per Apache-2.0 §4(a).
- The merged-LoRA GGUF is a derivative of the 3B base and inherits the Qwen Research License obligations. The NOTICE and any redistributed artifact (HF model card, GitHub release) must carry the attribution.

## Plan

| # | Files | Change | Commit ref |
|---|---|---|---|
| 1 | `NOTICE` (new), `LICENSE` | Attribution file + pointer | step-1 |
| 2 | `pyproject.toml`, `scripts/setup.sh:69-71/986-989`, `src/arail/router/backends.py`, `src/arail/router/airllm_worker.py`, `src/arail/portal/app.py` | Sentinel rollout for deep defaults | step-2 |
| 3 | `pyproject.toml` | Self-hosted keys (`ai_eng_hf_repo`, `ai_eng_quant`, `ai_eng_gh_url`, `ai_eng_cdn_url`, `ai_eng_sha256`) | bundled with step-2 |
| 4 | `scripts/setup.sh:730-808` | Rewrite `install_models()` — self-hosted fetch ladder + digest verify + preview net | step-4 |
| 5 | `scripts/check_ai_eng_artifact.sh` (new) | Probe HF + GitHub for live artifact (2b gate) | step-4 |
| 6 | `scripts/package_ai_eng.sh` (new) | Merge→GGUF→Modelfile→sha256→upload scaffold | step-5 |
| 7 | `models/ai-eng/Modelfile.preview`, `src/arail/chat/models_catalog.yaml` | Strip qwen narrative; self-hosted install; new deep placeholder row | step-6 |
| 8 | `README.md`, `CLAUDE.md`, `src/arail/portal/templates/tuning.html`, `pyproject.toml` tier desc, `docs/INSTALL.md`, `CHANGELOG.md` | Copy rewrites — honest framing + self-hosted pull narrative | step-7 |

## Execution

### Step 1 — NOTICE + LICENSE pointer
Confirmed licenses. Wrote NOTICE with Qwen Research License (3B base) and Apache-2.0 (7B preview base) attribution. Added HF-card/GitHub-release redistribution clause. Appended one-line pointer to LICENSE.

### Step 2+3 — Sentinel rollout + pyproject self-hosted keys
Replaced 70B/405B deep defaults with `__TODO_DEEP_MODEL__` in pyproject, setup.sh, backends.py, airllm_worker.py, app.py. Added self-hosted keys with placeholder markers.

### Step 4 — install_models() rewrite + check_ai_eng_artifact.sh
Rewrote setup.sh install_models() with HF→GitHub→CDN→preview-net ladder. Added digest verification (fail-closed on placeholder). Created check_ai_eng_artifact.sh probe.

### Step 5 — package_ai_eng.sh scaffold
Created merge→GGUF→Modelfile→NOTICE→sha256→upload scaffold. Exits nonzero on missing inputs. No credentials, no invented weights.

### Step 6 — Modelfile.preview + catalog
Stripped qwen self-description from Modelfile.preview SYSTEM. Updated catalog ai-eng entry (self-hosted install). Added deep-model placeholder row.

### Step 7 — Copy rewrites
Rewrote README maximus row, CLAUDE.md tier line + qwen fallback prose, tuning.html hero copy, pyproject maximus description, docs/INSTALL.md pull narrative, CHANGELOG Unreleased section.

## Deferred (follow-up ticket 2b)

- Delete `Modelfile.preview` and the preview net once `scripts/check_ai_eng_artifact.sh` returns 0 (i.e., the self-hosted GGUF is live on HuggingFace or GitHub).
- Win Condition #1 is "met-on-upload" — the code path ships correct and complete; it succeeds the moment the GGUF lands.

## Architect feedback required

*(none — no gaps surfaced during implementation)*

## Final state

All steps complete. Tests: full suite run with `python -m pytest` (config/copy sprint; no OOM-risk loads). Shell scripts syntax-verified with `bash -n`. Python files verified with `py_compile`. YAML parsed cleanly.
