# Review: remove in-place World switching

**Date:** 2026-07-29
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `557c5a7` (commits `18a8d5c`, `d2bac46`, `557c5a7`)
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at `2afde18`
**Reviewer runs:** `pytest tests/test_world_switcher.py tests/test_world_import.py
tests/test_world_import_zip.py tests/test_instance_api.py tests/test_worlds_ui.py
tests/test_world_mount.py -q` → **77 passed**; `node tests/js/world_step_harness.mjs` → **7/7**.

## Verdict: BLOCK

One BLOCK (the third door, `/api/worlds/import-zip`, is still a one-click
destructive in-place switch), three ASKs, three INFOs. Everything the spec
*named* was built correctly and the guard order is right; the failure is that
the spec's own ruling ("import is the same destructive swap by another door")
was applied to one import endpoint and not the other, and the builder correctly
escalated that rather than deciding it. This is that decision.

---

## The `/api/worlds/import-zip` ruling

**Ruling: it must be guarded, and it is a BLOCK, not a follow-up.**

The builder's reasoning for deferring ("out of the architecture's explicit
scope") is procedurally right and substantively wrong. ARCHITECTURE.md §Test
strategy's ruling was written about *category* — "import mounts too … it is the
same destructive swap by another door" — and import-zip is that same door with
an unzip step in front. The scope line said `api_worlds_import` because the
architect enumerated endpoints from memory, not because import-zip was
considered and exempted. Read the ruling by its rationale, not its enumeration.

Severity is BLOCK rather than ASK because of real reachability, which I checked
rather than assumed:

- `nav.js:1` renders the World-switcher on **every page**; the `add` row calls
  `showImport()` (`nav.js:794-880`), which offers a `.zip` file picker posting
  to `/api/worlds/import-zip` (`nav.js:873`).
- That row is **not** gated on "nothing mounted here" — this sprint made the
  nav non-mutating for *select*, but deliberately kept Import (`nav.js:640-643`
  comment: "Import stays here (it only mutates an EMPTY root; see
  api_worlds_import's own in_place_switch_removed guard for the mounted case)").
  That comment is true of `/import` and **false of `/import-zip`**.
- So on a mounted lab: open the nav badge → "Add a World…" → drop a friend's
  zip → `mount()` at `app.py:3747` → `_sweep_other_worlds()` (`world_mount.py:1469`)
  `rmtree`s the mounted World's staged KB layer. Exactly the data-loss path this
  sprint exists to close, still reachable in two clicks, now *behind* a UI and a
  doc set that both tell the user in-place switching was removed. Shipping the
  removal message while leaving the least-obvious door open is worse than
  shipping neither.

The shipped state also makes the two import doors behave differently for
identical user intent, which is the kind of asymmetry that survives for years.

---

## Findings

### [BLOCK-1] `import-zip` mounts over an occupied root — `src/arail/portal/app.py:3730-3755`

No `current_mount()` check anywhere between the CSRF envelope (`:3697-3707`) and
`mount(bundle_dir)` (`:3747`). Also absent: the `instance_live` check that
`api_worlds_select` carries.

**Fix (concrete).** Put the guard immediately after the CSRF envelope, *before*
`await upload.read()` — refusing before extracting an untrusted archive is both
cheaper and the safer posture:

```python
# after the Origin/Host check, before pulling the multipart body
from arail.world_mount import current_mount
cur = current_mount()
if cur is not None:
    return _err(409, {
        "error": "in_place_switch_removed",
        "message": (
            f"'{cur.world}' is mounted in this lab. Switching Worlds in place "
            "was removed — one lab, one World. Unmount first (AI Lab default) "
            "on the Worlds page, then import this .zip here — or run the "
            "imported World as its own instance."
        ),
    })
```

Note there is **no** identical-bundle exemption here, and that is correct, not an
oversight: the zip is always extracted to a fresh `tempfile.mkdtemp()` staging
dir (`:3731`), so `bundle_dir` can never equal `cur.bundle_dir`. Do not
copy/paste the `!=` comparison from the other two endpoints — it would read as
if a re-import could be exempt and mislead the next reader.

Also update the docstring's "Expected failures" line (`:3683-3685`) and add
`tests/test_world_import_zip.py::test_import_zip_over_mounted_root_refused`
(mount `physics`, POST a zip of another bundle, assert 409
`in_place_switch_removed`, assert `current_mount().world == "physics"` and that
`pkb/sources/world-physics` still exists — the anti-`rmtree` assertion is the
point, as in `test_switch_a_to_b_refused_record_stays_on_a`).

Then fix the now-stale comment at `nav.js:640-643`, which asserts a guard that
will finally be true.

### [ASK-1] A World refuses to re-bind to itself after an external import — `app.py:3479-3489`, `app.py:3579-3591`

Reproduced (throwaway test, not committed):

```
import PHYSICS (external path) → 200
record bundle_dir: <repo>/tests/fixtures/world-bundles/physics
catalog now contains: ['physics']
POST /api/worlds/select {"slug": "physics"} → 409
  "'physics' is mounted in this lab. … Run 'physics' as its own instance"
```

Cause: `mount()` records the *source* dir (`world_mount.py:1485`), then
`_adopt_into_catalog()` (`:1494`) copies it to `WORLDS_DIR/<world>`. The slug
path and the recorded path are two different strings for one World, so F6's
idempotent re-bind is refused for every externally-imported World, with a
message that recommends running a World as its own instance *because it is
already mounted here*. Harmless to disk (fails safe), corrosive to trust.

**Fix.** Either (a) narrow: allow when `cur.world == bundle_dir.name` in both
guards, or (b) better, at the root: have `mount()` write the adopted catalog dir
into the record when `_adopt_into_catalog()` returns a path, so one World has one
canonical `bundle_dir`. (b) is the real fix but touches mount-record semantics —
if you take (a) now, file (b) in `sprints/BACKLOG.md`. Either way add a
regression test in `tests/test_world_import.py`.

### [ASK-2] The un-brick path (F3) has no door left in the browser — `src/arail/portal/static/js/worlds.js:720-730`

Unmount is rendered *per card*, only for a catalogued World with `w.mounted`. If
the mounted World's bundle dir is gone from the catalog (the exact F3 scenario),
no card claims `mounted`, so no Unmount button renders anywhere — and this sprint
deleted the one catalog-independent unbind door that used to exist, the nav
dropdown's `action: 'default'` POST (`nav.js`, removed in `d2bac46`). F3 is
proven at the API layer (`test_unmount_with_bundle_dir_deleted_still_frees_root`
passes) and unproven at the UI layer, where it now regresses.

Not a BLOCK: `./arailctl world unmount` (`arailctl:182`) still frees the root,
and `DELETE /api/worlds/{slug}` unmounts before deleting
(`world_routes.py:475-478`), so the common "I deleted the mounted World" path is
safe. It is out-of-band deletion/corruption that strands a browser-only user.

**Fix.** In `renderCatalog()`, when `data.current` is truthy but no rendered card
has `w.mounted`, render a standalone "Unmount current World (<name>)" control
above the grid posting `{"slug":"default"}`. Cheap, and it makes the invariant
"the root can always be freed from the UI" structural instead of incidental. At
minimum, add the `./arailctl world unmount` escape hatch to
`docs/concurrent-worlds.md`'s new section.

### [ASK-3] `./arailctl world swap <dir>` still does the thing the docs say was removed — `arailctl:182`

The CLI help still advertises `world … | swap <dir>`, an in-place switch. The new
docs say flatly "In-place World switching has been removed." Both can be true
(an explicit CLI verb is the same posture as the permitted unmount→mount), but
not silently. **Fix:** one line in `docs/concurrent-worlds.md` — the CLI keeps
`world swap` as a deliberate operator escape hatch, unavailable from any UI — or
retire the verb. Pick one; don't leave the contradiction.

### [INFO] Duplicated guard body

The same 12-line refusal now appears at `app.py:3479` and `app.py:3579`, and will
appear a third time after BLOCK-1. At three copies, extract
`_refuse_in_place_switch(cur, target_slug) -> Optional[JSONResponse]`.
ARCHITECTURE.md predicted this debt and accepted two copies; three is the
threshold it named.

### [INFO] `showLaunchCommand()` duplicated in `welcome.html` and `worlds.js`

Builder flagged it and correctly declined to fix it in-sprint. File it.

### [INFO] Dead CSS check — clean

`wc-swap-banner`, `wc-swap-confirm`, `wc-swap-cancel`, `wc-what-changed` have
zero remaining references anywhere in `src/arail/portal/` (grepped). The
`arail.worlds.deprecation-dismissed` localStorage key is orphaned and inert, as
Assumption 4 permits. No dead UI states, no unreachable JS in the welcome flow.

---

## Spec adherence

Strong on everything the spec enumerated.

- **Guard order at `select` is exactly the diagram** (`app.py:3419-3489`): CSRF
  → `default`/unmount (returns at `:3444`, before any guard, so F1 cannot bite)
  → `_resolve_world_dir` jail → `instance_live` → `in_place_switch_removed` →
  `mount()`. The ordering ruling is pinned by
  `test_swap_precedence_instance_live_over_in_place_switch` and F2 by
  `test_cross_site_swap_attempt_while_mounted_is_403`. Both pass.
- **Idempotent re-bind is robust against symlinks and trailing slashes.**
  `_resolve_world_dir` returns a `.resolve()`d `Path` (`app.py:3242, 3245`) and
  the record stores `str(bundle_dir.resolve())` (`world_mount.py:1485`), so both
  sides of the `!=` are canonical absolute strings — `..`, a trailing `/`, and a
  symlinked path all normalize to the same comparison. The one asymmetry that
  survives is ASK-1, which is about adoption, not path normalization.
- **F7 (slug-vs-path) is genuinely covered**: the path test uses
  `world-a`/`world-b`, two dirs sharing the `physics` slug, so a slug-based
  comparison would have passed it wrongly. Good fixture choice.
- **The tampered-bundle security test still bites.** Verified by reading it, not
  by trusting the log: `test_select_tampered_bundle_409_unchanged` now asserts
  `current_mount(data) is None` *before* the select and still asserts
  `error == "mount_refused"` after. The new guard is provably not preempting the
  seal check — with a mounted root it would have returned
  `in_place_switch_removed` and the test would have gutted itself silently. This
  was the single most dangerous item in the sprint and it was handled correctly.
- **Welcome first-bind intact.** `current == null` still reaches `performMount()`
  directly (`welcome.html:804-806`); the mounted branch calls
  `showLaunchCommand()` and issues zero `select` fetches. Harness T15/T16 cover
  both; 7/7 green.
- **The self-caught `return performMount()` fix is sound.** `dispatch()` in the
  harness does `await fn({})`; without the `return`, the handler resolves before
  the mount promise and the fetch-queue ordering assertions race. Restoring the
  `return` restores the awaited chain. Correct diagnosis, correct fix, correctly
  disclosed — this is what a build log is for.
- **Deviation:** `api_worlds_import_zip` not guarded (BLOCK-1). Acknowledged by
  the builder, escalated rather than silently decided. That is the right
  behaviour; the answer is "guard it."

## Test coverage assessment

Tests 1–10 and 11–16 from the strategy all exist and pass; the two rewritten
tests kept their teeth. 77 passed across the six suites I ran; `test_instance_api.py`
(the 409 `instance_live` path and the roster) is green **untouched**, so
regression risk to instance flows is nil — this sprint changed no instance code
and the nav still fetches `/api/instances` and renders Open-as-link
(`test_nav_js_still_fetches_instances_and_renders_open_link`).

**Gaps:** (1) no test for `/api/worlds/import-zip` over a mounted root — the
BLOCK; (2) no test for the re-select-after-external-import case — ASK-1; (3) F3
is covered at the API layer only, not in the JS/UI layer — ASK-2.

## Performance assessment

N/A. The guard is one `current_mount()` JSON read on a user-initiated POST,
already performed elsewhere in the same request family. Nothing on a hot path.

## Tech debt delta

Matches the architecture's prediction and its direction (net negative: ~250 lines
deleted, one destructive path made two deliberate steps, nav's last mutating POST
gone). Unpredicted additions: the duplicated `showLaunchCommand()` in
`welcome.html`, and — once BLOCK-1 is fixed — a third copy of the guard, which
crosses the threshold ARCHITECTURE.md set for extracting a helper. Both are
INFO-level and belong in `sprints/BACKLOG.md`, not in this sprint.

## Required actions before merge

1. **BLOCK-1** — guard `/api/worlds/import-zip` after the CSRF envelope with an
   unconditional `in_place_switch_removed` refusal when anything is mounted; add
   the anti-`rmtree` regression test; update the docstring and the now-stale
   `nav.js:640-643` comment.
2. **ASK-1** — allow (or canonicalize) the self-re-bind of an externally
   imported World; add the regression test. If you take the narrow fix, file the
   record-canonicalization follow-up.
3. **ASK-2** — add the catalog-independent Unmount control on `/worlds`, or at
   minimum document `./arailctl world unmount` as the un-brick path in
   `docs/concurrent-worlds.md`.
4. **ASK-3** — reconcile `./arailctl world swap` with the docs' removal claim.
5. File the two INFO items (guard helper extraction, `showLaunchCommand`
   duplication) in `sprints/BACKLOG.md`.

Re-review after 1; 2–4 may ship in the same pass. Actions 2–4 alone would be a
WEAK_PASS; action 1 is what makes this a BLOCK.
