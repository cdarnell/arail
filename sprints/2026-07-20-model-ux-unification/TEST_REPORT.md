# Test report: Model selection UX — unified-list fidelity, disclosed honestly

**Date:** 2026-07-20
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `692b460` (branch `qukaizen/model-ux-unification`)
**Review:** [REVIEW.md](./REVIEW.md) — WEAK_PASS, zero BLOCK (QA proceeds)
**Verdict:** WEAK_PASS

QA weighted per the mandate toward the two things that have broken user
trust in this codebase historically:
**(a)** does displayed memory/fit information match reality under real
conditions (cold start, warm, near-OOM), verified against actual system
state — live `psutil.virtual_memory()` and the live `ollama ps` / `/api/ps`,
not "the UI didn't throw"; **(b)** does every Unload button actually free
memory for every model type the UI offers one on, verified against the
**live ollama daemon** (memory really drops off `/api/ps`).

New tests are real pytest, matching repo conventions, in
`tests/test_qa_model_ux_memory_and_eject_fidelity.py`. The two real-daemon
tests (`T-EJECT-OLLAMA` / real warmth) that BUILD_LOG deferred as
"out of unit-test reach" **actually executed** here against a live daemon
(`ai-engineer:latest` resident throughout, never evicted; disposable
`llama3.2:1b` loaded and ejected).

## Test inventory

| # | Test | Category | Covers | Status |
|---|---|---|---|---|
| 1 | `test_memory_snapshot_free_matches_live_psutil_within_tolerance` | (a) real-mem fidelity | `_local_memory_snapshot().free_gb` within ±2 GB of live `psutil.available`; not 0/total/constant | PASS |
| 2 | `test_api_chat_models_hardware_free_matches_live_psutil` | (a) real-mem end-to-end | `compact.hardware.free_gb` is a real reading inside a live-psutil envelope; top-level `hardware` deleted | PASS |
| 3 | `test_no_good_fit_chip_on_any_real_row_that_exceeds_free_memory` | (a) F-FAKEFIT invariant | On the REAL installed list: no `Good` where `estimated_vram_gb > free_gb` | PASS |
| 4 | `test_near_oom_fit_is_honest_using_real_free_memory` | (a) near-OOM | Anchored to machine's real free: 2×free→Requires streaming, 1.05×→never Good, 0.5×→Good | PASS |
| 5 | `test_psutil_import_failure_never_fabricates_optimistic_free_memory` | (a) F-FALLBACKLIE | Real darwin sysctl fallback: `free_gb=0`≠`total_gb`, verdict Unknown | PASS |
| 6 | `test_warmth_probe_matches_live_ollama_ps_exactly` | (a) warm, live daemon | `_ollama_ps_resident_ids()` == live `ollama ps` set (screen-vs-terminal) | PASS |
| 7 | `test_installed_but_cold_ollama_row_is_not_marked_warm` | (a) warm/cold, live daemon | Cold installed row warm=False; resident row warm=True — vs live `/api/ps` | PASS |
| 8 | `test_rail_eject_button_is_offered_on_every_nondeep_runtime` | (b) surface enumeration | Rail eject gate is isDeep+warm only — every non-deep runtime gets an Unload button | PASS |
| 9 | `test_eject_endpoint_never_reports_false_success_for_any_ui_runtime` | (b) honesty contract | mlx/mlx-openai/cpu/cuda → ok:false+requires_restart (never false success) | PASS |
| 10 | `test_mlx_openai_unload_button_cannot_free_memory` | (b) finding surface | Endpoint honest ok:false, but button rendered on a type it cannot free | PASS |
| 11 | `test_ollama_unload_button_actually_frees_memory_on_live_daemon` | (b) **real eject** | Load `llama3.2:1b` resident → eject via endpoint → **gone from live `/api/ps`** | PASS |
| 12 | `test_eject_ollama_rejects_injection_before_any_subprocess` (×6 payloads) | security | Injection/traversal/oversized/newline ids rejected before `subprocess.run` | PASS |
| 13 | `test_eject_ollama_passes_model_as_argv_not_shell_string` | security | Validated id reaches `["ollama","stop",model]`, `shell=False` | PASS |
| 14 | `test_hon1_rail_eject_clears_warm_dot_before_checking_ok` | (b) regression | Pins HON-1: rail eject clears warm dot before `d.ok` check | PASS |

**New file:** 19 test cases, **19 passed**. Existing sprint suite +
directly-related pre-existing files (`test_chat_ui`, `test_chat_model_sync*`,
Phase-0/0b files): **125 passed** together. Full suite run below.

## Failures

No new-test failures. No sprint-caused failures. Findings (not test
failures) that answer the mandate:

| # | Finding | Symptom | Minimal repro | Severity |
|---|---|---|---|---|
| QA-1 | **Unload button offered on model types it cannot free.** The rail eject affordance is gated only by `isDeep` + warmth — so mlx / mlx-openai / cpu / cuda rows render an eject button titled "Free this model from VRAM/RAM," but `/api/chat/eject` for those runtimes returns `ok:false, requires_restart:true, freed:[]` (it genuinely cannot hot-free them in-process). The **endpoint stays honest**, but the button over-promises on the exact surface this sprint owns. Answer to mandate (b): only the **Ollama** Unload button actually frees; the others cannot. | `POST /api/chat/eject {"runtime":"mlx-openai"}` → `ok:false` while `chat.html:3367-3371` still renders the eject button for that warm row | Test #10, #9 | Medium |
| QA-2 | **HON-1 (already filed, REVIEW.md #2) amplifies QA-1.** Rail-card eject does `State.warmModels.delete(m.id)` unconditionally (`chat.html:3401`) *before* checking `d.ok` (`:3402`). On a runtime whose eject returns `ok:false` (QA-1, or a failed `ollama stop`), the warm dot flips to cold anyway — a looks-freed dot on a model that was **not** freed, while the flash simultaneously says "eject failed:". Self-correcting on next `/api/chat/models` probe. The active-card path already gates the delete on `d.ok` (`:3577`); the rail path should match. | Any `ok:false` eject on a warm rail row | Test #14 | Low |

Neither is a failing test; both are honesty gaps on the Unload surface,
filed as dated follow-ups (below). QA-2 was already accepted by the review
as a dated follow-up; QA-1 is a QA-surfaced extension of the same class the
sprint's own thesis targets ("no lying/over-promising unload buttons") and
should join the same ticket.

**Recommendation (builder):** mirror the deep-row treatment — render the
eject affordance only for runtimes the endpoint can actually free
(`ollama`), and gate the rail-card `warmModels.delete` on `d.ok`. Both are
small, local edits; neither blocks merge.

## Security review

| Surface | Checked | Findings |
|---|---|---|
| User input (eject `runtime`/`model`) | `runtime` lower-cased, matched to a fixed branch set (no free-form use). `model` for ollama gated by `_validate_local_model_id_relaxed` (rejects `..`,`/`,`\`, >256 chars, and any id not in the installed/scan allowlist) **before** any subprocess. Verified rejection precedes `subprocess.run` via a tripwire across 6 injection/traversal/oversized/newline payloads (test #12). | Clean |
| Command injection | Eject subprocess is `subprocess.run(["ollama","stop",model], …)` — argv list, **no `shell=True`** (verified: the three `shell=True` sites in app.py are unrelated pre-existing diagnostics endpoints at lines 4801/4881/4978, not on this sprint's surface). Validated id reaches argv as a discrete element (test #13). | Clean |
| Network I/O (SSRF) | `_ollama_ps_resident_ids()` hits a hardcoded `127.0.0.1:11434/api/ps`, no user-controlled URL, ≤1 s timeout, last-known fallback. `_local_memory_snapshot` runs fixed-argv `sysctl`/`nvidia-smi`. | Clean |
| XSS | New rail fields go through `escapeHtml`: `verdict` (`chat.html:3358,3427`), `warmLabelText` (`:3360`). Server `notes` surface via `flashStatus` (textContent). | Clean |
| Deserialization / Crypto / Auth / New deps | No deserialization of untrusted input, no crypto, no auth change, **no new dependency** (confirmed vs `main...HEAD` diff — only `app.py`, `chat.html`, `models_catalog.yaml`, `router/backends.py`, `docs`, tests). | Clean |

## Performance

N/A — not a hot path (per ARCHITECTURE §Performance). The one added
request-path probe (`ollama ps`) is behind a ≤1 s timeout with last-known
fallback (verified present, `app.py:8587`); the `compact.hardware` re-key is
O(1). No benchmark required or run. Observed side note: `GET
/api/chat/models` transiently allocates a few GB during a cold call
(gallery/catalog/model_specs import); the memory snapshot it renders is a
real mid-request `psutil` reading (test #2 brackets it), not a regression —
but see Notes.

## Full-suite run

`pytest tests/` (PYTHONPATH=src): **28 failed, 3198 passed, 1 skipped,
1 xfailed, 7 errors, 602 s.**

Attribution — none of the 28 failures / 7 errors are caused by the sprint or
by these QA tests:

- **New QA file:** 0 failures in the full suite; all 19 pass in isolation
  and when run immediately before `test_chat_ui`/`r1_snapshot` (no state
  pollution).
- **Sprint-touched test files** that appear in the full-suite failure list
  (`test_chat_ui::…compact_selector_payload`,
  `test_r1_hardened_golden_snapshot::…model_load_has_required_keys`)
  **pass in isolation** → the documented order-dependent shared-global
  (`_CHAT_MODEL_LOAD_STATE`) flakiness the BUILD_LOG spent three attempts
  on; a pre-existing test-isolation weakness, not a code regression.
- **Other failures** are in files the sprint never touched (`world_forge`,
  `build_tab`, `opencode_*`, `swarm_goal`, `dashboard_layout`,
  `token_compliance`, `shell_source_safety`, `cache_prewarm`, …) or are
  **machine-dependent**: `test_aerollm_defaults` fails even in isolation
  because it hardcodes a memory expectation (`19,327,352,832` bytes) that
  doesn't match this 36 GB host (`got 16,092,557,312`) — the sprint diff
  does not touch kv_budget. Consistent with the BUILD_LOG's documented
  "~28 pre-existing failed / 7 error" baseline that varies run-to-run.

## Coverage delta

pytest-cov is not installed in this env, so no line-count delta. Qualitative:
every changed function on the two mandated surfaces is exercised against
**real** system state — `_local_memory_snapshot` (both psutil and darwin
sysctl-fallback branches), `_fit_verdict_label` (near-OOM boundaries on real
free), `_ollama_ps_resident_ids` (live daemon), `_build_local_model_entry`
(warm true/false vs live `/api/ps`), and `api_chat_eject` for every runtime
branch the UI can render an eject button on, plus the real `ollama stop`
happy path end-to-end. The one path not machine-reachable here is the CUDA
`nvidia-smi` branch of `_local_memory_snapshot` (Apple-Silicon host).

## Notes for the next QA pass

- **QA-1 is the crisp answer to "does every Unload button free memory":
  no — only Ollama's does.** The fix (gate the affordance to freeable
  runtimes + gate the warm-dot delete on `d.ok`) is the natural closure of
  this sprint's own "no over-promising buttons" thesis and should ship with
  HON-1.
- **Under-tested here:** the CUDA `nvidia-smi` memory path (no CUDA host);
  a real near-OOM squeeze (I anchored to real free memory arithmetically
  rather than actually exhausting 36 GB) — a Linux/CUDA box or a
  memory-pressure harness would close both.
- **Shared-global fragility persists.** `_CHAT_MODEL_LOAD_STATE` and
  `_OPTIONAL_CHAT_BACKEND_CACHE` are module-level singletons that tests
  mutate; the BUILD_LOG isolated two files but the pattern (full-suite-only
  flakiness on `test_chat_ui`/`r1_snapshot`) still bites. A fixture that
  snapshots/restores these globals per test would retire a recurring source
  of noise for future sprints.
- **Real-daemon tests skip cleanly** when ollama is absent, so CI stays
  green; they run for real on an operator machine, which is where this
  sprint's trust claims actually live.
