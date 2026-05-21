# When you add a new class/backend/endpoint, write a reachability test, not just a unit test

**Date:** 2026-05-20
**Tags:** [arail, build, review, qa, infra, pitfall]
**Source:** Sprint 2026-05-18-provider-aware-chat-dropdown (architect loop-1 BLOCK; B1 + B2)

## Action shape

When you add a new class, backend, or endpoint and its unit tests pass, do **also write a reachability/contract test that exercises the real dispatch or render path** instead of trusting the green unit suite, because a unit test proves the thing *works in isolation*, not that the actual caller *constructs or consumes it*. Passing units + dead wiring looks identical to a working feature until someone clicks the button.

## Context

This sprint shipped two new seams and both passed their unit tests while being completely unwired in production:

- **B2 (backend):** `OllamaNativeBackend` was fully implemented, registered in `BACKEND_MAP`, and unit-tested green — but `_get_runtime_backend`'s ollama branch still constructed the old `OpenAICompatBackend` at `/v1`. The ctx feature (the whole point of L3 for the most common local runtime) was dead. The unit test proved the class works; nothing proved it was reachable from dispatch.
- **B1 (server↔frontend contract):** the server wrote cloud models to `gallery.catalog` and had passing server-side tests; the frontend read `gallery.installed` (always `[]` for cloud). A successful Claude/OpenRouter fetch rendered the "no models" empty state. Two green sides of a contract that didn't meet in the middle.

The architect's review caught both as a single `BLOCK`. The fix added `test_b2_ollama_dispatch_wiring.py` (asserts `_get_runtime_backend("ollama", ...)` returns `OllamaNativeBackend` AND that a ctx override flows into `options.num_ctx` in the real POST body) and `test_b1_cloud_gallery_contract.py` (asserts a cloud-success response yields renderable `gallery.catalog` cards). Re-review went PASS.

## Why this matters

Both defects were the headline features of their layers. They would have shipped invisible: the test suite was green, the code reviewed clean line-by-line, and only an end-to-end click would have exposed them. The cost was one full review loop (BLOCK → fix → re-review). Writing the reachability test in the *build* phase — "does the real caller construct/consume this?" — would have caught both before review and saved the loop. The smell to watch for: a new class registered in a map/registry, or a new response field, whose only tests instantiate it directly or assert the server side alone.

## Related learnings

- [2026-05-20-isolate-secrets-env-in-tests.md](2026-05-20-isolate-secrets-env-in-tests.md) — the other pitfall from this same sprint (caught in QA, not review).
