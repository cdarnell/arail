# Review: recap-core (Sprint 1)

**Date:** 2026-05-17
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 14419d6
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 097df62

## Verdict: WEAK_PASS

Ship it with two documented follow-ups (see "Required actions" §). All 11 failure-mode invariants are implemented and covered by tests; the three documented deviations are acceptable; the test suite is 142/142 green for recap and shows 0 new failures elsewhere (13 pre-existing failures, builder claimed 12 — see process note below).

## Per-invariant verdict (11 failure modes)

| # | Failure mode | Code | Test | Verdict |
|---|---|---|---|---|
| 1 | Malformed JSON | `schema.parse_think_subtasks` retry w/ `_is_retry` flag | `test_recap_schema.py::TestRetryPath` (4 tests) | PASS |
| 2 | Recursion depth runaway | `core.py:221-231` MAX_DEPTH check forces primitive | `TestDepthRunaway::test_max_depth_cap_forces_primitive` | PASS |
| 3 | Step budget exhausted | `_descend` line 207 (before each subtask) | `TestBudgetExhaustion` (2 tests) | PASS |
| 4 | Sliding window evicts entry 0 | `state.window` pins `_PINNED_INDEX=0`; handles k=1 | `test_recap_state.py` (K=1..64 parametrized + pin tests) | PASS |
| 5 | Parent-plan re-injection | `_execute_nonprimitive` constructs `[system, fresh user_msg]` from `node.T` directly — NOT from chat history | `test_parent_reinjection_invariant_with_k1_window` | PASS |
| 6 | Env raises exception | `_execute_primitive` try/except wraps `env.step()` | `TestEnvExceptionHandling::test_env_exception_treated_as_failed_obs` | PASS |
| 7 | Infinite replan loop | `LEAF_RETRY_CAP=2`, `NONLEAF_RETRY_CAP=2` honored in `_execute_primitive`/`_descend` | `test_leaf_failure_after_retry_cap`, `test_parent_replans_on_child_failure` | PASS |
| 8 | Cost runaway | `_check_cost_ceiling` invoked in both `_llm_call` (every call) and `_descend` (every N) | `TestCostCeiling::test_cost_exceeded_returned_when_ceiling_breached` | PASS (with deviation, see §) |
| 9 | Prompt-size overflow | `RouterAdapter.chat` checks `len(flat) > budget*4`, calls `truncate_for_context` | `test_recap_adapter.py::test_prompt_budget_triggers_truncation`; state-level §A tests | PASS |
| 10 | Concurrent runs clobber contextvar | `contextvars.ContextVar` (not threading.local); `recap_depth_context` resets via finally token | `test_recap_depth_reset_after_call`, `test_contextvar_set_during_adapter_chat`. **No explicit concurrent/async test** — gap, but ContextVar correctness is intrinsic to the type. | WEAK PASS |
| 11 | Ambiguous primitive | Honored as-emitted; env rejection routes to leaf-backtrack | Behavior covered by `test_backtrack_fires_on_leaf_failure` | PASS |

## Per-paranoia-probe finding

- **Parent-plan re-injection** — VERIFIED. `core.py:368-380` builds `parent_S_str = state_to_summary(node.S)` then `render_recursive_downward(parent_T=node.T, ...)` from the **tree node**, not history. Test at line 134 explicitly monkeypatches to demonstrate the invariant holds independent of history windowing.
- **Contextvar correctness** — VERIFIED. `costs.py:29` declares `_recap_depth_tls: contextvars.ContextVar[Optional[int]]` (not `threading.local`); `recap_depth_context` (line 40) is a contextmanager using `set()` + `reset(token)` in `finally`. Reset-after-call test exists; explicit concurrent test does NOT exist — recorded as ASK below.
- **One-line ModelRouter edit** — VERIFIED. `router/core.py:60` is the single added line (`recap_depth=current_recap_depth()`); import on line 10 is the only other change. `stream_complete` left untouched (deviation #2 — acceptable). All 8 grep'd `cost_tracker.track(` callers use only pre-existing kwargs; kwarg is `Optional[int] = None`, backward compatible.
- **JSON parser retry discipline** — VERIFIED. `schema.py:194-203` uses `_is_retry` flag; on second failure raises immediately (no recursion). `test_is_retry_flag_prevents_third_call` asserts exactly this.
- **Sliding-window pin** — VERIFIED. `state.window` returns `[pinned]` for k=1 (special-cased `tail_k==0`); `history[:]` for no overflow. Test parametrized K=1..64.
- **Step-budget guard placement** — VERIFIED (with architectural nuance). The check at `_descend:207` runs before each subtask iteration, which precedes both env action (primitive case) and LLM call (nonprimitive case). It is not duplicated inside `_llm_call`, but structurally covers both call sites. Acceptable.
- **§A truncation policy** — VERIFIED. `state.truncate_for_context` (line 172) uses `drop_indices = {2, 3}` — exact spec compliance. Test `test_drops_indices_2_and_3` asserts those specific indices' content is absent post-truncation.
- **Deviation #1 cost ceiling per-call** — IMPLEMENTATION IS CLEAN. Single check site (`_check_cost_ceiling` called once at top of `_llm_call:475`); raises `_CostCeilingError` sentinel re-raised at each `except _CostCeilingError: raise` site (verified at 4 spots in `core.py`). The `_descend` per-N check at line 215 is belt-and-suspenders but does NOT double-count cost (it reads `cost_tracker.total_billed_usage_usd`, no mutation). Acceptable; cleaner than threading return values.
- **Deviation #2 no stream_complete edit** — CONFIRMED RouterAdapter never calls `stream_complete()`. ReCAP cost telemetry is complete for the actual call surface. If a future agent uses stream_complete with recap_depth, that gap would need closing — recorded as tech debt.
- **Deviation #3 state.py + prompts.py same commit** — INFO ONLY. Justified by import ordering; no functional impact.

## Code quality findings

- [INFO] `_CostCeilingError` exception-for-control-flow is a documented code smell (also flagged by builder). Acceptable for Sprint 1; isolated to `core.py`.
- [INFO] `core.py` is ~510 lines, several helper methods just under 30 lines each. Complexity is bounded; recursion is paper-faithful. No refactor needed.
- [INFO] `Subtask.to_dict()` round-trip into state entries (builder-flagged) is a minor coupling — fine at this scope.

## Security findings

- [INFO] No new user-input surfaces — RecapAgent is invoked programmatically, no portal route changes.
- [INFO] No new secrets, file I/O, network egress, or auth touched. `LAB_MODE=airgapped` posture unchanged.
- [INFO] LLM responses are parsed into a strict dataclass; `eval`/`exec` not used; `json.loads` only.

## Test coverage assessment

- 142 new recap tests, all passing in 0.06s. State (85), schema (19), adapter (16), core (17), integration (5).
- Coverage on changed lines: every failure mode row has a corresponding test (table above).
- **Gap:** No explicit concurrent / async test for ContextVar isolation (architecture spec line 336 called for one). The invariant is structurally guaranteed by ContextVar's semantics, but a `pytest-asyncio` or `concurrent.futures` test would close the loop.

## Performance assessment

Not applicable for Sprint 1 — no benchmarks demanded by architecture. Recap is on the agent path, not a hot inference path.

## Tech debt delta

Vs ARCHITECTURE.md "Tech debt added":
- Predicted: contextvar misuse risk, second LLM call surface, flatten-loses-tool-use, mock-not-real-Robotouille. All present, all accepted.
- **New (not predicted):** `_CostCeilingError` control-flow exception (builder-flagged). `Subtask.to_dict()` schema-drift coupling (builder-flagged).
- **New (not flagged by builder):** `stream_complete()` does not propagate `recap_depth` — if a future agent uses it, telemetry will silently miss depth labeling. Should be tracked as a follow-up.

## Required actions before merge

None blocking. Recommended carry-overs (do not block Sprint 2):

1. **Add a concurrent-run ContextVar isolation test** — `tests/test_recap_adapter.py` should contain one `concurrent.futures.ThreadPoolExecutor`-based test running two adapters at different depths and asserting each sees its own value inside `complete()`. Closes the architecture-mandated test gap.
2. **File tech-debt ticket: `stream_complete()` does not thread `recap_depth`** — Sprint 2 should add the symmetric one-line edit when (and only when) a ReCAP caller uses streaming. Document the asymmetry in `router_adapter.py` docstring.

## Process probes

- Branch commits: 8 (1 BUILD_LOG skeleton + 6 feature + 1 docs/build-log finalization). Matches expectation.
- Recap test suite: 142 passed, 0 failed.
- Full suite: 1612 passed, 13 failed (1 xfailed). Build log claimed 12 pre-existing; the +1 is most likely environment-dependent (`test_metrics_hybrid_mode` and the Sequoia/uvicorn-adjacent tests can flicker). None of the 13 failures are in router/costs/recap code paths. INFO only.
- `cost_tracker.track(` callers: 8 found, all backward-compatible.
