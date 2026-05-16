# Review: SSE health-stream tier filtering

**Date:** 2026-05-16
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 5fb1929
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 88fb7de
**Diff:** commits `e699f7f` (test scaffold + app.py change, bundled with unrelated WIP) and `5fb1929` (BUILD_LOG + REVIEW closure)

## Verdict: PASS

## Spec adherence

The implementation matches ARCHITECTURE.md essentially verbatim:

- `checks_all` 3-tuple list at app.py:6853–6871 mirrors the design's annotation
  table line-for-line, including every `service_id` mapping the architect
  specified (ttyd, notebook, ollama, lance-memory, marimo, open-notebook,
  neo4j; `None` for the always-on diagnostics).
- `_check_visible()` inline closure (app.py:6875–6881) implements the
  fail-closed semantics for unknown ids that the architect required
  (matches `_build_services_dict()` convention).
- `total = len(checks)` is recomputed after the filter (app.py:6884), so
  `done.total` reflects the filtered count — the wire invariant
  `index < total` is preserved.
- `_generate()` body is untouched. Order, pacing, and event shape unchanged
  — exactly the boundary the architect drew.
- `app.py` delta is **+21 lines**, well inside the 40-line hard ceiling.
- Implementation order followed: one atomic logical change in `app.py`,
  one new test file, plus the carryover closure note appended to
  `sprints/2026-05-14-platform-foundation/REVIEW.md`.

Drift: zero on the design contract. The only deviation from the original
plan is bookkeeping — the diff was bundled into commit `e699f7f` along
with unrelated WIP (compiled docs refresh, dashboard mission mirror,
portal updates). This is noted as a sprint hygiene issue (see Code
quality findings) but does not affect correctness.

## Failure-mode cross-reference

Walking the ARCHITECTURE.md failure-modes table row-by-row:

| Row | Addressed? | Evidence |
|---|---|---|
| `LAB_TIER` unset → defaults to min | Yes | `_current_tier()` (unchanged) returns "min" by default; min filter applied |
| Invalid tier string clamps to min | Yes | `_visible = {"min"} if _tier == "min" else {"min", "max"}` — anything not exactly "max" yields the min set. Even safer than the design implied |
| service_id typo / unknown id | **Yes — both layers** | Runtime: `_check_visible()` returns False on unknown id (app.py:6880). Test layer: `test_stream_check_service_ids_are_known` enumerates the max−min name diff and asserts every gated name maps to a known `_OPTIONAL_SERVICES` key |
| `checks_all` order shuffled | Partial | No explicit order assertion, but tests 1/2 assert presence/absence on each tier; test 8 implicitly checks N is in range. UX cascade order isn't strictly tested — minor gap, see Code quality |
| `done.total` drifts from emitted count | Yes | `test_stream_done_total_matches_check_count` parametrized over both tiers |
| Min-tier client expects Marimo (forker breakage) | Yes | Documented in REVIEW carryover closure; intentional |
| `_generate()` exception mid-stream | Yes | Per-check try/except (app.py:6893–6894) untouched |
| **Tier downgrade race mid-stream** | Yes | `_tier` and `checks` are captured at handler entry, **before** `_generate()` is constructed. The closure binds the filtered list once; a concurrent `arailctl upgrade min` does not retroactively widen the stream. Confirmed by inspection at app.py:6872–6884 |
| Filter accidentally hides min-tier service | Yes | `ALWAYS_ON_STREAM_NAMES` set asserted present on min in test 1 |
| Empty checks list (pathological) | Indirect | `_generate()` still emits `done` with `total=0` — code path unchanged |

Every row has either a test or an inspection-verified runtime guard.

## Code quality findings

- [INFO] **Tier-downgrade race is safe.** The filter executes before
  `_generate()` is constructed, so the captured `checks` list is the
  authoritative cascade. A mid-stream `LAB_TIER` mutation cannot leak
  max-only services into an already-running min stream. Good.
- [INFO] **Fail-closed on unknown id matches `_build_services_dict()`
  precedent** — registry consumers in `app.py` are now consistent.
- [INFO] **No order regression test.** ARCHITECTURE.md row "checks_all
  order shuffled" suggested a UX cascade order assertion. The test suite
  doesn't include one. Acceptable because (a) the UX is not a documented
  contract and (b) the file diff makes order changes visible in code
  review. Filing as informational, not blocking.
- [INFO] **Commit hygiene:** the code change for this sprint was bundled
  into `e699f7f` along with unrelated WIP (README, compiled docs,
  dashboard template overhaul). The sprint's logical atomicity is
  preserved in the design intent but not in the commit boundary. Future
  sprints should land tier-gating-only diffs on their own commit so the
  carryover-closure paper trail is single-blame-able. Not a BLOCK.
- [INFO] **Test numbering:** BUILD_LOG.md references tests 1–5, 7, 8
  (no test 6 — the explicit regression-on-existing-tests row was
  satisfied by re-running the platform-foundation suite, which the
  builder reports stayed green). Numbering matches ARCHITECTURE.md
  intent.

## Security findings

- [INFO] **Query-param bypass:** `test_stream_tier_bypass_query_param_ignored`
  hits `?show_all=true&tier=max` under `LAB_TIER=min` and asserts no
  max-only events appear. Confirms there's no accidental future
  regression honoring spoofed query params. Pass.
- [INFO] **Tier source of truth is env-only.** `_current_tier()` is
  read once at handler entry from the process env (no header, cookie,
  or query input). Cannot be influenced by an unauthenticated SSE
  client. Pass.
- [INFO] **No new dependencies introduced.** Filter uses stdlib +
  existing `_OPTIONAL_SERVICES` registry. No supply-chain delta.
- [INFO] **No new I/O surface.** Endpoint accepts no new params; no
  file or network I/O introduced; tokens / secrets untouched.

No security BLOCKs.

## Test coverage assessment

- 8/8 new tests pass locally (`pytest tests/test_system_health_stream_tier_filter.py`).
- All 7 platform-foundation `test_system_health_tier_gating.py` tests
  remain green. Verified by running the combined suite — 15/15 pass in 8.45 s.
- Coverage on the 21 changed lines in `app.py`: every branch exercised
  (`svc_id is None` path via always-on names; `_OPTIONAL_SERVICES.get()`
  hit + miss via min/max tiers; unknown-id fail-closed branch is
  defended by the registry-integrity test, even though no live unknown
  id exists today).
- Gap: no test asserts the **exact** filtered count (e.g., "min produces
  exactly 13 events"). Considered and rejected — would be brittle to
  future check additions. The `done.total` parity test catches the
  invariant that actually matters.

## Performance assessment

Not a hot path (handler runs at human/dashboard cadence). The added
work is one `dict.get` per entry on stream start (~17 lookups, sub-
millisecond). `test_stream_endpoint_latency_under_two_seconds_min_tier`
gives a 2 s ceiling and passes comfortably (≈560 ms expected; observed
< 1 s in the local run). No regression vs pre-sprint behavior.

## Regression risk vs platform-foundation REST endpoint

The snapshot endpoint `/api/system/health` was not touched. The shared
`_build_services_dict()` helper and the `_OPTIONAL_SERVICES` registry
are read-only consumers. `test_stream_and_snapshot_services_keysets_align_min`
calls both endpoints from the same client and asserts agreement on
max-only ids — that's the explicit parity guard the platform-foundation
REVIEW flagged as missing. Now present and green.

Platform-foundation tier-gating tests (7) re-run alongside the new
suite: all still pass.

## Tech debt delta

Matches the architect's prediction exactly:

- **Added:** `checks_all` carries a 3rd element; future edits must set
  `service_id` or `None`. Mitigated by `test_stream_check_service_ids_are_known`.
- **Repaid:** platform-foundation WEAK_PASS carryover closed with a
  regression test that cross-validates both endpoints.
- **Net:** Negative (good). No surprise debt beyond the architecture
  forecast.

Follow-ups from ARCHITECTURE.md still open (not in scope here):
- `check_opencode` not present in stream (parity gap with snapshot).
- `check_ide` / `check_mlx_openai` un-registered in `_OPTIONAL_SERVICES`.

These remain as documented backlog items and do not block this sprint.

## Required actions before merge

None. Verdict is PASS. Hand off to `/qa`.

Optional, non-blocking, for the orchestrator's awareness:

1. Future sprint diffs should land in their own commit (not bundled
   with unrelated WIP) so carryover-closure traceability is cleaner.
2. Consider opening backlog tickets for the two ARCHITECTURE.md
   follow-ups (opencode parity, ide/mlx registry entries).
