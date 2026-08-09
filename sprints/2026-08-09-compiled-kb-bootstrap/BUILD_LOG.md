# Build log: Compiled-KB bootstrap (QA-6)

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 6bef72c
**Started:** 2026-08-09

## Plan

Given the size of ARCHITECTURE.md's scope, this build targets the
"recommended implementation order" §1-5 and §8 (the mechanism that actually
fixes QA-6: the empty-gate bug and its mount-time bootstrap), plus the unit
and integration tests the architect assigned to the builder. Caller UX
updates (§6: doctor/lab_brief/goal-drafter/researcher wiring;
§7: promote_bulk + /dac UI) are large, independent surfaces; deferred and
called out below rather than half-built under time pressure. This is a scope
note, not a design disagreement — no architect gap found.

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/compiled_kb.py` | `manifest_present`, `gate_state` | unit (`tests/test_compiled_kb.py`) | `72e7232` |
| 2 | `src/arail/pkb.py` | `retrieve_for_agents`; `search_for_agents` becomes `["hits"]` | unit + regression (`tests/test_pkb_gate.py` untouched) | `af9ef85` |
| 3 | `src/arail/compiled_kb.py` | `auto_approve_world_terms`, sticky `unapproved.json` | 21 unit cases in `test_compiled_kb_bootstrap.py` | `e6b1dff` |
| 4 | `src/arail/compiled_kb.py`, `arailctl` | `bootstrap()` + CLI + `./arailctl pkb bootstrap` | unit (bootstrap) + CLI smoke-test | `e6b1dff`, `1755d8a` |
| 5 | `src/arail/world_mount.py` | mount() step 3.5 hook | integration, real physics fixture | `c9524fe` |
| 6 | `scripts/install.sh` | call bootstrap once, non-fatal, in verify phase | `bash -n` + code review | `e12fca6` |
| 7 | `docs/cli.md` | document `bootstrap` verb + both escape hatches | n/a | `87e27e9` |

Deferred (documented, not implemented this pass — flagged to orchestrator):
- Caller updates: `lab_brain.py`, `agents/researcher.py`, `portal/app.py`
  goal drafter, `lab_brief.py`, `doctor.py` gate_state wiring.
- `promote_bulk` endpoint + `/dac` empty-state/bulk-select UI +
  `ARAIL_APPROVED_ONLY=off` persistent banner.

## Execution

### Step 1 — `manifest_present` + `gate_state`
Implemented exactly per contract §"Interface contracts". `gate_state(cheap=True)`
skips `pending_count` and reports `-1`; verified with a monkeypatch that
raises if `pending_count` is called under `cheap=True`. Total-failure branch
returns a complete dict with `state="unbootstrapped"`.
Tests: 15 new cases in `tests/test_compiled_kb.py` (manifest_present shapes,
all 4 gate_state values, cheap perf contract, total-failure fail-closed).
Commit: `72e7232`.

### Step 2 — `pkb.retrieve_for_agents`
`search_for_agents` is now `retrieve_for_agents(...)["hits"]`, byte-identical
(asserted by test). `empty_reason` distinguishes `gate_empty` (search never
ran) / `no_match` / `gate_off_no_match` / `None`. `tests/test_pkb_gate.py`
untouched and still passing, per the architecture's back-compat contract.
Tests: new file `tests/test_pkb_retrieve_for_agents.py` (6 cases, including
a monkeypatched internal-error case proving fail-closed-and-loud).
Commit: `af9ef85`.

### Step 3/4 — `auto_approve_world_terms` + sticky revocation + `bootstrap`
Implemented the scope invariant as four AND-ed conditions inside one
function; added a local `_safe_term_slug` mirroring `world_mount`'s (same
regex, documented parity requirement). `approve()` gained an additive
`extra` dict param (`{"auto": True}`); `revoke()` now writes to
`compiled/kb/unapproved.json` and `approve()` clears a path from it.
Added `revoke_auto()` for the one-step rollback the architecture's
"Rollback" section describes.
`bootstrap()` discovers the staged World from `sources/world-<slug>/`,
resolves the catalog copy via `arail.build.world_corpus.resolve_world_bundle`
(reusing its existing WORLDS_DIR-catalog logic rather than duplicating it),
computes `seal_sha` from the catalog `terms.json`'s raw bytes (matches what
`verify_seal` would compute at a real mount), and always writes the manifest
even when zero terms qualify.
Tests: new file `tests/test_compiled_kb_bootstrap.py`, 21 cases covering the
happy path, hand-dropped-file exclusion, notes/inbox/agents unreachability,
traversal, both escape hatches (env off, sentinel present, sentinel
unreadable), sticky revocation surviving a re-mount, explicit re-approval
overriding stickiness, idempotency, rejected-entries skip, terms-missing-
on-disk skip, unknown slug, empty bundle_terms, malformed term dicts,
`revoke_auto`, and 5 `bootstrap()` cases (fresh lab, dry-run, no-catalog-
bundle, real bundle, missing root).
**Environment note (not a code defect):** this worktree's system Python
lacks `python-dotenv`; `arail.config` (and therefore anything importing it,
including `resolve_world_bundle`'s `WORLDS_DIR`) fails to import without it.
Installed `python-dotenv --user` locally to run these tests; flagging so
CI/reviewer environments don't hit the same surprise if it isn't already a
project dependency there.
Commit: `e6b1dff`. CLI wiring (`./arailctl pkb bootstrap [--dry-run]`,
`python -m arail.compiled_kb bootstrap`) in a separate commit `1755d8a` —
smoke-tested directly (see commit message), no automated CLI-argparse test
added (the underlying `bootstrap()` function has full coverage; the CLI
layer is a thin argparse passthrough matching the existing `prune` verb's
pattern). `--all-instances` / `--world <slug>` CLI flags from the
architecture's signature are **not** implemented — `PKB_ROOT` is resolved
per-process from env (per the architecture's own assumptions), so backfilling
the six existing roots today means running the verb once per instance's env.
Flagged as scope not completed, not a design disagreement.

### Step 5 — `world_mount.mount()` step 3.5 hook
Added immediately after the pointer write (`_write_record`), wrapped in
try/except so a bug there can never fail a mount — verified by
`test_mount_still_succeeds_if_auto_approve_raises`. Full regression run of
`tests/test_world_mount.py` (12 cases, pre-existing) still passes unchanged.
Tests: new file `tests/test_world_mount_auto_approve.py`, 5 cases using the
real `tests/fixtures/world-bundles/physics` bundle — happy path (all term
slugs from the fixture's real `terms.json` approved, gate state
`"populated"`), non-term-path unreachability, both escape hatches, and the
best-effort/never-fails-mount case.
Commit: `c9524fe`.

**Gap discovered, not fixed (flagged, per "no scope drift"):** ARCHITECTURE.md's
data-flow diagram and "Recommended implementation order" §5 name only
`world_mount.mount()`. `world_mount.swap()` (used by `./arailctl world swap`)
independently stages a new bundle and flips the pointer but does **not** call
`auto_approve_world_terms`. A World swapped in via `swap()` therefore lands
in the same "sealed, staged, but nothing approved" state the four pre-sprint
roots are in today, until an explicit `./arailctl pkb bootstrap` is run. This
does not violate the scope invariant (nothing is *wrongly* approved) — it's
a completeness gap matching the original bug's symptom for one mount path.
Not fixed here since it's outside the architecture's stated hook location;
surfacing for the architect/orchestrator to decide whether `swap()` needs
the same 3.5 step in a follow-up.

### Step 6 — `./arailctl install` calls bootstrap once
Added `_install_kb_bootstrap()` inside `scripts/install.sh`'s existing
`[5/5] verify` phase (before `doctor` runs), rather than introducing a new
named phase into the `source|deps|components|models|verify` phase-selection
system — smaller, additive change with the same "one non-fatal call, output
summarized" effect the architecture specifies. `bash -n` syntax-checked;
not exercised end-to-end (no live lab in this environment to install into).
Commit: `e12fca6`.

### Step 7 — docs
Documented `./arailctl pkb bootstrap`, both escape hatches, and the sticky
revocation semantics in `docs/cli.md`'s existing `pkb <op>` section (matches
where `prune` was already documented, rather than a new sibling doc — the
architecture said "a `docs/` note," not a specific file).
Commit: `87e27e9`.

## Not implemented this pass (scope, not disagreement)

Per the plan above, these ARCHITECTURE.md elements are unbuilt:

- **Caller updates (§"What each caller does with the empty state"):**
  `lab_brain.py` (Buddy's "no approved knowledge" system note),
  `agents/researcher.py`'s `_kb_search` reason-recording,
  `portal/app.py`'s goal drafter `kb_gate` field, `lab_brief.py`'s gate-state
  line, `doctor.py`'s unbootstrapped/empty distinction and warn-on-mounted
  escalation, `GET /api/pkb/review`'s `gate` block, `/dac` template's
  empty-state block and the persistent `ARAIL_APPROVED_ONLY=off` banner.
  These are the surfaces that make the *fixed* gate legible to a human;
  today's fix repairs retrieval and the mount-time bootstrap, but nothing
  yet tells Buddy to say "I could not search the KB" instead of answering
  as if it searched and found nothing empty-handed.
- **`POST /api/pkb/promote_bulk`** (scoped bulk-approve with CSRF, scope-drift
  detection, and the kind allowlist) and its `/dac` UI ("Select all in
  scope (351)").
- **`world_mount.swap()` hook** — see the flagged gap under Step 5.
- **`--all-instances` / `--world <slug>`** flags on the `bootstrap` CLI verb.

These are independent, sizeable surfaces (UI + several call sites each) and
were not started rather than half-built. The core mechanism this sprint
exists to deliver — the empty-gate bug itself, and the mount-time +
explicit-verb bootstrap that fixes it — is complete, tested, and does not
depend on any of the above landing.

## Architect feedback required

One item, not blocking (see Step 5 execution notes above): `world_mount.swap()`
is not hooked at the same "auto-approve on mount" point `mount()` is. This
wasn't in ARCHITECTURE.md's stated hook location, so it was not built without
sign-off, but a World brought in via `swap` will need the same manual
`./arailctl pkb bootstrap` the four pre-existing sealed bundles need. Worth a
line in ARCHITECTURE.md's data-flow section (or an explicit "swap is
out of scope, here's why") before this is called fully shipped.

## Final state

- 5 commits of implementation + 1 BUILD_LOG skeleton + 1 docs commit = 7
  commits total this build phase.
- New/changed test files: `tests/test_compiled_kb.py` (+15 cases),
  `tests/test_compiled_kb_bootstrap.py` (new, 21 cases),
  `tests/test_pkb_retrieve_for_agents.py` (new, 6 cases),
  `tests/test_world_mount_auto_approve.py` (new, 5 cases).
  `tests/test_pkb_gate.py` and `tests/test_world_mount.py` untouched —
  both still pass (13 and 12 cases respectively), proving the back-compat
  contracts held.
- Full targeted regression run: `pytest tests/test_compiled_kb.py
  tests/test_compiled_kb_sweep_prune.py tests/test_compiled_kb_bootstrap.py
  tests/test_pkb_gate.py tests/test_pkb_retrieve_for_agents.py
  tests/test_world_mount.py tests/test_world_mount_auto_approve.py` →
  **80 passed, 0 failed**.
  `tests/test_scouting.py::test_scouting_never_imports_compiled_kb` → pass
  (no new `compiled_kb` import in scouting).
- Broader `pytest tests/ -k "compiled_kb or pkb or world_mount"` shows
  additional failures/collection errors, all pre-existing environment gaps
  in this worktree (missing `fastapi`, `lancedb`, and a subprocess-spawned
  test that can't see the locally-installed `python-dotenv`) — none touch
  files this build changed; verified by inspecting failure tracebacks.
- No commented-out code. No TODO comments added.
- Files touched this build: `src/arail/compiled_kb.py`, `src/arail/pkb.py`,
  `src/arail/world_mount.py`, `arailctl`, `scripts/install.sh`,
  `docs/cli.md`, plus the four test files above. Nothing outside this list.
