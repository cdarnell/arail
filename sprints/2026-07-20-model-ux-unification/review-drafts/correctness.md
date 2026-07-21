# Review (correctness lens): Model selection UX — unified-list fidelity

**Date:** 2026-07-20
**Build:** BUILD_LOG.md at `692b460`
**Architecture:** ARCHITECTURE.md at `938ff9d`
**Base for diff:** `qukaizen/gemma4-ollama-think-fix` (`689ced8`)
**Lens:** correctness — does the diff do what BUILD_LOG/ARCHITECTURE claim, cross-referenced against the failure modes the architecture itself names as handled?

## Verdict: WEAK_PASS

No BLOCK findings. One unresolved ASK (a latent inflight-lock leak) filed as a follow-up; everything the architecture claims to handle is actually implemented and backed by non-vacuous tests.

## Spec adherence

Verified each contract against the diff, not the prose:

- **C1 / F-BLANK / F-DEADFIELD** — `memory_snapshot` nested into `compact.hardware` (app.py ~8252); top-level `hardware` key deleted in the same emission (~8283), replaced by a comment. Frontend reads `d.compact.hardware`. Matches BLOCK-1 resolution. ✓
- **C1 / F-FALLBACKLIE** — the darwin sysctl fallback no longer sets `free_gb = total_gb`; `free_gb` stays 0.0 → `_fit_verdict_label` returns "Unknown". ✓
- **C2 / F-FAKEFIT** — `State.models` sourced from `d.compact.local_models.items` (was `d.gallery.installed`). **Both** `'good'` defaults changed to `'Unknown'` — rail (chat.html ~3325) and active-mini (~3425). ✓ The discovered `endpoint` top-level mirror added to `_build_local_model_entry` is a correct back-compat fix (selectModel reads `m.endpoint`).
- **C4 / F-HEADER (both twins)** — `Local · GPU (≤ 8B)` → `Local · GPU`; `Local · SSD (streamed)` → `Local · aeroLLM` at rail cards, picker sections, subtitle, and column-B picker. ✓
- **C4 / F-OVERSELL** — aeroLLM streaming/layer-stream/SSD/bit-exact claims swept from chat.html (tooltips, streamed-badge titles, comparison strip, References) and models_catalog.yaml (deep-placeholder comment, gpt-oss-20b entry). aeroLLM `"streamed"` field flipped True→False in `optional_backends`. Deep-entry frontend verdict no longer emits `'streaming'` for aeroLLM (`o.installed ? 'streaming'` → backend-branched `Resident`/`Ready to load`/`Not installed`, `Streaming` only for AirLLM). ✓
- **Gemma license fix** — catalog `(Apache-2.0)` → `Built with Gemma · Gemma Terms of Use (ai.google.dev/gemma/terms)`. ✓ Note: the model retains the Apache-2.0 gpt-oss entry's label correctly (that one *is* Apache-2.0); only the Gemma row was mislabeled and is now fixed.
- **C5 / F-EJECTLIE / F-EJECT-OLLAMA-FALSE** — the terminal `return {"ok": True, ...}` is gone; `ok`/`requires_restart` computed per-runtime. ollama tracks real `returncode`; aerollm/airllm always `ok=False, requires_restart=True` with backend-accurate label and no fake `freed`; mlx/cpu/cuda/mlx-openai `ok=False, requires_restart=True`; blank `ok=bool(freed)`. ✓ The BUILD_LOG-noted inline addition of `_validate_local_model_id_relaxed(model)` before `subprocess.run(["ollama","stop",model])` is present and correct — closes the architecture's own Security assumption that was actually false.
- **C6.1 / F-INITREADY** — initial `_CHAT_MODEL_LOAD_STATE` = `idle`/"No model loaded"/`eta_seconds=None`/`progress=0.0`. ✓
- **C6.2 / F-CACHERACE / F-LOADRACE** — `_OPTIONAL_CHAT_BACKEND_CACHE_LOCK` guards eject's clear-all and `_get_optional_chat_backend`'s double-checked read/store (construction deliberately outside the lock). `_CHAT_MODEL_LOAD_INFLIGHT` (asyncio.Lock) enforces single-load; `_run` wraps construction in `scheduler.inference_slot("chat-model-load")`. ✓
- **C6.3 / F-SWITCH** — `_get_optional_chat_backend(..., expected_model=...)` raises `_ChatBackendModelMismatch` when a resident instance's `model_name` differs; caught → honest "requires a portal restart" error, never false `ready`. Degrades safe: if `model_name` is absent/empty, the check no-ops (never a false refusal). ✓
- **C6.4 / F-CANCEL** — cancel endpoint never mutates state, never returns `canceled`; returns honest `loading`/`no load in progress` notes. Verified by ast-level test (docstring stripped) that the function body contains neither `"canceled"` nor `_set_chat_model_load_state`. ✓
- **C6.5 / F-TIMEOUT-ORPHAN** — `asyncio.wait_for(asyncio.shield(task), timeout=_load_max_sec())`. Timeout flips *reported* state to `error` but the inflight lock is released only by the task's done-callback, not by the guard — so a second load is refused until the background thread settles. The test proves the safety property directly (`construct_calls == 2`: the refused middle call never constructed). This is the OOM-critical path and it is correctly implemented. ✓
- **C6.6 / F-FAKEETA / F-CORRUPT** — ETA = `real_on_disk_gb / rolling-median throughput`; `progress=None` (no fake bar); corrupt detection = >30% disagreement vs catalog `size_gb`, suppresses ETA. `:tag`-suffix no-op documented as a known safe limitation. ✓
- **C6.7 / F-REFIT** — `_prepare_chat_model_load` re-snapshots memory and recomputes verdict at click time; "Requires streaming" doesn't block but the message says so. ✓
- **C6.8 / F-DAEMONDOWN** — `_friendly_load_error` replaces the `type(exc).__name__: {exc}` dump; daemon-down markers → actionable banner; full exception logged server-side only. ✓
- **C7** — `_backend_notices`, `backend_notice` var, and response key all deleted. ✓
- **C8** — References pointer `gallery.py` → `__init__.py`. ✓
- **F-WARMDOT** — `_ollama_ps_resident_ids()` (live `/api/ps`, ≤1s timeout, last-known fallback) feeds `warm` on Ollama rows; `_tier1_resident()` feeds aeroLLM `resident`; wrapper-cache presence for AirLLM. `State.warmModels` seeded from `m.warm || m.resident` on every fetch. ✓

**Post-step-14 self-deadlock fix** — the `_caller_holds_inference_slot` kwarg is a genuine correctness requirement introduced by C6.2's own change (nesting two acquisitions of the single non-reentrant process-wide semaphore). The admin call site sets it; `_run` honors it. Regression test proves both directions (flag prevents hang; absence times out). This is the builder catching and fixing a bug its own sprint introduced — exactly right.

Implementation order followed; no scope drift beyond documented inline fixes, all within contracts already being edited.

## Code quality findings

- [INFO] `_prepare_chat_model_load` is long (~7250–7380) but the internal `_do_load`/`_run`/`_release_inflight_once` decomposition is legible and each nested piece is small. Acceptable for a state-machine executor.
- [INFO] Deep-row fit vocabulary (`Resident`/`Ready to load`/`Not installed`/`Streaming`) is a new frontend-only verdict set distinct from the local `{Good,Marginal,Requires streaming,Unknown}`. `fitClass()` was extended to color them (`resident`→good, `not install`→marginal; `Ready to load`/`Streaming` fall to the `streaming` class). Cosmetic only, no honesty impact — none of these is a false "streaming" claim on aeroLLM.

## Security findings

- [INFO] eject now validates `model` via `_validate_local_model_id_relaxed` before `subprocess.run(["ollama","stop",model])` (argv, not shell). The architecture's Security section *assumed* this was already true; it wasn't, and the builder closed it. Correct.
- [INFO] `warmLabelText` / `flashStatus` new fields go through `escapeHtml` / textContent — F-XSS coverage confirmed by test.

## Test coverage assessment

Every Phase-0 and Phase-0b failure-mode row maps to a named test, except the three the architecture itself scopes to real-hardware QA (T-EJECT-OLLAMA real residency delta, T-RESTART real process restart, T-NOFLICK real memory jitter). Spot-checked the two safety-critical tests (F-TIMEOUT-ORPHAN, F-CANCEL) — they assert the real invariants (no double residency via construction-count, no `canceled` mutation via ast), not implementation trivia. The full-suite flakiness saga (3 attempts, 2 disproved by re-running) is a model of paranoid verification; the final fix (private-dict accessor monkeypatch) is a genuinely stronger isolation pattern. Fifth full-suite run confirms zero sprint-attributable failures.

## Performance assessment

`ollama ps` warmth probe is a single per-request call with ≤1s timeout and last-known fallback — off the hot path, per the architecture's Performance guard. ETA derivation is arithmetic. No regression concern.

## Tech debt delta

No new debt beyond what ARCHITECTURE.md predicted (approximate-until-warmed ETA; operator-opt-in >1 concurrency). One latent gap surfaced (below) that should be filed.

## Required actions before merge

None are blocking. One follow-up to file:

1. **[ASK — follow-up] Inflight-lock leak on early exception.** In `_prepare_chat_model_load`, between `await _CHAT_MODEL_LOAD_INFLIGHT.acquire()` and `task.add_done_callback(_release_inflight_once)`, the pre-task setup (`_local_memory_snapshot`, `_estimate_model_memory_gb`, `_fit_verdict_label`, `_set_chat_model_load_state`, `asyncio.ensure_future`) runs *outside* any try/finally. If any of those raises synchronously, the inflight lock is acquired but its release callback is never wired, and the lock leaks permanently — which bricks *all* future chat model loads until a portal restart. That is a strictly worse failure than the bug C6.2 fixes. Probability is low (`_real_on_disk_gb` swallows its own exceptions; the rest are simple), so this is not a BLOCK, but it is a real correctness gap the F-TIMEOUT-ORPHAN handling does not cover. Recommend wrapping the acquire-to-callback span in `try/except` that releases on early failure (or acquiring immediately before `ensure_future`). Owner: builder. Review-by: next sprint.

### Non-blocking observations (no action required)

- Ollama warmth matching compares `entry.id` against `/api/ps` `name`/`model` fields, which typically carry a `:tag` suffix. A format mismatch would under-report warmth (dot stays `cold`) — an honest under-claim, not a lie, so it degrades safe. Worth a QA check on a real box that a warmed Ollama model actually lights the dot.
- The refused-second-load path returns the *current* state (which may be `error`/`ready`), not literally `state="loading"` as C6.2's prose says. The message is honest and the state reflects reality, so this is a harmless deviation from the literal spec wording.
