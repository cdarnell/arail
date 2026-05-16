# Test report: SSE health-stream tier filtering

**Date:** 2026-05-16
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 5fb1929
**Architect verdict:** PASS ([REVIEW.md](./REVIEW.md))
**QA verdict:** PASS

## Summary

- 8 pre-existing builder tests (`tests/test_system_health_stream_tier_filter.py`) — all pass.
- 34 new QA tests (`tests/test_system_health_stream_tier_filter_qa.py`) — all pass.
- 7 platform-foundation regression tests (`tests/test_system_health_tier_gating.py`) — all pass.
- **Combined suite: 49/49 green in ~31 s.**

The architect's PASS verdict holds. Every architect-noted INFO/gap (cascade
order assertion, full registry parity, timing-channel disclosure) is now
covered by the QA suite. No FAIL findings.

## Test allocation (this sprint)

Adjusted from arail's default (30/30/20/10/10) toward edge-heavy because the
change is a tier-gating contract, not a setup-or-Buddy change:

| Category | Target | Actual | Tests |
|---|---|---|---|
| Edge cases | 60% | 62% (21 / 34) | tier-unset, garbage values (8 parametrize), casing/whitespace (5 parametrize), opencode tech-debt absence, cascade-order stability, index monotonicity (2 parametrize), tier-flip mid-stream, concurrent-clients-different-tiers, empty registry / fail-closed, runtime registry mutation |
| Security | 20% | 21% (7 / 34) | timing-channel non-disclosure, 4 spoofed-tier headers, cookie spoofing, plus the existing builder query-param test |
| Regression | 20% | 18% (6 / 34) | full snapshot/stream parity over entire `_OPTIONAL_SERVICES` registry, done arithmetic invariant (2 parametrize), check-event shape, done-event shape |

## Test inventory (new)

| # | Test | Category | Covers | Status |
|---|---|---|---|---|
| Q1 | test_stream_lab_tier_empty_defaults_to_min | Edge | LAB_TIER='' clamps to min — no max leakage. (Note: full `delenv` not reliable due to `arail.config.load_dotenv` repopulating; `''` is the canonical "effective unset" in this codebase per `test_aerollm_defaults.py`.) | PASS |
| Q2 | test_stream_lab_tier_garbage_clamps_to_min [×8] | Edge | Garbage values (`MAX` casing, whitespace `  max  `, typo `maxx`, nonsense `pro`, empty `""`, injection `min;DROP TABLE`, trailing newline, cyrillic `тах`). Variants that strip+lower to `max` correctly expose max; all others clamp to min. | PASS |
| Q3 | test_stream_lab_tier_max_variants_all_expose_max_only [×5] | Edge | `max`, `MAX`, `Max`, ` max`, `max\t` all expose max-only checks (verifies `_current_tier()` strip+lower normalization) | PASS |
| Q4 | test_opencode_absent_from_stream_on_both_tiers | Edge | Documented tech-debt gap (opencode is in registry but has no stream probe) is consistent — no accidental leak under any plausible display name on either tier | PASS |
| Q5 | test_stream_check_order_stable_on_max | Edge | Cascade order matches source-list order exactly (addresses architect INFO row "no order regression test") | PASS |
| Q6 | test_stream_check_indices_zero_indexed_and_monotonic [×2] | Edge | check.index = 0..N-1, all check events agree on total | PASS |
| Q7 | test_stream_tier_flip_after_entry_does_not_widen_stream | Edge | Mutating `LAB_TIER` while an SSE response is mid-flight does not retroactively unlock max-only checks (architect-claimed "captured-at-entry" invariant) | PASS |
| Q8 | test_stream_concurrent_clients_each_see_own_tier_at_request_time | Edge | Sequential requests with different LAB_TIER each see their own filter — guards against module-level caching | PASS |
| Q9 | test_stream_handles_all_filtered_empty_checks_list | Edge | With `_OPTIONAL_SERVICES` patched to `{}`, all registry-gated checks fail-closed; always-on diagnostics still stream; done event still emitted with correct total | PASS |
| Q10 | test_stream_filter_respects_runtime_registry_additions | Edge | Demoting an entry from min→max at runtime (mutate registry) correctly hides it from min stream — proves filter reads live registry, not a snapshot | PASS |
| Q11 | test_stream_min_tier_timing_independent_of_max_only_service_state | Security | Min-tier executed check set is identical whether ports are open or closed — no timing-channel disclosure of max-only service presence | PASS |
| Q12 | test_stream_tier_bypass_headers_ignored [×4] | Security | `X-Lab-Tier`, `X-Forwarded-Tier`, `Authorization: Bearer tier=max`, `X-Override-Tier` all ignored | PASS |
| Q13 | test_stream_tier_bypass_cookie_ignored | Security | LAB_TIER cookie cannot override env-derived tier | PASS |
| Q14 | test_snapshot_and_stream_parity_for_every_optional_service | Regression | Full parity check over every `_OPTIONAL_SERVICES` entry at both tiers, with probes True. Generalises the architect's parity guard from "max-only ids" to "the whole registry" | PASS |
| Q15 | test_stream_done_arithmetic_invariant [×2] | Regression | `done.passed + done.warned + done.failed == done.total` on both tiers | PASS |
| Q16 | test_stream_check_event_shape_unchanged [×2] | Regression | Check events have exactly `{event, name, status, detail, duration_ms, index, total}` with correct types and value constraints | PASS |
| Q17 | test_stream_done_event_shape_unchanged | Regression | Done event has exactly `{event, passed, warned, failed, total, total_ms}` with non-negative int values | PASS |

Parametrized count breakdown: 8+5+2+4+2+2 = 23 instances on top of 11 base tests → 34 collected.

## Failures

None.

## Security review

| Surface | Checked | Findings |
|---|---|---|
| User input (query params) | Existing builder test (`test_stream_tier_bypass_query_param_ignored`) hits `?show_all=true&tier=max` under min tier and asserts no leak. Endpoint signature accepts no query params; FastAPI ignores unknown ones | None. Pass. |
| User input (headers) | Q12: 4 spoof headers (`X-Lab-Tier`, `X-Forwarded-Tier`, `Authorization: Bearer tier=max`, `X-Override-Tier`) sent under min tier — all ignored | None. Pass. |
| User input (cookies) | Q13: `LAB_TIER` and `tier` cookies set to `max` under min tier env — ignored | None. Pass. |
| Authentication / authorization | Tier source is process env only (`_current_tier()` reads `os.getenv("LAB_TIER")`). No header, cookie, or query input considered. SSE endpoint inherits portal's existing auth middleware (not changed in this sprint) | None. Pass. |
| Side channels (timing) | Q11: ran min-tier stream twice with all probes True vs all False; the executed check name set is identical (proves max-only probes are *not executed* on min — no timing leak about max-only port states). Stream duration is dominated by the deterministic 40 ms cascade sleep, not by probe outcomes | None. Pass. |
| Side channels (event count) | Architect's `done.total` parity test plus Q16's all-events-agree-on-total assertion: total is computed once from the filtered list and emitted consistently — does not encode the pre-filter list size, so it does not disclose which/how-many max-only services exist | None. Pass. |
| File I/O | No file paths read or written by the change | N/A. |
| Network I/O | No new network calls; reuses existing port probes which are now mocked in tests | N/A. |
| Deserialization | No untrusted input deserialized | N/A. |
| Crypto | No crypto in this change | N/A. |
| Dependencies | Zero new deps; filter uses stdlib + existing `_OPTIONAL_SERVICES` registry | None. |

## Performance

Not a hot path. The change adds one `dict.get()` per entry of `checks_all`
(17 entries today) on stream start. Builder's
`test_stream_endpoint_latency_under_two_seconds_min_tier` gives a 2 s ceiling
and passes well under that (observed ~560 ms expected, ~1 s actual local).
Q11's two-probe runs also stay under 3 s. No regression vs pre-sprint
behavior.

BENCHMARK.md: N/A (not on a hot path; 17-entry dict lookup × ≤17 = sub-ms).

## Coverage delta

The 21 changed lines in `app.py` (lines ~6847-6884) were already fully
covered by the builder's 8 tests per the architect's review. The QA suite
exercises additional branches:

- `_check_visible()` "unknown id → False" branch (Q9 — patches registry to empty)
- `_check_visible()` registry-mutation path (Q10 — flips ttyd to max at runtime)
- `_current_tier()` strip+lower normalization (Q2, Q3 — 13 input variants)
- Tier-capture-at-entry invariant (Q7 — mid-stream env mutation)

No code path in the changed range is unexercised after QA.

## Notes for the next QA pass

- **`.env` auto-load pollution.** `arail.config.load_dotenv()` repopulates
  `LAB_TIER` from the repo `.env` even after `monkeypatch.delenv` runs.
  This is documented in `tests/test_aerollm_defaults.py`. The robust
  pattern is `monkeypatch.setenv("LAB_TIER", "")`, which `_current_tier()`
  treats as "not in `_TIER_SURFACES`" → clamps to `min`. Future QA passes
  on tier-gating code should default to this pattern. Q1 documents this
  inline.
- **Stream uses `_port_open` directly, not `_build_services_dict`.** The
  stream endpoint runs its own per-check async probes; the snapshot
  endpoint uses `_build_services_dict()` over the same probe results.
  Parity is therefore behavioral, not structural — Q14 verifies it
  end-to-end with all probes True. Future changes that introduce a new
  optional service must update **two** sites (the registry AND the
  `checks_all` annotation in `system_health_stream()`).
- **Tech-debt follow-ups confirmed open:**
  - `check_opencode` not present in stream (parity gap with snapshot —
    snapshot exposes `opencode_up` on max, stream does not). Q4 locks
    this absence in as the current contract; once the follow-up sprint
    adds the probe, Q4 will need to be updated to assert presence on max.
  - `check_ide` / `check_mlx_openai` un-registered in `_OPTIONAL_SERVICES`
    — they stream on every tier as always-on diagnostics. Tier-policy
    decision, not a stream-filter issue.
- **Cascade order is now contract-tested (Q5).** If a future sprint
  reorders the checks list for UX reasons, Q5 will fail loudly. That's a
  feature: order changes should be explicit, not silent.
- **No order assertion on min tier.** Q5 covers max only. A min-tier
  order test would be redundant (it's a subset of the same source list
  with three rows removed). If a future change inserts a new entry, the
  max-tier order test will fire first.
