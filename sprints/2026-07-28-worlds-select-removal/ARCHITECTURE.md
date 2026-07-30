# Architecture: remove in-place World switching

**Date:** 2026-07-29
**Sprint:** `2026-07-28-worlds-select-removal`
**Ruling being executed:** [`../2026-07-28-concurrent-worlds/VISION.md`](../2026-07-28-concurrent-worlds/VISION.md) §2
**Transitional state being retired:** [`../2026-07-28-concurrent-worlds/ARCHITECTURE.md`](../2026-07-28-concurrent-worlds/ARCHITECTURE.md) §5.3–§5.5
**Branch base:** `022a711` (merge of PR #151)

---

## Restatement

The concurrent-Worlds sprint shipped instances (`./arailctl start --world <slug>`)
and announced, but did not execute, the death of in-place World switching. This
sprint executes it. `POST /api/worlds/select` keeps exactly two jobs: bind the
*first* World into a root that has none, and unbind back to the default lab.
Every other mount — "I'm in World Y, put me in World X" — is refused at the
server with a 409 that names the instance command, because that path runs
`_sweep_other_worlds()` and `rmtree`s the other World's staged KB. The nav
dropdown becomes a pure roster/viewer, the welcome flow's "swap door" (which is
an in-place switch wearing an onboarding costume) is retired to a read-only
pointer, and the transitional deprecation banner comes down and is replaced by a
one-line static hint. Nothing about the instance runtime changes; the endpoint
is not deleted.

## Assumptions

1. `world_mount.current_mount()` is the single truth for "is a World bound in
   this root," and it is cheap (one JSON read of `world-mount.json`). Verified:
   `app.py` already calls it in `api_worlds_list` at :3386.
2. A refused select leaves disk untouched. True by construction — the guard runs
   before `mount()`, and `mount()` is already atomic-or-refuse.
3. `unmount()` never raises and does not require the bundle dir to still exist
   (docstring: "never raises; returns bool"). This is what keeps a root with a
   deleted/corrupt World un-brickable. **The builder must re-verify this in
   `world_mount.py` before relying on it; if it is false, F3 below becomes a
   code fix, not just a test.**
4. Users on the previous release who dismissed the deprecation banner have a
   `localStorage` key `arail.worlds.deprecation-dismissed`. Leaving it orphaned
   is harmless; we do not need a migration.
5. No external script or blueprint POSTs `/api/worlds/select` with a swap intent.
   Verified by grep: the only callers are `worlds.js`, `nav.js`, `welcome.html`.

## Data flow

```
                     POST /api/worlds/select {slug|path|default}
                                   │
                    ┌──────────────▼──────────────┐
                    │ CSRF envelope (unchanged)   │──► 403 cross_site / cross_origin
                    └──────────────┬──────────────┘
                                   │
                slug=="default" ───┼──► unmount()  ──► 200 {ok, current:null}   [SURVIVES]
                                   │   (always allowed, even if the bundle dir
                                   │    is gone — the un-brick path, F3)
                                   │
                    ┌──────────────▼──────────────┐
                    │ _resolve_world_dir (jail)   │──► 400 bad_request
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │ live-instance guard (kept)  │──► 409 instance_live
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────────────────┐
                    │ cur = current_mount()                   │
                    │  cur is None            → allow (BIND)  │
                    │  cur.bundle_dir == tgt  → allow (RE-BIND)│
                    │  otherwise              → REFUSE        │──► 409 in_place_switch_removed
                    └──────────────┬──────────────────────────┘
                                   │
                              mount(bundle_dir) ──► 409 mount_refused / 500
                                   │
                                   └──► 200 {ok, current:<slug>}
```

The user's swap intent is now served by two other flows, both unchanged by this
sprint: `./arailctl start --world X` (a second, isolated instance — the
recommended answer), or Unmount → Mount inside this root (two deliberate steps).

## Interface contracts

### `POST /api/worlds/select` (modified)

**Promises.** Returns 200 only for: unbind-to-default; a first bind into a root
with no `world-mount.json` record; a re-bind of the *identical* resolved bundle
dir that is already mounted (an idempotent refresh — non-destructive because the
sweep has nothing else to remove, and it is the only way to re-index a
re-sealed bundle in place). Never mutates disk on any non-200.

**Requires.** Same CSRF envelope as before (unchanged; the new guard is added
*after* it, so the cross-site 403 still short-circuits first).

**On bad input.** Unchanged: 400 `bad_request` for an unknown slug or a path
outside `WORLDS_DIR`; 409 `mount_refused` for seal/partial/schema/category
failures; 409 `instance_live` when the target has a live instance.

**New refusal.**

```json
HTTP 409
{"error": "in_place_switch_removed",
 "message": "'ai' is mounted in this lab. Switching Worlds in place was removed — one lab, one World. Run 'physics' as its own instance:  ./arailctl start --world physics   — or unmount first (AI Lab default) and then mount it here."}
```

**Ordering ruling (load-bearing, pin it in tests).** `instance_live` is checked
**before** `in_place_switch_removed`. Rationale: when both apply, "that World is
already running on :8090, open it" is the more actionable message, and keeping
the existing guard first means the shipped `test_instance_api.py` cases keep
their meaning unchanged.

**Explicitly reachable, by design:** unmount → root empty → mount. Two POSTs,
two deliberate user actions, and destructive of nothing in *any other* root by
definition (a root only ever holds one World). VISION §2 permits this; do not
"harden" it away in a later pass without superseding that ruling.

### `GET /api/worlds`, `GET /api/instances`, `GET /api/instance`

Unchanged. Read-only. The UI's whole button matrix is derived from these two
facts (`current` from `/api/worlds`, `live` from `/api/instances`).

### `worlds.js` — button matrix (already nearly correct)

**Surprise, in our favour:** the shipped matrix at `worlds.js:703-750` already
gates Mount on "nothing mounted here" and shows Launch otherwise. The only work
is (a) the Mount handler must render the new 409 message if the server refuses
anyway (race: another tab mounted between render and click), and (b) the Launch
affordance copy should stop calling itself a deprecation-era alternative.

### `nav.js` — roster only

The dropdown after this sprint contains: the "AI Lab (default)" row, one row per
catalogued World with theme swatch + liveness dot + `:port`, and the non-mutating
footer rows. Behaviour per row:

| Row | Click |
|---|---|
| World with a live instance | `window.open(url)` — unchanged |
| World, not live | non-mutating: reveal the `./arailctl start --world <slug>` command (same helper posture as `worlds.js`), or fall through to `/worlds` |
| Currently mounted World | inert, ✓ marker only |
| "AI Lab (default)" when a World is mounted | **routes to `/worlds`** — unmount lives on one surface |
| `change-world` row | **removed** (it pointed at `/welcome?step=world`) |

**Decision — keep it simple: nav does not mutate at all.** Not first-bind, not
unbind. The `fetch('/api/worlds/select', …)` block at `nav.js:953` and its `busy`
lock are deleted wholesale. A fresh lab's nav row routes to `/worlds`, which is
one click further and one surface fewer to reason about; `/worlds` is where the
grid, the seal info, and the Unmount button already live. This also removes the
last mutating POST from a component rendered on *every* page.

### `welcome.html` — world step

**Surprise, and the largest single finding:** the welcome step is *not* pure
first-bind. `welcome.html:666-670, 765-845` implement a "swap door" —
`renderSwapBanner`, a Continue/Cancel confirm pair, and
`renderWhatChangedSummary` — that fires precisely when `currentSlug` is truthy,
i.e. a World is already mounted. Under the new contract that POST returns 409 and
the confirm pair leads to an error toast. It must be converted, not left to
degrade.

New contract for the step:
- `current == null` (the first-bind case, and the only case a genuinely fresh
  lab ever sees): **unchanged**. Same grid, same single POST, same error text,
  same `goHome()`.
- `current != null`: the grid renders **non-mounting**. The swap banner is
  replaced with a short line — "This lab is bound to *AI World*. To work in
  another World, run it as its own lab: `./arailctl start --world <slug>` — or
  unmount from the Worlds page" — with a link to `/worlds`. Cards become inert
  (or reveal the launch command). `renderSwapBanner`, the Continue/Cancel
  confirm, and `renderWhatChangedSummary` are deleted.

## Failure modes

| # | Failure | Detection | Recovery |
|---|---|---|---|
| F1 | Guard placed before the `default`/unmount branch → unbind starts 409ing and the root is stuck in a World forever | `test_select_default_unmounts_and_reverts` (existing) + a new explicit "unmount from a mounted root is always 200" | Branch order is fixed in the data-flow diagram; unmount is handled and returned before any guard |
| F2 | Guard placed before the CSRF envelope → cross-site request gets a 409 body instead of 403, weakening the envelope's short-circuit | `test_select_instance_live_check_respects_csrf_envelope` (existing) + a sibling for the new code | Guard is added after CSRF, after `default`, after jail |
| F3 | **Brick case:** a root is mounted to World X whose bundle dir was deleted / corrupted / re-sealed out from under it. Can the user still get out? | New test: mount, delete the bundle dir on disk, POST `{"slug":"default"}` → 200 and `current_mount() is None` | `unmount()` operates on the record + staged dir, not the bundle. If assumption 3 turns out false, the fix is to make `unmount()` tolerate a missing bundle dir — this is a **must-not-ship-without** |
| F4 | Two tabs race: tab A mounts while tab B's grid still shows "Mount"; B clicks and gets the new 409 | Server is authoritative; JS test that the 409 `message` is surfaced in the toast, not swallowed | Show the message, re-fetch the catalog, re-render. No client-side state trusted |
| F5 | A user's muscle memory (or a stale bookmark) hits `/welcome?step=world` on a mounted lab and finds a dead-end | JS harness test: mounted state renders the instances hint + a `/worlds` link and issues **zero** POSTs | The read-only variant above; the hint names the exact command |
| F6 | Re-bind of the same bundle (refresh after re-seal) is caught by the new guard, and the only way to re-index becomes unmount→mount (which needlessly re-stages) | New test: mount X, POST X again by the same path → 200 | Explicit `cur.bundle_dir == resolved target` allowance in the guard |
| F7 | Path-vs-slug asymmetry: a swap is refused when addressed by slug but sneaks through when addressed by `path` (or vice versa) | New test issues the refused swap **both ways**; `world-a`/`world-b` share the `physics` slug, so the comparison must be on the resolved `bundle_dir`, not the slug | Guard compares resolved absolute bundle dirs, exactly as `_resolve_world_dir` returns them |
| F8 | Docs/CHANGELOG still promise in-place switching "this release," so a user reads the old paragraph and files a bug | Grep gate in CI-ish test or review: `README.md:167`, `docs/concurrent-worlds.md:95-107`, `CHANGELOG.md:38-43` | Doc WP; the deprecation section becomes a "removed in this release" section |
| F9 | The removed dismissible banner leaves an orphan `localStorage` key and dead CSS/handler | Review of `worlds.html:160-187` | Delete the block whole (markup + inline script); the orphan key is inert |

Every row has a test in the strategy below.

## Test strategy

**QA tilt: regression-heavy**, per SPRINT.md. The risk is not the removal; it is
breaking the two paths that survive.

### Existing tests whose *meaning changes* (must be edited, not deleted)

| Test | Now |
|---|---|
| `test_world_switcher.py::test_switch_a_to_b_leaves_record_on_b` | Inverted → `test_switch_a_to_b_refused_record_stays_on_a`: expects 409 `in_place_switch_removed`, `current_mount().bundle_dir` still A, and A's staged dir still present (the anti-`rmtree` assertion is the point of the test) |
| `test_world_switcher.py::test_select_tampered_bundle_409_unchanged` | **Ordering hazard.** It currently mounts `physics` first, then selects `tampered` — which under the new guard returns `in_place_switch_removed` and never reaches the seal check, silently gutting a security test. Rewrite to select `tampered` into an **unmounted** root: still 409 `mount_refused`, `current_mount() is None` after |
| `tests/js/world_step_harness.mjs::T14b` (swap door) | Replaced by the read-only-variant test (F5). T14/T15 (409-message display, exactly-one-navigation) survive as-is |
| `test_worlds_ui.py::test_page_has_dismissible_deprecation_notice` | Replaced by `test_worlds_page_has_static_instances_hint` — asserts the hint text + the `--world` command, asserts the dismiss button and the `localStorage` key are **gone** |

### New tests

Unit / API (`tests/test_world_switcher.py`, or a new `tests/test_world_select_removal.py`):
1. First bind into an empty root → 200, `current == slug`. (survivor)
2. Unbind from a mounted root → 200, `current is None`. (survivor, F1)
3. Swap by slug while mounted → 409 `in_place_switch_removed`; message contains the target slug and the literal `./arailctl start --world`. (F7)
4. Swap by path while mounted → same. (F7)
5. Two-step swap: mount A → unmount → mount B → 200, `current == B`; A's staged dir gone (the sweep is *expected* here), B's present. (the explicitly-permitted path)
6. Re-bind of the identical bundle dir → 200. (F6)
7. Refused swap touches nothing: staged dir mtimes / `world-mount.json` bytes identical before and after. (F4/F7)
8. Precedence: mounted root + target has a live registry record → `instance_live`, not `in_place_switch_removed`. (ordering ruling)
9. Cross-site swap attempt while mounted → 403 `cross_site`, not 409. (F2)
10. Unmount with the bundle dir deleted → 200, root freed. (F3, the un-brick)

UI-source assertions (`tests/test_worlds_ui.py` — same static-source style already used there):
11. `nav.js` contains no `POST` to `/api/worlds/select` and no `change-world` route.
12. `nav.js` still fetches `/api/instances` and still renders Open-as-link (no regression on the roster).
13. `worlds.js` still has all four button states and still never spawns.
14. `worlds.html` has the static hint, no dismiss button.

JS harness (`tests/js/world_step_harness.mjs`):
15. Welcome world step, `current == null` → grid mounts, exactly one POST, one navigation. (**the regression that matters most** — a fresh clone's onboarding)
16. Welcome world step, `current != null` → hint + `/worlds` link, **zero** `fetch` calls to `select`.

Regression suites that must stay green untouched: `test_instance_api.py` (all
12), `test_world_forge_seal.py`, `test_worlds_ui.py` title tests, the full
welcome-flow suite, and whatever exercises `/api/worlds/import` (import mounts
too — **the builder must check whether import into a mounted root should also be
refused; ruling: yes, it is the same destructive swap by another door, and it
should return the same `in_place_switch_removed` code**).

Performance: none — the guard adds one already-performed JSON read. Security: F2
(envelope precedence) and the tampered-bundle rewrite are the two security-
relevant cases; both are in the list.

## Tech debt

**Repaid:** the transitional two-mechanism state disappears; one destructive code
path (`_sweep_other_worlds` reachable from a single UI click) becomes reachable
only via an explicit unmount-then-mount; `nav.js` loses its only mutating POST;
`welcome.html` loses ~80 lines of swap-door machinery; three docs stop describing
a deprecated affordance as current.

**Added:** the `in_place_switch_removed` guard is a second place (alongside
`_sweep_other_worlds`'s docstring) that encodes the one-World-per-root invariant.
If `/api/worlds/import` is also guarded, that is a third. Acceptable; the
alternative is a shared helper for a three-line check.

**Net: negative.** This sprint deletes more than it adds.

## Work packages

### WP1 — Server contract (the whole behavioural change)
- `app.py::api_worlds_select`: add the `in_place_switch_removed` guard after the
  `instance_live` loop; update the docstring's "Expected failures" line.
- `api_worlds_import`: apply the same guard (see ruling above).
- Tests 1–10.
- **Gate:** `pytest tests/test_world_switcher.py tests/test_instance_api.py` green,
  including the two rewritten tests; the un-brick test (F3) passes without a
  `world_mount.py` change, or the change is made and noted.

### WP2 — UI: nav roster, welcome step, worlds page
- `nav.js`: delete the select POST + `busy` lock + `change-world` row; default row
  → `/worlds`; non-live World row → launch-command reveal.
- `welcome.html`: delete `renderSwapBanner` / swap confirm / `renderWhatChangedSummary`;
  add the read-only mounted variant. First-bind path untouched.
- `worlds.html`: replace the dismissible banner (markup + inline script + the
  `localStorage` key) with a one-line static hint above the grid.
- `worlds.js`: surface the new 409 message on the race; re-render after refusal.
- Tests 11–16.
- **Gate:** JS harness green; `test_worlds_ui.py` green; manual smoke on a fresh
  `LAB_ROOT` (welcome → first bind → home) and on a mounted lab (nav dropdown
  mutates nothing).

### WP3 — Docs
- `docs/concurrent-worlds.md` §"The in-place World switcher is being deprecated"
  → "In-place World switching has been removed"; describe the two survivors and
  the two-step swap.
- `README.md:167` paragraph: drop "still works this release."
- `CHANGELOG.md`: new entry under the next release — removal, the new 409 code,
  what still works.
- `CLAUDE.md`: no change needed — grep confirms it never describes the dropdown's
  mutating behaviour. Re-verify before claiming done.
- **Gate:** grep for "still works this release", "removed in the next release",
  "In-place Mount is deprecated" returns nothing outside `sprints/`.

## Non-goals

- No change to the instance runtime, registry, `start.sh`, `status.sh`, `stop`.
- **`POST /api/worlds/select` is not deleted.** First-bind and unbind use it.
- No shared-corpus mechanism, no one-click launch from the browser, no
  `instances/`-vs-`lab/instances/` unification, nothing else from `sprints/BACKLOG.md`.
- No re-litigation of the VISION §2 ruling.

## Recommended implementation order

WP1 → WP2 → WP3. WP1 first so the UI is written against a server that already
enforces the contract, rather than the reverse.
