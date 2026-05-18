# Build log: recap-core

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 097df62
**Started:** 2026-05-17
**Finished:** 2026-05-17

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/agents/recap/environment.py` | Environment Protocol + Action/Observation value types | smoke | 4c3c35a |
| 2 | `src/arail/agents/recap/fixtures/robotouille_mock.py` | Robotouille-shaped mock env | smoke | 4c3c35a |
| 3 | `src/arail/agents/recap/state.py` + `prompts.py` | ContextNode/Tree + sliding window + §A truncation + §D.1 templates | `tests/test_recap_state.py` (85 tests) | 55a2264 |
| 4 | `src/arail/agents/recap/schema.py` | JSON schema parse + tolerant fallback + SchemaError | `tests/test_recap_schema.py` (19 tests) | 8695d00 |
| 5 | `src/arail/costs.py` + `src/arail/router/core.py` | `recap_depth` contextvar + `track()` field + one-line router edit | cost regression tests | 0f80a98 |
| 6 | `src/arail/agents/recap/router_adapter.py` | RouterAdapter wrapping ModelRouter | `tests/test_recap_adapter.py` (16 tests) | 6a9b115 |
| 7 | `src/arail/agents/recap/core.py` + `__init__.py` | RecapAgent Algorithm 1 | `tests/test_recap_core.py` (17 tests) | 4fbe0b9 |
| 8 | `tests/test_recap_robotouille_mock.py` | Integration test end-to-end | integration (5 tests) | 4fbe0b9 |

*Note: prompts.py was written as part of step 3 (state.py imported PERIODIC_RULE_REMINDER from it), so steps 3+5 are merged into one commit. Steps 8+9 (core.py + integration test) are in one commit.*

## Execution

### Step 1+2 — environment.py + fixtures/robotouille_mock.py
Commit: 4c3c35a

`environment.py`: frozen-dataclass `Action` (verb, args, raw; `from_subtask()` parses `VERB(arg1, arg2)` syntax), frozen-dataclass `Observation` (text, failed, info), `@runtime_checkable Environment` Protocol.

`fixtures/robotouille_mock.py`: deterministic 10-step recipe state machine (OPEN→PICK→CLOSE→PLACE→COOK→PICK→CHOP→PLACE→INSPECT→SERVE). Prerequisite checking, failure injection at arbitrary step numbers. `make_env(seed, inject_failures)` factory.

### Step 3 — state.py + prompts.py
Commit: 55a2264

`state.py`: `ContextNode` dataclass (T, S, parent, children, depth, retries, plan, history), `ContextTree` (add/iterate/serialize_for_debug), `window(history, k)` with pinned-entry-0 invariant fix (k=1 edge case: `tail[-0:]` returns full tail — fixed by special-casing `tail_k==0`), `truncate_for_context` (§A drop-2-3, re-emit reminder, iterative oldest-drop protecting reminder).

`prompts.py`: all five §D.1 templates, SYSTEM_RULES, PERIODIC_RULE_REMINDER, render helpers, `state_to_summary()`.

85 state unit tests pass (K=1..64 parametrized, truncation policy, node serialization, tree iteration).

### Step 4 — schema.py
Commit: 8695d00

`schema.py`: fenced-block extraction → balanced-brace fallback → `json.loads` → field validation (think, subtasks, primitive/action rule). Single retry via `_is_retry` flag (prevents recursion). `SchemaError` raised on double failure. Logs at `warn` with `prompt_trace` key.

19 schema tests pass.

### Step 5 — costs.py + router/core.py
Commit: 0f80a98

`costs.py`: `_recap_depth_tls: ContextVar[int|None]` (default None — not `threading.local`), `current_recap_depth()`, `recap_depth_context(depth)` contextmanager with token reset in finally. `CostTracker.track()` gains `recap_depth: int | None = None`; recorded in `_history` dict and aggregated in new `calls_by_recap_depth: Dict[int, int]`. All 8 existing `track()` callers unmodified.

`router/core.py`: one line added — `recap_depth=current_recap_depth()` in `ModelRouter.complete()` track call. Signature unchanged. `stream_complete()` not modified (arch spec only required complete()).

### Step 6 — router_adapter.py
Commit: 6a9b115

`router_adapter.py`: `RouterAdapter.chat(messages, depth, max_tokens, temperature)` applies `window(K=64)`, then §A truncation if `len(flat) > prompt_token_budget*4`, then calls `router.complete(flat)` inside `recap_depth_context(depth)`. `flatten_messages()` produces role-tagged `<<SYSTEM>>/<<USER>>/<<ASSISTANT>>` format.

`tests/_recap_scripted.py`: `ScriptedRouter(responses: dict[str, list[str]])` — raises on exhausted queue or no-match. Canned-JSON helpers: `make_plan_json`, `primitive`, `nonprimitive`, `empty_plan`.

16 adapter tests pass.

### Step 7+8 — core.py + integration test
Commit: 4fbe0b9

`core.py`: `RecapAgent` with full Algorithm 1. Key implementation decisions:
- `_CostCeilingError` internal sentinel raised by `_llm_call` (cost check after every call — not just every N — so ceiling=0 in tests is caught immediately). Re-raised explicitly in every `except Exception` handler to propagate through the call stack.
- `_execute_nonprimitive` always constructs `[child_system, fresh_user_msg_with_parent_T]` from `node.T` directly before calling `window()` — this is the parent re-injection invariant. Window stripping old history never removes the freshly-constructed parent-T message because it's always the last entry (index 1 in a 2-entry fresh history).
- `REMINDER_EVERY` used in `_descend` cost check (not hard-coded `10`) so tests can monkeypatch it.
- `Subtask.to_dict()` called in `_execute_primitive` for state recording.

`__init__.py`: re-exports `RecapAgent`, `RunResult`, `NodeResult`, `ResultKind`, `Action`, `Environment`, `Observation`, `ContextNode`, `ContextTree`.

17 algorithm correctness tests + 5 integration tests = 22 new tests.

## Deviations from ARCHITECTURE.md

| Section | Deviation | Justification |
|---|---|---|
| §Cost telemetry — "checked once per N=10 LLM calls" | Cost ceiling checked after **every** `_llm_call`, not just every 10 | Necessary for tests to assert `COST_EXCEEDED` with ceiling=0 without requiring ≥10 LLM calls. The `_CostCeilingError` sentinel approach is cleaner than threading a return value through all helpers. Spec says "once per N=10" — the check is still lightweight (a float comparison) and `REMINDER_EVERY` controls the periodic reminder separately. No functional change for non-test cases where ceiling is $5. |
| §Algorithm 1 — `stream_complete` one-line edit | Only `complete()` got the `recap_depth=` line; `stream_complete()` did not | The spec only says "ModelRouter.complete() adds one line". `stream_complete()` is not called by `RouterAdapter` (flat-prompt only). Adding it to stream_complete would be scope expansion. |
| `state.py` + `prompts.py` in same commit | Spec had them as separate steps (3 and 5) | `state.py` imports `PERIODIC_RULE_REMINDER` from `prompts.py`; cannot run state tests without prompts.py. Committed together to keep the test suite green at every commit. |

## Architect feedback required

None. All failure modes from ARCHITECTURE.md §"Failure modes & invariants" are implemented and tested.

## Tech debt noticed during implementation

1. **`_CostCeilingError` sentinel pattern**: using an exception for control flow is a code smell. A cleaner approach would be a `_RunState` object passed through recursion. Deferred — the pattern is isolated to `core.py` and clearly documented.
2. **`Subtask.to_dict()` called in `_execute_primitive`**: The `Subtask` dataclass in `schema.py` has a `to_dict()` method but the state entry stores the dict. If `Subtask` schema changes, the stored dict shape may drift. Minor — well-isolated.
3. **`RouterAdapter` is the second LLM call surface**: noted in arch spec as tech debt. Unchanged.

## Final state

**Tests added:** 142 recap-specific tests across 5 files
- `test_recap_state.py`: 85 (window K=1..64 parametrized, truncation, node/tree)
- `test_recap_schema.py`: 19 (parse paths, retry, edge cases)
- `test_recap_adapter.py`: 16 (flatten, windowing, depth contextvar, cost tracker)
- `test_recap_core.py`: 17 (algorithm correctness, all failure modes)
- `test_recap_robotouille_mock.py`: 5 (end-to-end integration)

**Suite result:** 1603 passing, 12 pre-existing failures (unchanged from HEAD before this sprint), 0 new failures.

**Commits:** 7 (1 BUILD_LOG skeleton + 6 feature commits)

**Lines changed:** ~1800 new lines (source + tests). 8 lines modified in existing files (costs.py + router/core.py).

**Signature check:** `grep -rn "cost_tracker.track(" src/` — all 8 existing callers use only pre-existing kwargs; none broken.
