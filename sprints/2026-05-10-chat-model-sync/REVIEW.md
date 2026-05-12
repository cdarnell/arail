# Review: chat-model-sync (architect, REVIEW mode)
**Verdict:** PASS
**Date:** 2026-05-10

## Failure-mode coverage
Every row in ARCHITECTURE.md § Failure modes is addressed in code and/or test. The arm64-AirLLM block, phantom-catalog suppression, Ollama-down graceful degradation, `None`-return handling at the hard-floor site (line 4371: `_resolved is None` → emits warn log and skips routing rather than crashing), stale-`d.current` fix, 30B threshold flip, `ai-engineer:latest` fallback, and the `ARAIL_DEV_AIRLLM=1`-on-arm64 escape-hatch closure all have direct mirror tests in `test_chat_model_sync.py` or the updated `test_default_deep_backend_resolver.py` / `test_dispatch_35b_enforcement.py`.

## arm64 absolute-block invariant
Holds. `_show_airllm()` checks arm64 first and returns `False` before consulting `ARAIL_DEV_AIRLLM` or install status — `if _platform.machine() == "arm64": return False` is the first executable line (app.py ~5607). `test_chat_model_sync.py` has the regression test (`ARAIL_DEV_AIRLLM=1` + arm64 → False). `_resolve_default_deep_backend()` similarly returns `None` on arm64-without-aerollm rather than `"airllm"` (app.py ~5018).

## Test coverage
14 new cases in `test_chat_model_sync.py` + 22 updates across the three pre-existing files = 36 sprint-touched assertions; 75 pass total. Spec called for "~20" new cases; the build consolidates resolver-table coverage into `test_default_deep_backend_resolver.py` and 30B-boundary coverage into `test_must_stream_rule.py` (no duplication) — coverage is fully met by partition, not reduced.

## Tech debt
Net negative as predicted in ARCHITECTURE.md § Tech debt. The three added helpers (`_show_airllm`, `_get_live_ollama_current`, `_default_teacher_backend` returning Optional) are narrow and well-named; followups are filed in the architecture doc. Repaid debt (silent arm64 routing failure, phantom picker entries, stale chip, hardware-floor drift) substantially outweighs the added surface.

## Must-fix before ship
*(none)*

## Nice-to-have followups
- Consolidate `_show_airllm` / `_is_airllm_installed` / `_is_aerollm_installed` into a `BackendRegistry` (already filed).
- Expose a `live_model()` method on the router so `_get_live_ollama_current()` collapses to a one-liner (already filed).
- Add an integration test that boots the FastAPI app on arm64 and asserts `GET /api/chat/models` returns `optional_backends` with no airllm entry — current coverage is unit-level only.
- Stale `.bak` files in `lab/tools/` (`benchmark_models.py.bak`, `model_router.py.bak`) appear in git status; unrelated to this sprint but worth a cleanup commit.
