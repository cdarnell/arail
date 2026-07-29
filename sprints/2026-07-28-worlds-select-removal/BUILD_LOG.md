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

## Architect feedback required

(none yet — WP1 matched the spec exactly, no gaps found)

## Final state (partial — WP1 only)

- Tests passing (targeted gate suites): 88/88.
- Files changed: `src/arail/portal/app.py` (+~45 lines), `tests/test_world_switcher.py`
  (+~120 lines, 2 rewrites), `tests/test_world_import.py` (+~25 lines).
- WP2, WP3 not yet started.
