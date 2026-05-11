# QA test report: chat-model-sync
**Verdict:** PASS
**Date:** 2026-05-10
**Allocation:** 40% model-sync / 30% platform-gating / 20% UI picker / 10% regression

## Edge cases tested

| # | Candidate | Disposition |
|---|---|---|
| 1 | Cache poisoning of `_get_live_ollama_current` via hidden cache on `_ollama_installed_models` | **Tested.** Confirmed no `lru_cache`/`@cache` marker; two back-to-back calls produce two HTTP requests. Pinned both invariants. |
| 2 | Concurrent `/api/chat/models` requests under arm64 — platform check per-request vs. import-time | **Inspected.** `platform.machine()` and `os.getenv("ARAIL_DEV_AIRLLM")` are called inside `_show_airllm()`/`_resolve_default_deep_backend()`, not at module import. No global cache. Per-request semantics confirmed. |
| 3 | `ARAIL_DEV_AIRLLM` flipped at runtime | **Tested.** Test sets env post-import, observes `_show_airllm()` flip False→True. Plus pinned strict `"1"` semantics (`"true"`, `"yes"`, `"0"`, `"1 "`, etc. all remain False). |
| 4 | `ollama show ai-engineer` on fresh system with deleted Modelfile | **Inspected.** `scripts/setup.sh:764` guards on `[[ -f "$_modelfile" ]] && ! ollama show ai-engineer` — both conditions required; missing Modelfile is a silent skip, no crash. Safe. |
| 5 | Compare-mode flash when no deep backend installed | **Inspected** in `chat.html:2434-2439`. `setCompare(true)` with `deeps.length === 0` fires `flashStatus(...)` and never calls `selectModelB`, leaving `State.bId` at its prior value (typically `null`). Column B stays hidden? No — `colB.hidden = !on` sets it visible. **Minor UI risk flagged**: column B is visible-but-empty after compare-on with no deeps. Not a regression (prior behavior was same shape; the change was the flash text), but worth a follow-up. |
| 6 | `ARAIL_DEEP_BACKEND` injection payloads | **Tested.** Parametrized over 7 adversarial strings (`"aerollm; rm -rf /"`, `"$(rm -rf ~)"`, `"<script>"`, SQL-shaped, etc.) — all fall through to auto-detect because the value is only checked via `in _OPTIONAL_CHAT_BACKEND_CONFIG` (a dict-keys allowlist). Never exec'd. Plus pinned `.strip().lower()` semantics (trailing newline normalizes; whitespace-only falls through; mixed case matches). |
| 7 | AirLLM importable but unconstructable | **Tested.** Pinned that `_is_airllm_installed()` uses `importlib.util.find_spec` only — does NOT attempt construction. Documented as intentional tradeoff (fast, side-effect-free; real errors surface from the airllm subprocess). |

**Additional edges caught during inspection:**

- `_get_live_ollama_current(be)` with `be.base_url=None` (attribute exists but is None) — tested, returns None cleanly.
- `_get_live_ollama_current(be)` with backend lacking `model_name` — tested, falls through to first tag.
- `_get_live_ollama_current(be)` matched by type-name only (URL rewritten but class name still `*ollama*`) — tested.
- arm64 + `ARAIL_DEV_AIRLLM=1` + airllm installed → `_show_airllm()` still False — regression-pinned (headline BUG fix).
- arm64 + no aerollm → `_resolve_default_deep_backend()` returns None, never `"airllm"` — regression-pinned.

## New tests added

- `tests/test_chat_model_sync_qa.py` (20 cases) — covers all 7 candidate edge cases plus the additional defensive paths above. Separate from `test_chat_model_sync.py` so BUILD_LOG.md doesn't need re-touching.

## Test run summary

```
$ pytest tests/test_chat_model_sync.py tests/test_chat_model_sync_qa.py \
         tests/test_default_deep_backend_resolver.py \
         tests/test_dispatch_35b_enforcement.py \
         tests/test_must_stream_rule.py -q
95 passed, 6 warnings in 2.30s

$ pytest tests/ -q  (full suite, regression check)
1037 passed, 1 skipped, 1 xfailed, 33 warnings in 31.98s
```

Zero failures. Zero regressions vs. the build commit's claimed 75-pass baseline.

## Issues found

None at PASS-blocking severity.

## Recommendations before ship

1. **Low / follow-up.** `setCompare(true)` with `deeps.length === 0` leaves column B visible-but-empty (gray pane) until user toggles compare off. Functionally correct (no crash, flash explains why), but cosmetically poor. Suggest a follow-up that either keeps `colB.hidden = true` when `!deeps.length` or renders an empty-state card in column B. Not a sprint blocker.
2. **Low / follow-up.** REVIEW.md already flagged stale `.bak` files in `lab/tools/` (`benchmark_models.py.bak`, `model_router.py.bak`); confirmed still present in `git status`. Trivial cleanup.
3. **Low / follow-up (already filed).** The `_is_airllm_installed` find-spec-only semantics are now pinned by test; if a future operator hits "installed-but-broken AirLLM," the airllm-subprocess error is the surface. Consider a one-time construction smoke test in setup.
