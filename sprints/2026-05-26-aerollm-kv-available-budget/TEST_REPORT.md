# Test report: aerollm-kv-available-budget

**Date:** 2026-05-26
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at e630c5d (revision pass head); QA tests at d940908.
**Branch:** `qukaizen/arail-kv-available-budget`
**Verdict:** **WEAK_PASS**

WEAK_PASS rationale: every test passes (existing 17 + tier 14 + 26 new
edge tests = 57 green) and there are no security or correctness
findings, but the live activity-feed acceptance test was deliberately
skipped because the dev box reported only ~8 GiB available RAM at QA
time and `project_oom_pressure.md` is an explicit no-go for triggering
a live 7B aerollm chat under those conditions. Activity-feed behavior
is fully covered by tests 14a/14b (positive-path emit body) and the
new parametrized all-sources emit test added in this QA pass; the
gap is "operator saw the line in the running portal," not "the code
path is unverified."

## Test inventory

| #  | Test | Category | Covers | Status |
|----|------|----------|--------|--------|
| Pre-existing | `tests/router/test_aerollm_kv_budget.py` (12 tests) | unit | resolver behavior matrix | pass |
| Pre-existing | `tests/router/test_aerollm_backend_budget_emit.py` (5 tests) | integration | singleton/emit/kwarg wiring + 14a/14b positive emit | pass |
| Pre-existing | `tests/test_aerollm_tier_resolution.py` (14 tests) | regression | tier resolution unaffected | pass |
| NEW E1 | `test_tie_total_vs_available_picks_either_but_is_int` | edge | exact tie between ceil_total and ceil_available | pass |
| NEW E2 | `test_raw_budget_exactly_equal_to_floor_does_not_trigger_floor` | edge | strict `<` check on floor branch (off-by-one) | pass |
| NEW E3 | `test_available_smaller_than_headroom_negative_ceil_triggers_floor` | edge | negative `ceil_available` cleanly hits floor | pass |
| NEW E4 | `test_available_greater_than_total_container_quirk` | edge | psutil container weirdness — must not crash | pass |
| NEW E5 | `test_tiny_box_4gib_floor_applies` | edge | 4 GiB / 2 GiB available → floor | pass |
| NEW E6 | `test_huge_box_512gib_no_overflow` | edge | 512 GiB / 400 GiB — int-typed, no overflow | pass |
| NEW E7-10 | `test_env_whitespace_is_stripped` (4) | edge | `"  0.5  "`, `"0.5\n"`, `"\t0.5"`, `"0.5\r\n"` | pass |
| NEW E11-14 | `test_env_exotic_numerics_accepted` (4) | edge | `0.5e0`, `.5`, `5e-1`, `+0.5` | pass |
| NEW E15 | `test_env_locale_comma_falls_back` | edge | `"0,5"` not a float() literal → default | pass |
| NEW E16 | `test_env_very_small_valid_pct` | edge | `"0.001"` valid but below floor → floor wins | pass |
| NEW E17 | `test_env_exactly_one_falls_back` | edge | strict `< 1.0` boundary | pass |
| NEW E18 | `test_env_exactly_zero_falls_back` | edge | strict `> 0.0` boundary | pass |
| NEW E19-22 | `test_emit_handles_all_sources` (4) | edge | default/env/floor/unavailable → info/info/warn/warn | pass |
| NEW E23 | `test_singleton_same_key_resolves_only_once` | regression | resolver+emit called exactly once across two ctor calls | pass |
| NEW E24 | `test_singleton_distinct_model_keys_each_emit` | regression | distinct AEROLLM_MODEL → both fire (per-model keying) | pass |
| NEW E25 | `test_emit_swallows_exception_and_logs_warning` | edge | REVIEW.md Finding D — narrow-except + `_log.warning` | pass |
| NEW E26 | `test_psutil_attribute_failure_falls_back_to_none` | edge | psutil imports but `.virtual_memory` attr raises | pass |

Test allocation: 22 edge / 0 happy / 4 regression of the new tests
(85% edge / 0% happy / 15% regression). Happy path is already saturated
by the 12 pre-existing unit tests; this QA pass deliberately leans
edge-heavy as instructed for this sprint (target 60/20/20). The pure
new-tests ratio overshoots edge weighting because builder coverage
already over-served happy.

## Test results

```text
$ python3 -m pytest tests/router/ tests/test_aerollm_tier_resolution.py -q
.........................................................                [100%]
57 passed in 0.04s

$ python3 -m pytest tests/router/test_aerollm_kv_budget_edges.py -v
26 passed in 0.03s

$ python3 -c "import arail.router.backends; from arail.activity import activity_log; print('ok')"
ok
```

No failures.

## Failures

None.

## Security review

| Surface | Checked | Findings |
|---|---|---|
| User input | `AEROLLM_KV_BUDGET_PCT` is the only env-var the resolver reads. Confirmed it is `.strip()`ped, `float()`-parsed inside try/except, range-checked `0.0 < pct < 1.0`, and out-of-range/garbage values fall back to default (never raise). Non-float DOS (e.g., `"1e100000"`) — `float()` returns `inf`; `inf < 1.0` is False → fallback. No untrusted-string path reaches the runtime kwargs. | None |
| File I/O | Resolver does no file I/O. Backend uses `ARAIL_MODELS_DIR` (operator-owned). No new path. | None |
| Network I/O | None. Resolver is pure CPU/memory introspection. | None |
| Deserialization | None. | None |
| Crypto | N/A. | None |
| Dependencies | psutil already a hard dep; no new deps added by this sprint. activity_log lazy-imported; `_log` is stdlib logging. | None |
| Logging | Confirmed `_log.warning("activity_log emission failed: %s", e)` does not log secrets — only the exception text from `activity_log.emit`. Reasoning dict contains memory numbers only (no tokens, no paths beyond `psutil.virtual_memory()` output). | None |

## Performance

N/A. Resolver runs once per process per model at first init. Two
psutil reads + ~10 arithmetic ops. Not on hot path.

## Live smoke

**Status:** SKIPPED on safety grounds.

- `psutil.virtual_memory()` reported `available=8.0 GiB` at QA time
  (machine total 36 GiB).
- The 7B Qwen weights for aerollm are ~5 GiB resident; a chat turn
  would push the resolver's own `ceil_available = 8*0.85 - 1.5 = 5.3 GiB`
  budget on top, plus portal overhead — within the band that has
  historically triggered OOM on this box per
  `~/.claude/projects/-Users-netsushi-ProJects-arail/memory/project_oom_pressure.md`.
- The acceptance path is **fully covered** by:
  - Test 14a (`test_emit_budget_activity_positive_path_info`): lets
    `_emit_budget_activity` body execute, asserts
    `activity_log.emit("aerollm", msg, level="info")` with
    `"KV budget resolved"` in the message.
  - Test 14b (positive-path warn for `source="floor"`).
  - New `test_emit_handles_all_sources` parametrized: exhaustive
    over the four source values.
  - REVIEW.md Finding A+B regression: the import path and call
    signature are both exercised end-to-end (not mocked away).
- Portal probe (`/api/chat/models`) at :8082 confirmed
  `deep.installed: true` — the deep backend is wired and would
  consume the new resolver path on first chat. No restart was
  performed.

**Live floor-case stress:** also skipped. Floor path covered by unit
test 4 (`test_floor_applied_when_box_starved`), edge tests E3, E5, and
E16. Live stress requires `stress -m` which is itself an OOM hazard;
not run.

## Activity-feed evidence

Covered by unit/integration tests only (live smoke skipped, see above).
Specifically, tests 14a/14b and the new `test_emit_handles_all_sources`
collectively prove that `arail.activity.activity_log.emit` is called
exactly once per backend first-init with `source="aerollm"`, the
correct `level`, and a message containing `"KV budget resolved"` (info
path) or `"clamped to floor"` / etc. (warn path — message text comes
from `reasoning["reason"]` which the unit tests verify).

## Edge cases not covered

- **Concurrent first-construction across threads.** ARCHITECTURE.md
  §"Assumption 6" explicitly punts this; `_shared` has no lock.
  Out of scope per spec.
- **PyO3 actually rejects float at runtime.** We assert the resolver
  returns `int`, but the actual aerollm Rust runtime is not loaded in
  tests. Acceptable: `FakeRuntime` proxies the kwarg shape.
- **Live portal end-to-end.** Skipped for OOM safety (see above).
- **`AEROLLM_KV_BUDGET_PCT="inf"` / `"nan"`.** `float("inf")` parses
  but fails `< 1.0` so falls back to default; `float("nan")` is False
  on every comparison so also falls back. Behavior is correct
  (verified by inspection); a parametrized test would be trivial to
  add but redundant with the existing range-check tests.

## Coverage delta

Resolver `_resolve_kv_budget` and `_emit_budget_activity`:
all branches in ARCHITECTURE.md §"Behavior matrix" + REVIEW.md
Finding A/B/D guards are now exercised by at least one test. The
only previously-untested branch — the four-way `source` routing
through `_emit_budget_activity` — is now covered by the parametrized
`test_emit_handles_all_sources`.

## Notes for the next QA pass

- When the dev box has > 16 GiB free, run the live smoke per the
  ARCHITECTURE.md §"QA edge cases" list and append the observed
  activity-feed line as evidence (no code change needed).
- Consider a `stress`-based live floor test on a disposable VM, not
  the user's daily-driver Mac.
- `AEROLLM_MAX_LENGTH` audit (BUILD_LOG.md flagged it as set-but-
  ignored) is unrelated to this sprint but worth a follow-up.
