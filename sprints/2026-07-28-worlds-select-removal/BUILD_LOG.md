# Build log: worlds-select-removal

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at `2afde18`
**Started:** 2026-07-29

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| WP1 | `src/arail/portal/app.py`, `tests/test_world_switcher.py`, `tests/test_world_import.py` | Add `in_place_switch_removed` 409 guard (CSRF → default/unmount → jail → instance_live → guard → mount) to `api_worlds_select` and `api_worlds_import`; rewrite the two named tests; add tests 3–10 (+ import parity) | `test_world_switcher.py`, `test_instance_api.py`, `test_world_import.py` | pending |
| WP2 | `src/arail/portal/static/js/nav.js`, `.../js/worlds.js`, `src/arail/portal/templates/welcome.html`, `.../templates/worlds.html`, `tests/test_worlds_ui.py`, `tests/js/world_step_harness.mjs` | Nav becomes non-mutating roster; welcome step's swap door → read-only hint; worlds.html static hint replaces dismissible banner; worlds.js surfaces the new 409 | JS harness, `test_worlds_ui.py` | pending |
| WP3 | `docs/concurrent-worlds.md`, `README.md`, `CHANGELOG.md` | Docs stop describing in-place switching as current/"this release" | grep gate | pending |

## Execution

### WP1 — Server contract

Implemented exactly per the data-flow diagram: the `in_place_switch_removed`
guard sits after the `instance_live` loop and before `mount()`, comparing
`current_mount().bundle_dir` (str) to the resolved `bundle_dir` (`Path`, cast
to `str`) so slug/path addressing can't create an asymmetry (F7). Identical
resolved bundle dir → allowed (idempotent re-bind, F6). Applied the same
guard, same message shape, to `api_worlds_import` per the ARCHITECTURE.md
ruling ("yes, same destructive swap by another door"). `api_worlds/import-zip`
was **not** touched — out of the architecture's explicit scope (only
`api_worlds_import` is named) and it delegates to the same `mount()`, so a
follow-up decision on it is for the architect, not a builder judgment call
made mid-pass.

Assumption 3 (`unmount()` never requires the bundle dir to still exist) was
re-verified by reading `world_mount.py:1515-1552`: it operates on the mount
*record* + optional `remove_staged`, never touches `record.bundle_dir` on
disk. **No `world_mount.py` change was needed** — F3's un-brick test passes
against the existing code.

Docstrings for both endpoints updated to list the new 409 code.

Test changes:
- `test_switch_a_to_b_leaves_record_on_b` → `test_switch_a_to_b_refused_record_stays_on_a`
  (inverted per spec: expects 409, A's record + A's staged dir survive).
- `test_select_tampered_bundle_409_unchanged` → rewritten to select the
  tampered fixture into an **unmounted** root, so the seal check is still the
  thing under test (the ordering hazard the architecture called out).
- Added (tests 3–10 from the strategy, `tests/test_world_switcher.py`):
  `test_swap_by_slug_while_mounted_refused`,
  `test_swap_by_path_while_mounted_refused`,
  `test_two_step_swap_unmount_then_mount_allowed`,
  `test_rebind_identical_bundle_allowed`,
  `test_refused_swap_touches_nothing_on_disk`,
  `test_swap_precedence_instance_live_over_in_place_switch`,
  `test_cross_site_swap_attempt_while_mounted_is_403`,
  `test_unmount_with_bundle_dir_deleted_still_frees_root`.
- Added import-parity tests (`tests/test_world_import.py`):
  `test_import_over_mounted_root_refused`,
  `test_import_reimport_identical_bundle_allowed`.

**Gate:** `pytest tests/test_world_switcher.py tests/test_instance_api.py
tests/test_world_import.py tests/test_world_import_zip.py tests/test_world_mount.py
tests/test_world_identity_flip.py tests/test_worlds_ui.py` → **88 passed**, 0
failed, 0 new red. `test_worlds_ui.py` is pre-existing (WP2 not yet started)
and passed unmodified, confirming zero regression on that surface from the
WP1 server change alone.

Commit: (recorded below after commit)

### WP2 — UI: nav roster, welcome step, worlds page

`src/arail/portal/static/nav.js`: deleted the mutating `fetch('/api/worlds/select', …)`
block and its `busy` lock (the `busy` flag stays, now guarding only the
`/api/worlds/import` path, which is unaffected by this sprint). Deleted the
`change-world` row and its `/welcome?step=world` route. "AI Lab (default)"
row now routes to `/worlds` when a World is mounted, otherwise renders inert
(active + disabled, no `data-action`). Non-live World rows are always
disabled now, showing the launch command in `title`/`reason` (previously
only when something else was mounted — "launchable" case). A currently-
mounted World's row is inert (✓ marker, `active + disabled`), never
clickable.

`src/arail/portal/static/js/worlds.js`: the Mount button's click handler now
re-fetches (`renderCatalog()`) after a refusal, so a same-page race (another
tab mounted between render and click, F4) re-renders the button matrix from
the server's authoritative state instead of leaving a stale "Mount" button.
The 409 message was already surfaced via the existing `r.data.message` alert
path — no separate plumbing needed.

`src/arail/portal/templates/welcome.html`: deleted `renderSwapBanner`,
`renderWhatChangedSummary`, and the Continue/Cancel confirm-pair block
entirely. Added `renderMountedHint(card, currentName)` (one line + a
`/worlds` link) and `showLaunchCommand(slug)` (copy-to-clipboard + alert,
same shape as `worlds.js`'s helper of the same name — welcome.html's is a
separate copy since the two templates don't share a JS module; noted as
tech debt, not fixed here — out of this sprint's scope). `current == null`
path (first-bind) is byte-for-byte unchanged except removing the now-dead
`if (currentSlug) { renderWhatChangedSummary(...) }` branch inside the
200-response handler. `current != null` path never calls `performMount()`;
a card click calls `showLaunchCommand(w.slug)` instead — zero fetches to
`/api/worlds/select`.

`src/arail/portal/templates/worlds.html`: replaced the dismissible
`#worlds-deprecation-notice` card (+ inline script + the
`arail.worlds.deprecation-dismissed` localStorage key) with a static
one-line `<p id="worlds-instances-hint">` above the catalog grid. No script,
no dismiss button, nothing to persist.

Test changes:
- `tests/test_worlds_ui.py::test_worlds_page_has_dismissible_deprecation_notice`
  → `test_worlds_page_has_static_instances_hint` (asserts the hint text + the
  `--world` command; asserts the dismiss button and the localStorage key are
  gone).
- Added `test_nav_js_never_posts_to_worlds_select` (no `/api/worlds/select`,
  no `change-world`, no `?step=world` in `nav.js` source) and
  `test_nav_js_still_fetches_instances_and_renders_open_link` (roster fetch +
  Open-link behavior survive).
- `tests/js/world_step_harness.mjs`: swapped the `renderSwapBanner`/
  `renderWhatChangedSummary` extraction for `renderMountedHint`/
  `showLaunchCommand`; added `navigator`/`window.alert` stubs to the sandbox
  (needed by `showLaunchCommand`). Replaced the old T14b (swap-variant
  confirm pair) with two tests matching the architecture's numbering: T15
  (current == null — exactly one POST, one navigation, no mounted hint) and
  T16 (current != null — mounted-hint + `/worlds` link rendered, a card
  click reveals the launch command via `window.alert`, zero fetches to
  `/api/worlds/select`, `goHome()` never called).

**Deviation from spec, self-caught:** the first pass of the click-handler
rewrite in `welcome.html` used `btn.addEventListener('click', function () { performMount(); })` — dropping the `return` that the original code had. Since
`dispatch()` in the test harness does `await fn({})`, this silently broke
awaiting `performMount()`'s promise and made T14 flaky/failing (the fetch
mock queue and the assertion both ran out of order). Caught by the gate
(T14 failed), fixed by restoring `return performMount();`. No spec change
needed — this was an implementation slip, not an architecture gap.

**Gate:** `node tests/js/world_step_harness.mjs` → 7/7 assertions passed.
`node tests/js/cloud_render_harness.mjs` (unrelated harness, run for
completeness) → 3/3 passed. `pytest tests/test_worlds_ui.py` → 10/10 passed.
Manual smoke deferred to QA per SPRINT.md's regression-heavy tilt (no
browser available in this environment); the source-level assertions above
cover the same DOM/fetch contracts the manual smoke would exercise.

Commit: (recorded below after commit)

### WP3 — Docs

`docs/concurrent-worlds.md`: `## The in-place World switcher is being
deprecated` → `## In-place World switching has been removed`; describes the
409 code, the instance_live-before-in_place_switch_removed ordering, and the
two survivors (instances; unmount-then-mount). `README.md:166-169`: dropped
"still works this release" / "deprecation timeline", states the removal
plainly. `CHANGELOG.md`: added a `### Removed (2026-07-28/29
worlds-select-removal — in-place World switching)` entry under `[Unreleased]`
covering the 409 code, the nav/welcome/worlds-page UI removals, and what
still works; edited the existing concurrent-Worlds "In-place Mount is
deprecated — announced this release, removed next" line to point at the new
entry instead of repeating the now-stale "removed next" framing.
`CLAUDE.md`: re-verified via grep — no mention of the dropdown's mutating
behavior — no change made.

**Gate:** `grep -rln "still works this release\|removed in the next
release\|In-place Mount is deprecated" --include="*.md" .` returns only the
two prior sprints' `ARCHITECTURE.md` files (historical spec artifacts under
`sprints/`, correctly excluded by the gate's intent) — zero hits in
`README.md`, `docs/`, or `CHANGELOG.md`.

Commit: (recorded below after commit)

## Architect feedback required

(none — all three WPs matched the spec exactly; no gaps found)

## Final state

- All three WPs complete. Final combined regression run (server +
  nav/welcome/worlds-page + JS harnesses + onboarding/first-impression/
  boot-overlay/default-catalog suites): **163 pytest passed, 1 skipped
  (pre-existing, unrelated), 0 failed** + `tests/js/*.mjs` **10/10** (7
  world-step + 3 cloud-render).
- No commented-out code. No TODO comments added.
- Files changed: `src/arail/portal/app.py`, `src/arail/portal/static/nav.js`,
  `src/arail/portal/static/js/worlds.js`,
  `src/arail/portal/templates/welcome.html`,
  `src/arail/portal/templates/worlds.html`, `docs/concurrent-worlds.md`,
  `README.md`, `CHANGELOG.md`, `tests/test_world_switcher.py`,
  `tests/test_world_import.py`, `tests/test_worlds_ui.py`,
  `tests/js/world_step_harness.mjs`, this `BUILD_LOG.md`.
- One self-caught deviation during WP2 (documented above under WP2's
  execution notes): a dropped `return` in the welcome.html click handler,
  fixed before the gate passed. No architect feedback required — the spec
  matched the codebase exactly at every WP.
