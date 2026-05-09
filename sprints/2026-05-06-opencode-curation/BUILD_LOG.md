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
| 1 | `BUILD_LOG.md` | Skeleton — this file | — | 9feb89e |
| 2 | `tests/portal/test_openai_compat.py` | 19 unit tests for shim (F-SHIM-1 through F-SHIM-8, F-SEC-CRED-4) | test-first | 07c3375 |
| 2 | `src/arail/portal/openai_compat.py` | New module: `/api/openai/v1/models` + `/api/openai/v1/chat/completions` | — | 07c3375 |
| 3 | `tests/portal/test_opencode_render_config.py` | 22 unit tests for `_render_opencode_config` + `lab_system_prompt` | test-first | 6c189bd |
| 3 | `src/arail/portal/services/opencode.py` | Add `_render_opencode_config`, `lab_system_prompt`, `_config_path`, `_config_dir`, `_PROVIDER_TOKEN_ENV` | — | 6c189bd |
| 4 | `tests/portal/test_opencode_llm_ready.py` | 10 unit tests for `llm_ready_check` + cache | test-first | 6c189bd |
| 4 | `src/arail/portal/services/opencode.py` | Add `llm_ready_check`, `_LLM_READY_TTL_S`, `_LLM_READY_CACHE` | — | 6c189bd |
| 5 | `tests/portal/test_opencode_config_lifecycle.py` | 10 integration tests for `regenerate_config` + lifecycle | test-first | 6c189bd |
| 5 | `src/arail/portal/services/opencode.py` | Add `regenerate_config`; update `_compute_source_env`, `start`, `_start_inner` | — | 6c189bd |
| 6 | `tests/portal/test_opencode_compute_source_env.py` | 8 tests for updated `_compute_source_env` | test-first | 6c189bd |
| 7 | `src/arail/portal/app.py` | Mount `openai_compat`; update `/api/opencode/start` LLM gate; update `/api/notebooks/status` llm_ready; update `providers_active` hook; update `/opencode` page context | — | b5e2ccd |
| 8 | `tests/portal/test_opencode_routes.py` | Extend with 7 new integration tests for Sprint 2 routes | test-first | b5e2ccd |
| 8 | `tests/portal/test_opencode_service.py` | Update Sprint 1 tests for shim URL contract change | — | b5e2ccd |
| 9 | `src/arail/portal/templates/opencode.html` | 4-state template (installed_no_llm state added) | — | 612e32c |
| 9 | `src/arail/portal/templates/notebooks.html` | 4th card state (needs-LLM amber warn dot) | — | 612e32c |
| 9 | `src/arail/portal/static/style.css` | `.status-dot.warn` + `.status-warn` pill CSS | — | 612e32c |
| 10 | `scripts/setup.sh` | `--with-coder` flag + `download_coder_model()` | — | 826f90e |
| 10 | `scripts/upgrade.sh` | Mirror `--with-coder` | — | 826f90e |
| 10 | `pyproject.toml` | Add `coder_mlx/coder_cuda/coder_cpu` to `[tool.arail.models]` | — | 826f90e |
| 11 | `tests/test_with_coder_flag.py` | 9 setup tests | — | 826f90e |
| 12 | `docs/PRIVACY.md` | Trust-model section for opencode Workbench | — | 86740c7 |

## Execution

### Step 1 — BUILD_LOG.md skeleton
Committed with kickoff verification results.
Commit: 9feb89e

### Steps 2-6 — OpenAI shim, config renderer, LLM gate, regenerate_config
Committed together in previous session. Includes 19+22+10+10+8 = 69 new tests.
Commits: 07c3375, 6c189bd

Delta from plan: tests/portal/test_opencode_service.py Sprint 1 tests needed updating
because `_compute_source_env` contract changed (my_machine now points at shim, not Ollama).
Fixed cross-test isolation: patch `arail.portal.app._get_chat_model_load_state` (source)
not `arail.portal.services.opencode._get_chat_model_load_state` (module-local copy that
_compute_source_env doesn't hold after lazy import).

### Steps 7-8 — LLM gate on /start, llm_ready in status, Sprint 2 route tests
Commit: b5e2ccd

app.py changes:
- `/api/opencode/start`: llm_ready_check() gate → 409 {ok:false, reason, hint, chat_url} when not ready
- `/opencode` page: passes llm_ready, llm_hint, llm_chat_url to template context
- `/api/notebooks/status` opencode entry: adds llm_ready, llm_reason, llm_hint fields
- providers_active hook: regenerate_config() then restart() (in single lock)

7 Sprint 2 route tests: gate blocks correctly, tier gate fires before LLM gate,
status entry carries llm_ready fields.

### Step 9 — 4-state templates + warn dot CSS
Commit: 612e32c

opencode.html: State 2b (installed_no_llm) with amber status-warn pill + Chat CTA.
Start button 409 handler: amber colour + redirect to chat_url after 1.5s.
notebooks.html: setCard() handles nb.llm_ready === false → warn dot + llm_hint text.
style.css: .status-dot.warn (amber, animated) + .status-warn pill added.

### Steps 10-11 — --with-coder flag + setup tests
Commit: 826f90e

setup.sh: CODER_*_ID constants, WITH_CODER default, arg parsing in main(),
download_coder_model() function (warns on min but never aborts per A11),
called after download_model in main() sequence.
upgrade.sh: --with-coder / --no-coder arg parsing; inline coder download.
pyproject.toml: coder_mlx/coder_cuda/coder_cpu entries in [tool.arail.models].
9 tests: pyproject entries, Qwen2.5-Coder IDs, arg parse, env var, min tier warning.

Note: tests landed in tests/ (not tests/setup/) to match existing test layout.

### Step 12 — PRIVACY.md opencode trust-model section
Commit: 86740c7

Added "opencode Workbench (max-tier only)" section documenting:
loopback-only binding, no API keys in opencode.json plaintext,
OPENCODE_DISABLE_AUTOUPDATE, log capture, iframe URL safety, and
opencode's own network behaviour (out of lab audit scope).

Sprint 1 follow-up: `is_installed()` version probe — deferred. Current
bool API is tested and stable; a version-string return would break callers.
Sprint 1 follow-ups OPENCODE_LOG_LEVEL=WARN and OPENCODE_DISABLE_AUTOUPDATE
are already in opencode.py (set in start() env, committed in 6c189bd).

## Architect feedback required

None. All planned work implemented per spec.

## Final state

| Metric | Value |
|---|---|
| Portal tests | 153 passing, 1 skipped |
| Setup tests | 9 passing |
| Total new tests | 84 new tests (69 service/shim/config + 7 routes + 8 service-update + 9 setup) |
| Commits this sprint | 7 (9feb89e, 07c3375, 6c189bd, b5e2ccd, 612e32c, 826f90e, 86740c7) |
| Pre-existing failures | 5 (test_toast_ui × 2, test_drafter × 1, others × 2 — unrelated to this sprint) |
| New regressions | 0 |

Files changed (net new):
- `src/arail/portal/openai_compat.py` (NEW, ~170 lines)
- `src/arail/portal/services/opencode.py` (+590 lines)
- `src/arail/portal/app.py` (+40 lines net)
- `src/arail/portal/templates/opencode.html` (+25 lines)
- `src/arail/portal/templates/notebooks.html` (+8 lines)
- `src/arail/portal/static/style.css` (+12 lines)
- `scripts/setup.sh` (+75 lines)
- `scripts/upgrade.sh` (+48 lines)
- `pyproject.toml` (+7 lines)
- `docs/PRIVACY.md` (+35 lines)
- `.gitignore` (+1 line — lab/.opencode/)
- 6 new test files (~700 lines total)
