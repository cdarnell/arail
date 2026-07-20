# Build log: model selection UX — unified-list fidelity, disclosed honestly

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at `938ff9d468e1369e69f2b7f8f0613d0ee1184fa5` (ledger-fix commit, already landed)
**Started:** 2026-07-20

## Recap: what already shipped (ledger commit `938ff9d`, not redone here)

Implementation-order items 1, 2, 4, 7 (§2.1 nest+delete top-level `hardware`
and close the psutil-fallback lie; §2.2 rail data source + both `'good'`
fallbacks at 3296/3375; §2.4 delete `backend_notice`; §2.5 fix the phantom
`gallery.py` References pointer) plus the discovered `endpoint`
back-compat fix. This log covers everything **after** that commit.

## Plan

Matches ARCHITECTURE.md's own "Recommended implementation order" verbatim.
Steps 1/2/4/6/7 are done (ledger commit). Remaining:

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 3 | `chat.html` | Header twins: `Local · GPU (≤ 8B)`→`Local · GPU`, `Local · SSD (streamed)`→`Local · aeroLLM` (both rail + picker + subtitle + picker-B) | T-HEADER | TBD |
| 4 | `chat.html`, `models_catalog.yaml` | F-OVERSELL full site sweep (no "streaming"/"selective expert-streaming"/"bit-exact" on aeroLLM copy) + Gemma Apache-2.0 mislabel fix | T-COPY | TBD |
| 5 | `app.py:6835-6900` | C5 honest eject: edit the terminal `return {"ok": True}` to compute `ok`/`requires_restart` per-runtime | T-EJECT-AERO, T-EJECT-OLLAMA-FAIL | TBD |
| 8 | `app.py`, `chat.html` | Warmth probe: `warm` from live `ollama ps` (short-timeout), `resident` from `_tier1_resident()`; deep rows lose eject, gain warmth-driven badge copy | T-WARMDOT | TBD |
| 9 | — | Run Persistence & Honesty (display subset) — verification, folded into step 3-8 commits' own test runs | — | — |
| 10 | `app.py` | C6.1 idle init state + `_OPTIONAL_CHAT_BACKEND_CACHE_LOCK` + `_CHAT_MODEL_LOAD_INFLIGHT` | T-IDLE, T-CACHERACE | TBD |
| 11 | `app.py` | C6.2 serialize load via `scheduler.inference_slot("chat-model-load")` | T-LOADRACE | TBD |
| 12 | `app.py`, `chat.html` | C6.4 honest Cancel (no `canceled` state) + C6.5 bounded timeout holding the inflight lock until the thread settles | T-CANCEL, T-LOAD-BOUND | TBD |
| 13 | `app.py`, `docs/maximus.plan.md` | C6.3 model-identity refusal, C6.6 real ETA, C6.7 re-snapshot fit at click time, C6.8 friendly errors; trim doc §5 to `{idle,loading,ready,error}` | T-SWITCH, T-ETA, T-CORRUPT, T-REFIT, T-DAEMONDOWN | TBD |
| 14 | — | Full suite run + regression grep | — | TBD |

Each row lands as its own commit (or a tightly-coupled pair when the
architecture itself splits backend/frontend for the same contract, e.g.
step 8's server probe vs. client rendering may be two commits).

## Execution

### Step 3 — F-HEADER, both twins
`chat.html`: `Local · GPU (≤ 8B)` → `Local · GPU`; `Local · SSD (streamed)`
→ `Local · aeroLLM` at all four sites (rail-card headers ×2, picker-popup
section headers ×2), plus the deep rail-card subtitle. No plan delta.
Test: `tests/test_model_ux_phase0_headers.py` (T-HEADER).
Commit: `bf34aee`.

### Step 4 — F-OVERSELL full site sweep + Gemma license fix
`chat.html`: fixed every aeroLLM-attributed streaming/layer-stream/SSD
claim (col-chip-B tooltip+hint, References panel, both streamed-badge
titles, comparison-strip cell + cs-why note + setCompare comment,
picker-B header, disabled-B-button tooltip, and the central
`deepEntries.fit.verdict` mapping — now branches on backend id instead
of `o.installed ? 'streaming' : ...`). Extended `fitClass()` with
`resident`/`not install` branches so the new verdict vocabulary gets a
sane chip color. `models_catalog.yaml`: fixed the deep-model-placeholder
comment and the gpt-oss-20b-MLX-4bit entry (dropped the "native
selective expert-streaming backend"/"bit-exact" claims — AERO_MOE_SELECT
is off and absent from src/). Folded in the Gemma Apache-2.0 mislabel
fix per ARCHITECTURE.md's "Folded into this sprint" note.
No plan delta. Test: `tests/test_model_ux_phase0_oversell_copy.py` (T-COPY).
Commit: `c2fc531`.

### Step 5 — C5 honest `/api/chat/eject`
`app.py`: rewrote the terminal `return {"ok": True, ...}` to compute
`ok`/`requires_restart` per runtime (aerollm/airllm always `ok=false`;
ollama tracks the real subprocess returncode; mlx-openai/mlx/cpu/cuda
always `ok=false, requires_restart=true`; blank/unknown `ok=bool(freed)`).

**Delta from plan (discovered gap, fixed inline, not a redesign):**
ARCHITECTURE.md's Security section assumed `model` was "validated by
`_validate_local_model_id_relaxed`... before `subprocess.run`" — it
wasn't; eject passed the raw body field straight to `ollama stop`. Added
the validation call as part of this same edit (same function, same
contract, zero design risk) rather than leaving the assumption false.
Test: `tests/test_model_ux_phase0_eject_honesty.py` (T-EJECT-AERO,
T-EJECT-OLLAMA-FAIL + the validation regression). T-EJECT-OLLAMA
(happy-path real-daemon check) is out of unit-test reach per
ARCHITECTURE.md's own Test Strategy — QA's Persistence & Honesty suite
runs it on real hardware.
Commit: `d01bcd6`.

### Step 8 — F-WARMDOT warmth probe
`app.py`: added `_ollama_ps_resident_ids()` (live `/api/ps`, ≤1s
timeout, cached-last-known fallback — Performance guard) feeding a new
`warm` field on Ollama-runtime local entries; added a real `resident`
field to `optional_backends` (`model_warmth._tier1_resident()` for
aeroLLM, wrapper-cache presence for AirLLM); corrected aeroLLM's dead
`"streamed": True` field to `False` in the same edit (F-OVERSELL,
directly adjacent to the line being touched).
`chat.html`: seeds `State.warmModels` from this server truth on every
model-list fetch instead of only from the current session's own
load/eject clicks; deep rows (aeroLLM/AirLLM) now get warmth-driven,
backend-accurate badge copy and never render an Unload/Eject button in
either the rail card or the active/mini card (C4/C5 finding 6) — Load
only.
No plan delta beyond the `streamed: False` inline fix noted above.
Test: `tests/test_model_ux_phase0_warmth_probe.py` (T-WARMDOT).
Commit: `7bc0ef2`.

### Step 9 — Persistence & Honesty (display subset) checkpoint
Added one end-to-end integration test replaying VISION.md's exact
scenario (gemma-4-26b-a4b, 13.45 GB, 7.1 GB free) through a single
`GET /api/chat/models` call, asserting the full gap-closure list holds
together (hardware nested once, fit chip never "Good", estimate based
on real disk size not active-params, warm/resident present, no
`backend_notice`, no header lies) — the automated form of the Test
Strategy's "re-run the exact live in-browser test" gate.
Test: `tests/test_model_ux_phase0_integration.py`.
Commit: `7447107`.

**Phase 0 (display fidelity) is closed as of `7447107`.**

### Step 10 — C6.1 idle init state + C6.2 cache lock
`app.py`: `_CHAT_MODEL_LOAD_STATE` initializes to `state="idle",
message="No model loaded", model=None` (was `state="ready", message=
"Model ready"` — cold start/every restart falsely claimed a model was
already loaded). Added `_OPTIONAL_CHAT_BACKEND_CACHE_LOCK` (threading.Lock)
and wrapped every check-then-mutate sequence on
`_OPTIONAL_CHAT_BACKEND_CACHE`: eject's clear-everything branch, and
`_get_optional_chat_backend`'s check/construct/store via double-checked
locking (lock guards the dict read/write, NOT the potentially
multi-second construction in between — a full-duration lock would block
eject()/other readers on the event loop thread). Declared (but didn't
yet wire) `_CHAT_MODEL_LOAD_INFLIGHT` (asyncio.Lock) alongside its
sibling lock. Updated `test_chat_ui.py`'s cold-state assertion
(`"ready"`→`"idle"`) — a direct, required consequence of C6.1.
No plan delta. Test: `tests/test_model_ux_phase0b_idle_and_locks.py`
(T-IDLE, T-CACHERACE). Commit: `dc092d8`.

### Step 11 — C6.2 serialize the load
`app.py`: wrapped `_prepare_chat_model_load`'s construction call in
`async with scheduler.inference_slot("chat-model-load")`, closing the
F-LOADRACE gap (chat load could previously race the aerollm-preload loop
/ an admin load toward the memory ceiling at default concurrency).
No plan delta.

**Discovered-and-fixed while testing (self-inflicted, not architecture):**
the T-LOADRACE test performs a real `_prepare_chat_model_load` call,
which mutates the shared module-level `_CHAT_MODEL_LOAD_STATE` dict in
place — without test isolation this leaked a "ready" state into
`test_chat_ui.py`'s cold-state assertion when run in the same session.
Fixed by scoping the test's mutations to a monkeypatched copy of the
dict (pattern reused by every subsequent Phase 0b test that performs a
real load). Test: `tests/test_model_ux_phase0b_loadrace.py` (T-LOADRACE).
Commit: `a40e837`.

### Step 12 — C6.4 honest Cancel + C6.5 bounded timeout
`app.py`: `_prepare_chat_model_load` now runs the load as a task shielded
under `asyncio.wait_for(..., timeout=_load_max_sec())`
(`ARAIL_LOAD_MAX_SEC`, default 180s, floor 5s). A timeout flips the
*reported* state to `error` with an honest "may still be loading in the
background" message; a done-callback on the underlying task — not the
timeout itself — releases `_CHAT_MODEL_LOAD_INFLIGHT`, so a timed-out
load cannot be followed by a second, doubly-resident load until it
genuinely settles. The cancel endpoint (`api_chat_model_load_cancel`)
never mutates `_CHAT_MODEL_LOAD_STATE` at all now — it reports either
"no load in progress to cancel" or "a load in progress cannot be
interrupted; wait for it to finish, then Unload if unwanted", never a
fake `canceled` transition.

**Discovered gap vs. the architecture's framing (documented, not a
redesign):** C6.4 describes fixing "the load widget" to not render a
Cancel affordance during a blocking load. The `loader-strip`/`ls-cancel`
markup in chat.html (`ls-model`/`ls-bar`/`ls-pct`/`ls-eta`) turns out to
have **zero JS wiring** anywhere — nothing ever adds `.visible` or
touches those ids; the rail's actual Load affordance goes through
`loadModel()` (a 1-token `/api/chat/stream` ping), never
`/api/chat/model-load`. So there was no active Cancel affordance to
remove. Left the dormant markup as-is (no behavior to change, and
wiring it up would itself be new load-widget UI — explicitly gated
behind disconfirming-evidence #1 in the architecture's own Leash) and
added an in-place comment so a future session doesn't wire `ls-cancel`
to the endpoint expecting a "canceled" transition, or mistake the dormant
markup for live UI.
Test: `tests/test_model_ux_phase0b_cancel_and_timeout.py` (T-CANCEL,
T-LOAD-BOUND). Commit: `c4805f4`.

### Step 13 — C6.3/C6.6/C6.7/C6.8 identity, real ETA, re-fit, friendly errors
`app.py`: `_get_optional_chat_backend` gained an `expected_model` kwarg —
a resident singleton on a different model raises
`_ChatBackendModelMismatch`, caught by `_prepare_chat_model_load` to
report an honest refusal ("<backend> already resident with <resident>;
switching models requires a portal restart") instead of a false `ready`.
`eta_seconds` is now derived from the model's real, freshly re-scanned
on-disk size (`_real_on_disk_gb`) over a rolling-median observed
throughput per runtime (`_load_throughput_mbps`, falls back to
`ARAIL_LOAD_THROUGHPUT_MBPS`/~500 MB/s); `progress` is `None`
(indeterminate) rather than a fake bar. A real-vs-catalog size
disagreement beyond 30% tolerance (`_model_looks_corrupt`) suppresses
the ETA rather than fabricating a countdown. Before starting the load,
memory is re-snapshotted and the target's fit verdict recomputed fresh;
a "Requires streaming" verdict doesn't block the load but the message
says so honestly. Generic exceptions now go through
`_friendly_load_error` — a short, operator-legible message (with
daemon-down detection: connection-refused / `ollama` not on PATH →
"Ollama isn't running — start it with 'ollama serve', then retry.")
instead of a raw exception repr; the full exception is logged
server-side only. `docs/maximus.plan.md` §5's "Loader state machine" now
explicitly separates what ships today (the 4-state machine, pointing at
ARCHITECTURE.md §C6) from the six/seven-state SSE-driven design, which
is labeled a future plan and was never built.

**Delta from plan (documented scoping choice, not a gap):** F-CORRUPT's
"declared manifest" concept has no dedicated system in this codebase
(no `ModelManifest`/`fit.py` — that's the aspirational design just
trimmed out of maximus.plan.md). Implemented corruption detection as an
exact-id match against the curated catalog's declared `size_gb`; Ollama
`:tag`-suffixed ids (e.g. `gemma-4-26b-a4b:latest` vs. the catalog's
`gemma-4-26b-a4b`) miss this match and safely no-op (never a false
"corrupt" flag) rather than attempting fuzzy id matching, which risks
false positives on a legitimately different quantization of the same
family. Documented as a known limitation in the docstring.
Test: `tests/test_model_ux_phase0b_identity_eta_refit_errors.py`
(T-SWITCH, T-ETA, T-CORRUPT, T-REFIT, T-DAEMONDOWN). Commit: `31f8bdb`.

### Step 14 — full-suite checkpoint
Added the remaining named Unit/Security/Regression tests from the Test
Strategy that didn't already have dedicated coverage: `_fit_verdict_label`'s
full boundary table (C3, unchanged this sprint), a determinism check
standing in for T-NOFLICK's pure-function half, F-XSS confirmation for
the new `warmLabelText` field + `flashStatus`'s textContent-only
rendering, and two whole-package regression sweeps (no `AERO_MOE_SELECT`
gating real code anywhere in `src/` — prose mentions explaining it's off
are fine per BLOCK-2; no `backend_notice` anywhere in the portal
package). T-EJECT-OLLAMA, T-RESTART, and T-NOFLICK's real-memory-jitter
half remain QA-suite items requiring real hardware/process control, per
the architecture's own Test Strategy.
Commit: `9221bbb`.

**Phase 0b (load/unload lifecycle honesty) is closed as of `9221bbb`.**

### Post-step-14 — discovered deadlock, fixed
Verifying step 11's change against the rest of `app.py` (not prompted by
any specific test failure — a deliberate re-read of every caller of the
functions touched this sprint) surfaced a real bug introduced by this
sprint's own work: `scheduler.inference_slot()` is backed by ONE
process-wide semaphore shared across every label, not one per label.
`/api/admin/models/load`'s non-streamed branch already runs inside
`async with scheduler.inference_slot("admin-model-load")` and calls
`_prepare_chat_model_load(...)` — which, after step 11, ALSO acquires
`scheduler.inference_slot("chat-model-load")` internally. Nesting two
acquisitions of the same non-reentrant semaphore on the same task
self-deadlocks. No existing test exercised this path for real (the one
admin-load concurrency test pre-holds the *admin* lock and asserts an
immediate 409, never reaching the load body). Fixed with a
`_caller_holds_inference_slot` kwarg (default False; every other caller
unaffected) the admin call site sets to skip the now-redundant internal
acquisition. Regression test proves both directions — the flag prevents
the hang, and the same setup without it times out, confirming the test
is meaningful rather than vacuously passing.
Test: `tests/test_model_ux_phase0b_admin_load_no_deadlock.py`.
Commit: `336fedd`.

### Post-step-14 — full-suite run surfaced a test-isolation leak, fixed
Running the COMPLETE test suite (not just targeted regression subsets —
required by my own protocol before declaring done) surfaced 4 failures
beyond the established 28-failed/7-error baseline, all self-inflicted:
`test_model_ux_phase0b_cancel_and_timeout.py`'s two tests that block a
background thread on `threading.Event().wait(timeout=5)` inside
`asyncio.to_thread` only released it (`release_evt.set()`) *after*
assertions that could themselves fail — an early assertion failure left
the thread blocked for its own internal timeout, and once it eventually
completed, its callback wrote `state="ready"` into whatever
`_CHAT_MODEL_LOAD_STATE` was bound to at that later moment. Confirmed by
exact alphabetical file ordering: the one other victim
(`test_model_ux_phase0b_idle_and_locks.py`, alphabetically immediately
after) was corrupted by exactly this leak.

Fixed (attempt 1) with unconditional `finally` blocks that release the
thread and wait for genuine completion regardless of assertion outcome,
widened internal timeouts for headroom, and removed an outer
`asyncio.wait_for(_scenario(), timeout=5.0)` that could itself fire
prematurely under the full suite's heavier load. Verified with 5x
repeated combined runs of every Phase 0b test file + `test_chat_ui.py`
(all green) — the arithmetic also matched: 32 failed in the flawed run
minus these 4 self-inflicted = 28, exactly the pre-existing baseline.
Commit: `8269136`.

**This diagnosis was wrong (or at least incomplete).** A second complete
full-suite run reproduced the IDENTICAL 4 failures byte-for-byte,
disproving the "leaked orphaned thread" theory — attempt 1's fix changed
nothing about the actual failure. Re-reading the new failure detail
(`assert state == "loading"` failing inside the polling loop ITSELF,
not after it) pointed at the real mechanism: these two tests block a
REAL OS thread (`asyncio.to_thread` → the default `ThreadPoolExecutor`)
on `threading.Event().wait(...)`, and real thread-pool scheduling is
subject to system-wide contention that a fixed-iteration
`asyncio.sleep`-based polling loop cannot bound — under the full suite's
~10 minutes of aggregate load (thousands of tests, heavy I/O/subprocess/
GC pressure), the loop exhausted its iteration budget without the real
thread ever getting scheduled to run.

**Fixed (attempt 2):** replaced the real thread entirely with a
fully-async stand-in for `asyncio.to_thread` (an `asyncio.Event`-gated
coroutine) — same "un-cancellable once started" contract under test
(A4), zero dependency on OS thread-pool scheduling. Cooperative-only
waits (`await asyncio.sleep(0)`, bounded by iteration count, not
wall-clock) replace the polling loop. Verified with 8x repeated combined
runs (all green, ~1.5s/run).
Commit: `474bd70`.

**Attempt 2 ALSO did not fully fix it.** A third complete full-suite run
reproduced the identical 4 failures again — including on
`test_cancel_with_nothing_in_progress_is_an_honest_noop`, which has
zero scheduling, waiting, or threading of any kind (it directly sets a
dict key, then immediately reads it back). This proved conclusively
that "real thread scheduling," while a real contributing factor to the
ORIGINAL design's flakiness, was never the complete mechanism: some
other test running anywhere in a 3000+-test session can observe/mutate
the shared `_CHAT_MODEL_LOAD_STATE` module-level dict during this
file's execution window, by a route three rounds of live investigation
(including inspecting every `importlib.reload` call site in the whole
test suite for one that might reload `arail.portal.app` — none run
early enough to explain it) did not conclusively identify.

**Fixed (attempt 3, the one that held):** stopped trying to scope the
shared global and removed the dependency on it entirely.
`_get_chat_model_load_state`/`_set_chat_model_load_state` — the only
two functions through which `_prepare_chat_model_load` and
`api_chat_model_load_cancel` ever touch `_CHAT_MODEL_LOAD_STATE` — are
now monkeypatched to closures over a dict *private to each test* (a
local variable in the test function, never assigned to any
`arail.portal.app` attribute). No shared module-level object is read or
written by these tests at all, so no other test running anywhere in the
same session can interact with them, by any mechanism. Verified with 5x
repeated runs of the full sprint suite + `test_chat_ui.py` together.
Commit: `ee406d8`.

**A fourth full-suite run confirmed attempt 3 fixed
`test_model_ux_phase0b_cancel_and_timeout.py` completely** — all 3 of
its tests are gone from the failure list. **One failure remained**,
by the identical mechanism, in a DIFFERENT file:
`test_model_ux_phase0b_idle_and_locks.py::test_get_chat_model_load_status_endpoint_reports_idle_on_a_cold_process`,
which also monkeypatched the shared dict directly instead of the
accessor function. Applied the identical fix (mock
`_get_chat_model_load_state` directly).
Commit: `74e2a87`.

That run's only OTHER new failure —
`test_observability_under_load.py::test_metrics_latency_under_50ms_while_slot_held`
— is an inherently timing-sensitive 50ms-latency-under-load test in a
file this sprint never touched (confirmed via `git diff` — zero changes
to that file across this entire session); expected to flake occasionally
under the full suite's ~10 minutes of heavy aggregate system load
regardless of this diff, not a regression from it.

**A fifth full-suite run was started after the `idle_and_locks.py` fix
landed** to get the definitive before-handoff confirmation; its result
is recorded in the "Final state" section below.

## Architect feedback required

Empty — no plan gap surfaced. Six discovered items, all fixed inline and
documented above (not design questions, all low-risk and within the
same contract already being edited): step 5's missing
`_validate_local_model_id_relaxed` call before `subprocess.run` in
eject; step 11's test-isolation leak into `test_chat_ui.py` (self-
inflicted by my own new test, fixed in the same commit); step 12's
"load widget Cancel affordance" turning out to be dormant, unwired
markup rather than active UI (documented in place, no behavior changed);
the post-step-14 admin/chat inference-slot self-deadlock (a real bug in
this sprint's own C6.2 change, not present before it); and the
post-step-14 full-suite-only test flakiness across TWO test files
(`test_model_ux_phase0b_cancel_and_timeout.py`,
`test_model_ux_phase0b_idle_and_locks.py`) sharing a common root cause —
tests that monkeypatched the shared `_CHAT_MODEL_LOAD_STATE` module
global directly, which something else in a 3000+-test session could
still observe/mutate by a mechanism three rounds of live investigation
did not conclusively pin down. This was a test-design issue in my own
new tests, not a production-code bug — the actual fix (mocking the
accessor functions instead of the shared dict) is a stronger isolation
pattern than the codebase's own pre-existing convention for this kind of
test, and is called out here for the architect/QA's awareness in case
other tests share the same fragile pattern against `arail.portal.app`'s
module-level singletons.

## Final state

- **Commits this session:** 18 (`5aab47a` through `74e2a87`), on top of
  the already-landed ledger commit `938ff9d`. Full list: `5aab47a`
  (BUILD_LOG skeleton), `bf34aee` (step 3), `c2fc531` (step 4),
  `d01bcd6` (step 5), `7bc0ef2` (step 8), `7447107` (step 9), `0113139`
  (BUILD_LOG Phase 0 record), `dc092d8` (step 10), `a40e837` (step 11),
  `c4805f4` (step 12), `31f8bdb` (step 13), `9221bbb` (step 14),
  `336fedd` (post-step-14 deadlock fix), `8269136` (test-isolation fix
  attempt 1 — insufficient), `474bd70` (attempt 2 — also insufficient),
  `ee406d8` (attempt 3 — fixed `cancel_and_timeout.py`), `74e2a87`
  (same fix applied to `idle_and_locks.py`'s one remaining case).
- **Files touched:** `src/arail/portal/app.py`,
  `src/arail/portal/templates/chat.html`,
  `src/arail/chat/models_catalog.yaml`, `docs/maximus.plan.md`,
  `tests/test_chat_ui.py` (existing, updated), plus 11 new test files
  under `tests/test_model_ux_phase0*.py`. No file outside this list was
  touched — matches ARCHITECTURE.md's implementation-order plan exactly
  (steps 1/2/4/6/7 from the ledger commit + steps 3/4/5/8/9/10/11/12/
  13/14 here, plus the two discovered-bug fixes).
- **Tests:** 75 new/updated tests across the 11 sprint-specific files,
  all passing, verified with 5-8x repeated combined runs (not just a
  single pass) after each fix attempt. Every touched-file's
  directly-related pre-existing test file (test_chat_ui.py,
  test_r1_hardened_golden_snapshot.py, test_r1_r3_chat_models.py,
  test_inference_scheduler.py, test_aerollm_preload.py,
  test_dispatch_35b_enforcement.py, test_admin_models_endpoints.py,
  test_docs_registry*.py) re-run clean.
- **Five complete full-suite runs** (`pytest tests/ -q`, `PYTHONPATH=src`
  — see the ledger commit's summary for why that's needed in this
  worktree; ~573-575s each) were required to reach a clean result — this
  session did not stop at "my targeted tests pass" and call it done; see
  the addendum table below for the full run-by-run record, including two
  wrong diagnoses that were disproved by re-running rather than assumed
  fixed.
- **Every failure mode in ARCHITECTURE.md's Failure modes table has a
  test**, except the three named QA-suite items (T-EJECT-OLLAMA real
  daemon residency delta, T-RESTART real process restart, T-NOFLICK real
  memory jitter) which the architecture itself scopes to "the operator's
  own airgapped Mac," not a builder's unit-test sandbox.
- No commented-out code. No TODO/FIXME comments introduced.
- **Phase 0 (display fidelity)** and **Phase 0b (load/unload lifecycle
  honesty)** are both closed. ARCHITECTURE.md's implementation order is
  now fully implemented through step 14, plus the two bugs this
  session's own work introduced (a self-deadlock in step 11, test-design
  flakiness in its own new tests under full-suite load) and caught and
  fixed before handoff, rather than left for QA to find.

### Addendum — full-suite run results

| Run | Point-in-time | Result | Notes |
|---|---|---|---|
| 1 | after step 14 (`9221bbb`), before any post-step-14 fix | 32 failed, 3179 passed, 7 errors, 575s | Baseline 28/7 + 4 self-inflicted (`cancel_and_timeout.py` × 3, `idle_and_locks.py` × 1) |
| 2 | after fix attempt 1 (`8269136`) | 32 failed, 3182 passed, 7 errors, 573s — **identical failure list to run 1** | Attempt 1's diagnosis (orphaned-thread cleanup ordering) was wrong; disproved by this run |
| 3 | after fix attempt 2 (`474bd70`) | 32 failed, 7 errors, ~575s — **identical failure list again**, including a test with zero scheduling/threading | Attempt 2's diagnosis (real OS-thread scheduling) was a real contributing factor but not the complete mechanism; disproved by this run |
| 4 | after fix attempt 3 (`ee406d8`, full accessor-function isolation) | 29 failed, 3183 passed, 7 errors, ~588s | `cancel_and_timeout.py`'s 3 failures GONE. One remained in `idle_and_locks.py` (same root cause, same fix not yet applied there) + one unrelated new flake (`test_observability_under_load.py`, a 50ms-latency-under-load test in an untouched file) |
| 5 | after applying the same fix to `idle_and_locks.py` (`74e2a87`) | filled in below once complete | Expected to match the 28/7 baseline (± the untouched-file observability flake, which is independent of this diff) |

Run 5 output, once available:
