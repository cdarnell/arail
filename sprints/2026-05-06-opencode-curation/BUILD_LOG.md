# Build log: opencode default model + lab curation (Sprint 2)

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at commit 0967b7f
**Started:** 2026-05-07

## Kickoff verification results

| Check | Result |
|---|---|
| opencode version | v1.14.31 — confirmed |
| `OPENCODE_CONFIG_DIR` honored | YES — `opencode.json` (not `config.json`) is read from the specified dir. `debug config` output shows our content when the env var is set. |
| `enabled_providers` field | VERIFIED — present in `@opencode-ai/sdk/dist/gen/types.gen.d.ts` as `enabled_providers?: Array<string>`. Proceed with locked-picker design (A7 primary path, NOT fallback F-LOCK-3). |
| `huggingface-cli` on PATH | YES — `.venv/bin/huggingface-cli` |
| Baseline test suite | 78 passing, 1 skipped (all Sprint 1 tests green) |

**Key finding:** `OPENCODE_CONFIG_DIR` reads `opencode.json` (not `config.json`) from the directory. The `debug paths` output always shows the XDG default config dir; that's unrelated to where opencode reads `opencode.json` from. The actual config IS read from the OPENCODE_CONFIG_DIR-specified path when an `opencode.json` file is present there.

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `BUILD_LOG.md` | Skeleton — this file | — | — |
| 2 | `tests/portal/test_openai_compat.py` | 13 unit tests for shim (F-SHIM-1 through F-SHIM-8, F-SEC-CRED-4) | test-first | — |
| 2 | `src/arail/portal/openai_compat.py` | New module: `/api/openai/v1/models` + `/api/openai/v1/chat/completions` | — | — |
| 3 | `tests/portal/test_opencode_render_config.py` | 10 unit tests for `_render_opencode_config` + `lab_system_prompt` | test-first | — |
| 3 | `src/arail/portal/services/opencode.py` | Add `_render_opencode_config`, `lab_system_prompt`, `_config_path`, `_config_dir`, `_PROVIDER_TOKEN_ENV` | — | — |
| 4 | `tests/portal/test_opencode_llm_ready.py` | 9 unit tests for `llm_ready_check` + cache | test-first | — |
| 4 | `src/arail/portal/services/opencode.py` | Add `llm_ready_check`, `_LLM_READY_TTL_S`, `_LLM_READY_CACHE` | — | — |
| 5 | `tests/portal/test_opencode_config_lifecycle.py` | 8 integration tests for `regenerate_config` + lifecycle | test-first | — |
| 5 | `src/arail/portal/services/opencode.py` | Add `regenerate_config`; update `_compute_source_env`, `start`, `_start_inner` | — | — |
| 6 | `tests/portal/test_opencode_compute_source_env.py` | 3 tests for updated `_compute_source_env` | test-first | — |
| 7 | `src/arail/portal/app.py` | Mount `openai_compat`; update `/api/opencode/start` LLM gate; update `/api/notebooks/status` llm_ready; update `providers_active` hook; update `/opencode` page context | — | — |
| 8 | `tests/portal/test_opencode_routes.py` | Extend with 7 new integration tests for Sprint 2 routes | — | — |
| 9 | `src/arail/portal/templates/opencode.html` | 4-state template | — | — |
| 9 | `src/arail/portal/templates/notebooks.html` | 4th card state (needs-LLM amber dot) | — | — |
| 10 | `scripts/setup.sh` | `--with-coder` flag + `download_coder_model()` | — | — |
| 10 | `scripts/upgrade.sh` | Mirror `--with-coder` | — | — |
| 10 | `pyproject.toml` | Add `[tool.arail.models]` coder_mlx/coder_cuda/coder_cpu entries | — | — |
| 11 | `tests/setup/test_with_coder_flag.py` | 8 setup tests | — | — |
| 12 | `docs/PRIVACY.md` | Trust-model paragraph for `lab/.opencode/` (Sprint 1 follow-up fold-in) | — | — |
| 12 | `src/arail/portal/services/opencode.py` | `is_installed()` returns version string; `OPENCODE_LOG_LEVEL=WARN`/`OPENCODE_DISABLE_AUTOUPDATE=true` in env (Sprint 1 follow-ups fold-in) | — | — |

## Execution

### Step 1 — BUILD_LOG.md skeleton
Committed with kickoff verification results.

## Architect feedback required

None yet.

## Final state

_To be filled after implementation._
