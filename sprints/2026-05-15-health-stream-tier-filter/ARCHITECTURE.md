# Architecture: SSE health-stream tier filtering

**Date:** 2026-05-15
**Sprint:** 2026-05-15-health-stream-tier-filter
**Branch:** qukaizen/arail-health-stream-tier-filter (to be cut from main)
**Spec source:** [SPRINT.md](./SPRINT.md) (no VISION — bug-fix scope)
**Carryover from:** [2026-05-14-platform-foundation REVIEW §"Adjudication: SSE stream tier-gating deviation"](../2026-05-14-platform-foundation/REVIEW.md)

## Restatement

The platform-foundation sprint tier-gated `/api/system/health` so a `LAB_TIER=min`
operator no longer sees `marimo` / `open-notebook` / `neo4j` / `opencode` keys
in the `services` dict. That endpoint routes through a shared helper
`_build_services_dict()` (app.py:140) backed by the `_OPTIONAL_SERVICES`
registry (app.py:123). The sibling SSE endpoint `/api/system/health/stream`
(app.py:6686), which powers the dashboard "live checks" cascade, was *not*
filtered — its hardcoded `checks` list (app.py:6847–6865) still emits
`"Marimo"`, `"Open Notebook"`, `"Neo4j Bolt"` events on every tier. The
platform-foundation review accepted this as WEAK_PASS and tagged it as a
carryover. This sprint closes the carryover: align the stream with the
snapshot so a min-tier consumer (UI, scripted client, or external monitor)
sees the same set of services from both endpoints. The change is small,
revertable, and adds one regression test that ties the two endpoints
together at the protocol level.

## Assumptions

- The SSE consumer (the dashboard "live checks" modal in
  `templates/_live_checks_modal.html` and any forker scripts) treats the
  per-check event stream as informational, not as a tier-disclosure source.
  Filtering some events out is acceptable; the `done` event's
  `passed/warned/failed/total` counts will reflect the filtered total.
- `_current_tier()` is the canonical tier signal (already true for the
  snapshot endpoint). No new env var introduced.
- The mapping from stream-check display name to registry service id is
  stable and one-to-one for the entries we filter. The stream uses
  human-readable names (`"Marimo"`, `"Open Notebook"`, `"Neo4j Bolt"`,
  `"Terminal (ttyd)"`, etc.); the registry uses ids (`"marimo"`,
  `"open-notebook"`, `"neo4j"`, `"ttyd"`, etc.). We will encode the
  mapping in the `checks` list itself (a per-row optional `service_id`
  field), not in a separate global table — keeps both sides of the
  mapping in the same diff.
- Stream checks that have no corresponding registry entry (e.g.
  `"Portal HTTP"`, `"IDE (code-server)"`, `"MLX OpenAI compat"`,
  `"RAM available"`, `"Disk free"`, `"Agents loadable"`, `"PKB structure"`,
  `"Model checkpoints"`, `"AirLLM backend"`, `".env validation"`) are
  treated as always-on diagnostics and stream on every tier — they exist
  regardless of tier and the operator wants to see RAM/disk/agents
  regardless of LAB_TIER.
- Existing platform-foundation tests (`tests/test_system_health_tier_gating.py`)
  remain unchanged and still pass after this sprint.
- The stream's UX cascade (sequential reveal with 40ms pauses) is
  preserved; filtering removes entries from the list, it does not change
  ordering, status semantics, or pacing.

## Current state

Today, `system_health_stream()` (app.py:6686) builds a hard-coded `checks`
list of `(display_name, async_fn)` tuples and iterates it unconditionally:

```python
checks = [
    ("Portal HTTP", check_portal),
    ("Terminal (ttyd)", check_ttyd),
    ("Notebook (Jupyter)", check_notebook),
    ("IDE (code-server)", check_ide),
    ("MLX OpenAI compat", check_mlx_openai),
    ("Ollama API", check_ollama),
    ("Lance vector DB", check_lance),
    ("Marimo", check_marimo),               # max-only — leaks on min
    ("Open Notebook", check_open_notebook), # max-only — leaks on min
    ("Neo4j Bolt", check_neo4j),            # max-only — leaks on min
    ("RAM available", check_ram),
    ("Disk free", check_disk),
    ("Agents loadable", check_agents),
    ("PKB structure", check_pkb),
    ("Model checkpoints", check_models),
    ("AirLLM backend", check_airllm),
    (".env validation", check_env),
]
```

There is no reference to `_OPTIONAL_SERVICES` or `_current_tier()` in the
stream handler. Min-tier callers receive `check` events with
`"name": "Marimo"`, `"Open Notebook"`, `"Neo4j Bolt"` whose statuses
disclose that those services are not running. Today this is mostly noise
(every status is `"warn"` because the ports are silent), but it diverges
from the snapshot endpoint's filtered view and from the platform-contract
intent of the carryover.

`check_opencode` does not exist in the stream handler — there is no
opencode entry in the `checks` list today. The snapshot endpoint exposes
`opencode_up` separately, but the stream simply omits it. This is a
pre-existing gap and **not** in scope for this sprint (the sprint is "stop
leaking", not "achieve full parity of probes"). We add a follow-up entry
for it under "Tech debt".

## Desired state

After this sprint:

- `GET /api/system/health/stream` with `LAB_TIER=min` (the default)
  emits `check` events that do **not** include `"Marimo"`, `"Open Notebook"`,
  or `"Neo4j Bolt"`.
- `GET /api/system/health/stream` with `LAB_TIER=max` emits all check
  events that exist today (Marimo, Open Notebook, Neo4j Bolt included).
- The `done` event's `total` field equals the number of `check` events
  actually emitted (i.e. it counts filtered checks, not the pre-filter
  count) — so consumers can use `index < total` invariants safely.
- A regression test asserts the stream's max-only check names are absent
  on `LAB_TIER=min` and present on `LAB_TIER=max`, mirroring the existing
  snapshot test.
- No behavior change for any check that lacks a registry entry. Min-tier
  callers still see Portal HTTP, ttyd, IDE, MLX, Ollama, Lance, RAM, Disk,
  Agents, PKB, Models, AirLLM, .env — the everyday diagnostics.

## Design

### Approach: annotate the stream checks list with optional `service_id`

The cleanest atomic change is to add an optional third element to the
`checks` tuple — the registry id — and filter the list with one
comprehension that reads `_OPTIONAL_SERVICES` + `_current_tier()` exactly
like `_build_services_dict()` does. Concretely:

```python
# Each entry: (display_name, async_fn, service_id_or_None)
# service_id is None for diagnostics that are not in _OPTIONAL_SERVICES
# (RAM, disk, agents, etc.) — they stream on every tier.
# Otherwise service_id is the registry key; the entry is kept iff that
# service's tier is visible at the current LAB_TIER.
checks_all: list[tuple[str, Callable, str | None]] = [
    ("Portal HTTP",         check_portal,        None),
    ("Terminal (ttyd)",     check_ttyd,          "ttyd"),
    ("Notebook (Jupyter)",  check_notebook,      "notebook"),
    ("IDE (code-server)",   check_ide,           None),      # not in registry
    ("MLX OpenAI compat",   check_mlx_openai,    None),      # not in registry
    ("Ollama API",          check_ollama,        "ollama"),
    ("Lance vector DB",     check_lance,         "lance-memory"),
    ("Marimo",              check_marimo,        "marimo"),
    ("Open Notebook",       check_open_notebook, "open-notebook"),
    ("Neo4j Bolt",          check_neo4j,         "neo4j"),
    ("RAM available",       check_ram,           None),
    ("Disk free",           check_disk,          None),
    ("Agents loadable",     check_agents,        None),
    ("PKB structure",       check_pkb,           None),
    ("Model checkpoints",   check_models,        None),
    ("AirLLM backend",      check_airllm,        None),
    (".env validation",     check_env,           None),
]

current_tier = _current_tier()
visible_tiers = {"min"} if current_tier == "min" else {"min", "max"}

def _check_visible(svc_id: str | None) -> bool:
    if svc_id is None:
        return True  # diagnostic — always streams
    required = _OPTIONAL_SERVICES.get(svc_id)
    if required is None:
        # Unknown id — fail closed (do not leak). This is the safe default
        # if a future entry is added to the stream list with a typo.
        return False
    return required in visible_tiers

checks = [(name, fn) for (name, fn, svc_id) in checks_all if _check_visible(svc_id)]
total = len(checks)
```

The rest of `_generate()` is **unchanged** — it iterates `checks` exactly
as before. `total = len(checks)` is recomputed after the filter so the
`done` event reports the filtered count, preserving the `index < total`
invariant on the wire.

### Why not extract a shared `_build_stream_checks()` helper?

Considered. Rejected because:

1. The stream checks list closes over local variables (`bind`, port ints
   from env, the per-check async closures). Extracting to a module-level
   function would require passing all those as arguments — adds noise
   without reducing duplication, since the *list* itself is the unique
   surface, not the filter.
2. The filter is six lines of code and uses two already-public symbols
   (`_OPTIONAL_SERVICES`, `_current_tier`). Inlining is honest about the
   scope; a "helper" implies generality that doesn't exist.
3. Atomic-commit goal: one diff, one file. A helper would mean either a
   second module or moving the inner closures out, both larger surgery.

If a third health surface (e.g. a Prometheus probe-by-probe view) appears
later, *that* is when we extract.

### Why fail-closed on unknown service_id?

The registry lookup `_OPTIONAL_SERVICES.get(svc_id)` returns `None` for
typos. `_build_services_dict()` (line 185) uses
`_OPTIONAL_SERVICES.get(svc_id, "max")` — i.e. *also* fail-closed (defaults
to max-only, so a typo'd entry stays hidden on min). We match that
convention exactly. A test asserts that every annotated `service_id` in
the stream list either matches a key in `_OPTIONAL_SERVICES` or is
explicitly `None` — that's the architect-supplied guard against typos
landing silently.

## Data flow

```
GET /api/system/health/stream
        │
        ▼
system_health_stream()
        │
        ├── _current_tier()         ─┐
        │                            │
        ├── _OPTIONAL_SERVICES       │
        │                            ▼
        ├── checks_all = [(name, fn, svc_id?), …]
        │                            │
        │                            ▼
        │              filter: keep iff svc_id is None
        │                        OR _OPTIONAL_SERVICES[svc_id] ∈ visible_tiers
        │                            │
        │                            ▼
        ├── checks = [(name, fn), …]   ← tier-filtered
        │
        └── _generate():
                for (name, fn) in checks:
                    status, detail = await fn()
                    yield SSE "check" event
                yield SSE "done" event with total=len(checks)
```

## Interface contracts

### `/api/system/health/stream` (modified)

- **Postcondition:** for each `(name, fn, service_id)` in the in-source
  list, an SSE `check` event is emitted **iff** (a) `service_id is None`,
  or (b) `_OPTIONAL_SERVICES.get(service_id)` is in
  `{"min"}` (on min tier) or `{"min", "max"}` (on max tier). The `done`
  event's `total` equals the number of `check` events actually emitted.
- **Event shape unchanged:** `event`, `name`, `status`, `detail`,
  `duration_ms`, `index`, `total` for `check`; `event`, `passed`,
  `warned`, `failed`, `total`, `total_ms` for `done`. No new fields
  in this sprint.
- **Order unchanged:** the cascade order is the order of the residual
  list — i.e. preserves the existing left-to-right reveal modulo
  removed entries.
- **Bad input:** none — no query params accepted. Future-compat
  forward stance.
- **Latency:** ≤2 ms additional work on stream start (one dict lookup
  per entry); stream pacing dominated by existing 40 ms `asyncio.sleep`.

### Internal: `_OPTIONAL_SERVICES` registry (read-only)

- **Promise:** key set unchanged by this sprint; tier values unchanged.
  Stream filter reads the registry, does not mutate it.
- **Requires:** if the stream list adds a new annotated check, the
  registry must contain that id. Enforced by the new unit test
  (`test_stream_check_service_ids_are_known`).

## Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| `LAB_TIER` unset | `_current_tier()` returns `"min"` (existing default) | Min-filter applied; max-only checks hidden |
| `LAB_TIER` invalid string | `_current_tier()` clamps to `"min"` | Same — min-filter applied |
| Stream annotates a check with a `service_id` that is not in `_OPTIONAL_SERVICES` | New unit test enumerates the stream list and asserts every non-None svc_id is a registry key | Builder caught at test-time; fail-closed at runtime (entry hidden) |
| `checks_all` order shuffled accidentally | Existing UX/regression test asserts a stable order of names for `LAB_TIER=max` | Diff review + test failure |
| `done.total` drifts from emitted check count | New test counts emitted `check` events and compares to `done.total` | Built into the new test |
| Min-tier client expects Marimo events (breaking change for forkers) | Documented in REVIEW carryover; min-tier semantics now match snapshot endpoint | Forkers consult `/api/system/health` to discover services; stream is informational diagnostic; matching shapes is the *desired* behavior |
| `_generate()` exception mid-stream after filter | Existing try/except per check (`status, detail = "fail", "check raised: {e}"`) | Same — filter does not change `_generate()` |
| Race: tier changes during stream (e.g. operator runs `arailctl upgrade max` mid-cascade) | Tier is captured at handler entry; stream completes with the original tier | Acceptable — fresh stream picks up new tier; documented in this row |
| Filter accidentally hides a min-tier service | Regression test enumerates min-only check names on `LAB_TIER=min` and asserts presence | Test fails before merge |
| Empty `checks` list (pathological: all entries hidden) | Defensive: stream still emits `done` event with `total=0` | Frontend handles `total=0` gracefully (existing modal behavior) |

## Test strategy

All tests live in `tests/test_system_health_stream_tier_filter.py` (new
file). They use the same `TestClient` + `_port_open` monkeypatch pattern
as `tests/test_system_health_tier_gating.py` so the SSE deterministic-
without-real-ports approach matches.

### Unit (3 tests)

1. **`test_stream_min_tier_hides_max_only_check_names`** — `LAB_TIER=min`:
   parse the SSE response, collect all `check` event `name` fields,
   assert `"Marimo"`, `"Open Notebook"`, `"Neo4j Bolt"` are **not** in
   the set. Assert `"Portal HTTP"`, `"Terminal (ttyd)"`, `"Ollama API"`,
   `"Lance vector DB"` **are** present.

2. **`test_stream_max_tier_includes_max_only_check_names`** —
   `LAB_TIER=max`: parse SSE, assert `"Marimo"`, `"Open Notebook"`,
   `"Neo4j Bolt"` **are** present.

3. **`test_stream_done_total_matches_check_count`** — for both tiers,
   parse all events, assert `len([e for e in events if e["event"] ==
   "check"]) == done_event["total"]`.

### Integration (1 test)

4. **`test_stream_and_snapshot_services_keysets_align_min`** — call
   `/api/system/health` and `/api/system/health/stream` with
   `LAB_TIER=min`. Map each stream check name (where it has a registry
   id) to the snapshot service id; assert: every max-only id is absent
   from **both** responses, every min-only id that is "up" (probed True
   in this test setup) appears in both responses. This is the parity
   guard the platform-foundation REVIEW identified as missing.

### Registry-integrity (1 test)

5. **`test_stream_check_service_ids_are_known`** — import the stream
   handler's `checks_all` shape (the cleanest path: expose the list as
   a module-level `_STREAM_CHECKS_REGISTRY` or, if that's awkward,
   build a tiny test that calls the endpoint with both `LAB_TIER=min`
   and `LAB_TIER=max`, computes the *difference* of check name sets,
   and asserts every name in the diff has a known mapping). Default
   route: extract the static portion of `checks_all` (display_name →
   service_id) to a module-level dict in `app.py` *if and only if*
   that doesn't grow the diff. Builder may choose: either expose a
   tiny `_STREAM_CHECK_TIER_MAP` constant for testability, or run the
   diff-based test. Either form satisfies the failure-mode row "stream
   annotates a check with a `service_id` not in `_OPTIONAL_SERVICES`".

### Regression — already-green tests should stay green

6. All existing tests in `tests/test_system_health_tier_gating.py`
   continue to pass — they test `_build_services_dict()` directly and
   the snapshot endpoint, neither of which we touch.

### Security tests (per arail QA allocation, 20%)

7. **`test_stream_tier_bypass_query_param_ignored`** — issue
   `GET /api/system/health/stream?show_all=true&tier=max` with
   `LAB_TIER=min`; assert Marimo / Open Notebook / Neo4j events are
   absent. (Today the endpoint accepts no query params; we assert no
   accidental future regression honors them.)

### Setup tests (per arail QA allocation, 30%)

8. **`test_stream_endpoint_latency_under_one_second_per_check`** — assert
   end-to-end stream completes in `O(N × 40ms + check_runtime)`. Hard
   threshold: under 2 seconds for the filtered min-tier stream with
   mocked ports. Guards against accidental synchronous sleep changes.

## Tech debt

**Added:**

- The `checks_all` list now carries a third element (`service_id`). Future
  edits must remember to set it (or `None`). Mitigated by test (5).
- One more place that reads `_OPTIONAL_SERVICES`. The registry now has
  two consumers in `app.py`: `_build_services_dict()` and the stream
  filter. Acceptable; both reads are tiny.

**Repaid:**

- **Platform-foundation carryover closed.** The accepted WEAK_PASS
  deviation in REVIEW.md §"Adjudication" now has its regression test;
  the stream and snapshot endpoints agree on tier-visibility semantics.
- **Implicit "stream is informational" claim is now testable.** Before
  this sprint, "the stream doesn't tier-filter" was a documented
  exception; now the rule is uniform and the exception is gone.

**Net:** Negative (good). Roughly +12 lines of code, +5 tests, –1
carryover row in the platform-foundation REVIEW.

**Follow-ups (file as backlog, not this sprint):**

- **Opencode missing from stream.** The snapshot endpoint includes
  `opencode` as a max-only service, but the stream has no
  `check_opencode` entry. Add a `check_opencode` + entry in a future
  sprint if/when the dashboard's "live checks" modal grows enough that
  forkers care about parity. Effort: ~20 min.
- **`check_ide` / `check_mlx_openai` un-registered.** These two stream
  checks have no corresponding `_OPTIONAL_SERVICES` entry. Both *are*
  effectively max-only (code-server lands in `max` tier; MLX OpenAI
  port is local-inference plumbing) but adding them is a tier-policy
  decision, not a stream-filter cleanup. Defer to the next platform
  sprint.

## Recommended implementation order

One atomic commit, one file touched in `app.py`, one new test file.

1. **Single commit: tier-filter stream checks + tests + carryover
   close-out.**
   - Edit `src/arail/portal/app.py` ~line 6847: change `checks = [...]`
     to `checks_all = [...]` with the third-element `service_id`
     annotation, then derive `checks = [...]` via the filter; update
     `total = len(checks)`.
   - Add `tests/test_system_health_stream_tier_filter.py` containing
     tests 1–4, 7, 8 (and 5 if `_STREAM_CHECK_TIER_MAP` is exposed; else
     the diff-based variant).
   - Append a one-line resolution note to
     `sprints/2026-05-14-platform-foundation/REVIEW.md` under
     "Required actions before merge" referencing this sprint as the
     closure.

Total diff target: ≤120 lines added (test file is the bulk),
≤20 lines changed in `app.py`. The architect's hard ceiling: if the
diff in `app.py` exceeds 40 lines, the builder must pause and ask
because the design above doesn't justify more.

## Cross-item concerns

- **No regression on existing platform-foundation tests.** The
  `_build_services_dict()` path is untouched. The stream filter reads
  the registry but does not mutate it.
- **Frontend impact:** the dashboard's `_live_checks_modal.html` (and
  its JS driver) renders whatever events arrive; fewer events on min
  tier means a shorter cascade. No JS change required. Builder may
  visually confirm in the portal but no template edits should be in
  this sprint's diff.
- **Forker breakage:** the SSE stream is not documented as a platform
  contract in `docs/api-conventions.md`. No external script is
  guaranteed to receive every check event. Min-tier consumers losing
  three event entries is the *correction*, not a breaking change.
