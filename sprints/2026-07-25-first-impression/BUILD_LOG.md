# Build log: First-impression experience — one World moment, three doors

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at `92ac206`
**Started:** 2026-07-25
**Status: PARTIAL — steps 1-4 of 9 complete and green; steps 5-9 not started.**

This build stopped after the loop-safety core (steps 1-4) was solid and
fully tested, rather than proceeding into the remaining UI-heavy steps
(Step 3 template/JS rewrite, swap-confirmation banner, three door
retargets, dashboard card) without an adequate budget to implement and
verify them carefully. Steps 5-9 are open work for a follow-up session —
see "Remaining work" below. Nothing in steps 1-4 depends on anything in
5-9; the route is addressable and loop-safe today, but Step 3's content
is still today's un-upgraded version (still has the three swallowed
`goHome()` calls, no term-count/provenance chips, no concept strip, no
swap confirmation, no new door retargets, no first-win card).

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `scripts/reset.sh`, `tests/test_world_reset.py` | `reset pkb` drops dangling `world-mount.json` + `.world-prompt-seen` (C10) | T9/T10 | `afa0527` |
| 2 | `src/arail/world_mount.py`, `tests/test_world_first_impression.py` | `WorldInfo` + `/api/worlds` additive fields (C2) | T11/T12 | `df0b327` |
| 3 | `src/arail/portal/app.py`, `tests/test_world_first_impression.py`, `tests/test_onboarding.py` | marker helper + dashboard conditional (C3/C4) | T1-T7, T17 | `76365e9` |
| 4 | `src/arail/portal/app.py`, `src/arail/portal/templates/welcome.html`, `tests/test_world_first_impression.py` | `welcome_page()` `?step=world` branch + boot flag + Step-1 suppression (C1/A5/A6) | T8 | `cfa0383` |
| 5 | `welcome.html` | Step 3 upgrade: explainer, concept strip, enriched cards, honest failure states (C5/C6) | T13-T16 | **not started** |
| 6 | `welcome.html` | swap-variant confirmation banner + "what changed" summary (C8) | T14b | **not started** |
| 7 | `_world_hero.html`, `dashboard.html`, `nav.js` | swap doors: three retargets + new nav row (C7) | — | **not started** |
| 8 | `dashboard.html` | first-win card (C9) | — | **not started** |
| 9 | — | full local test run + `CHANGELOG.md` | — (live pass explicitly skipped, no browser in this environment) | **not started** |

## Execution

### Step 1 — `reset.sh` pkb scope fix + T9/T10 (C10, F11)

Inserted the two `rm -f` lines from C1's exact diff into `reset_pkb()`,
after the conversations-override block, before the closing `info`. Added
three new shell-driven tests to `tests/test_world_reset.py` using the
same sandbox-copy pattern as `tests/test_reset_paths.py` (copy the real
`reset.sh` into a throwaway repo root so it can never touch the real
`lab/`):

- `test_reset_pkb_drops_dangling_mount_pointer_and_rearms_marker` (T9)
- `test_reset_pkb_idempotent_when_no_mount_files_present` (T10, part 1)
- `test_reset_models_and_plugins_leave_world_mount_files_untouched` (T10,
  part 2 — no scope drift into unrelated reset modes)

No deltas from plan. Commit: `afa0527`.

### Step 2 — `WorldInfo` + `/api/worlds` additive fields + T11/T12 (C2)

Added `term_count: Optional[int]`, `provenance_tier: str`,
`categories: List[str]` to `WorldInfo`, plus a new
`_catalog_extras_from_manifest_and_spec()` helper that independently
try/excepts each field — missing or malformed data yields `None`/`""`/`[]`,
never a fabricated value, and the function itself never raises. Wired
into both `list_available_worlds()` arms (the scanned-bundle loop and the
out-of-folder current-mount arm, which now also best-effort-reads
`spec.json` alongside the `manifest.json` it already read).
`GET /api/worlds` needed no code change — it already does a straight
`to_dict()` passthrough, so the new keys arrive for free.

New file `tests/test_world_first_impression.py` created here (grows in
later steps): T11 (three cases — complete bundle, truncated `spec.json`,
manifest missing `provenance_counts`/`provenance_tier`) and T12
(`GET /api/worlds` response shape carries all 11 `WorldInfo` keys).

Confirmed pre-existing, unrelated failures in
`test_default_worlds_catalog.py` (two tests) are caused by untracked
`lab/worlds/photography/` and `lab/worlds/physics/` directories already
present in the working tree before this build started (leftover local
dev state, not a regression from this change — verified by `git stash`
reproducing the same failures against pre-sprint `HEAD`).

No deltas from plan. Commit: `df0b327`.

### Step 3 — marker helper + dashboard conditional + T1-T7, T17 (C3/C4)

Added `_world_prompt_marker()` and `_world_prompt_pending()` next to
`_lab_password_set()` in `app.py`, per C3's exact contract (lazy
`DATA_DIR` import, never raises, presence-only). Inserted C4's
try/except/else block as the *first statement* of the `dashboard()`
route — marker write happens before the redirect is constructed, which
is the structural fix for the historical redirect-loop bug.

Added T1-T7 (the full truth table: not-onboarded, onboarded+mounted,
onboarded+unmounted+marker-present, onboarded+unmounted+marker-absent
[×2 for the loop-safety check], marker-write-`OSError`, and a two-thread
concurrent-request race) plus T17 (marker touch doesn't dirty
`git status` — skips in this environment because `DATA_DIR` resolves to
a relative `lab/data` that pytest's cwd handling doesn't reliably anchor
to the repo root for a clean `Path.relative_to` check; the guard is
still exercised structurally by every other test's tmp-path isolation).

**Delta from plan:** `tests/test_onboarding.py::test_dashboard_unblocks_after_onboarding`
broke as a *direct, intended consequence* of C3/C4 — post-onboarding,
with no World mounted and the marker unset, the first dashboard request
now legitimately 302s to `/welcome?step=world` (this is exactly Door 2,
the gap the sprint exists to close) instead of rendering the dashboard
on the first hit. Updated the test to assert the new two-request
sequence (first 302, second 200) rather than leaving it red or working
around the redirect. This is not scope drift — it is the sprint's stated
purpose — but it's called out explicitly per the "no silent scope
expansion" rule.

Commit: `76365e9`.

### Step 4 — `welcome_page()` `?step=world` branch + boot flag + Step-1 suppression + T8 (C1/A5/A6)

Implemented C1's route branch verbatim (extract `step`, `.strip().lower()`,
exact-match against `"world"`, never echoed into the body). Added
`world_step`/`lab_mode` to all three `TemplateResponse` context dicts.
In `welcome.html`: wrapped the Step-1 markup in `{% if not world_step %}`
with a neutral "Loading your lab's World…" placeholder in the `{% else %}`
arm (A6 — avoids the passphrase-form flash); emitted
`window.__ARAIL_BOOT_STEP = "world"` as the sole server→client signal
(A5); added a boot trigger at the end of the inline script that calls
the *existing* (not-yet-upgraded) `showWorldStep(null)` when the flag is
set. Guarded the passphrase-form JS (`form.addEventListener(...)`) behind
`if (form)` since `form` is `null` on the placeholder branch.

Added T8 (the full `?step=` matrix).

**Architect feedback required (see section below):** C1's own prose
bad-input example list is inconsistent with C1's own pseudocode
regarding case-sensitivity of `step`. Implemented per the pseudocode
(the executable contract); test asserts the pseudocode's actual
behavior, not the prose example.

**Deliberately deferred to step 5** (per the recommended order, C5's
`showWorldStep(opts)` signature change is bundled with the Step 3
content upgrade): the boot path still calls `showWorldStep(null)` with
today's positional signature, so no swap-variant chrome exists yet and
none is expected yet — `GET /api/worlds` always returns `current: null`
in every environment this build ran in (no live mount), so this couldn't
have been exercised further without step 6 anyway.

Commit: `cfa0383`.

## Architect feedback required

1. **C1 case-sensitivity contradiction — RESOLVED 2026-07-25.** C1's
   pseudocode does `step = (...).strip().lower()` before
   `if step == "world"` — this makes `?step=WORLD`, `?step=World`, and
   `?step=world ` (trailing whitespace) all match and render the World
   step (200). C1's own "Bad input" prose, one paragraph below the
   pseudocode, had listed `?step=WORLD` as an "unknown/garbage" example
   that "falls through" (302) — directly contradicting the code block
   and the same sentence's own "lowercased" clause. **Resolution: the
   pseudocode stands; the prose was wrong and has been corrected in
   ARCHITECTURE.md** (case-insensitive matching is the deliberate,
   correct behavior — a URL fragment shouldn't be case-sensitively
   fragile). The implementation and `test_t8_welcome_page_step_matrix`
   in `tests/test_world_first_impression.py` already match this; no code
   or test change was needed, only the doc correction.

2. **Steps 5-9 are unbuilt.** Not a plan defect — a budget/scope
   boundary called out rather than rushed. See "Remaining work." A
   follow-up build session is picking these up now.

## Remaining work (not started)

- **Step 5 — Step 3 upgrade** (C5/C6, T13-T16): `showWorldStep(opts)`
  signature change; World-concept explainer; illustrative-examples strip
  (photography/biology/video-games, labeled as examples — checking
  `GET /api/worlds` at build time showed `video-games` **is** a real,
  mountable bundle in `lab/worlds/` as of PR #141, so per the task's
  explicit instruction it needs its own real C2-driven card with its own
  prose line, not double-narrated by the illustrative strip); enriched
  cards using the new `term_count`/`provenance_tier`/`categories`
  fields from step 2; and replacing the four swallowed `goHome()` calls
  with the honest failure states C6 specifies.
- **Step 6 — swap-variant confirmation** (C8, T14b): confirmation banner
  + Continue/Cancel gate + "what changed" summary, triggered when
  `GET /api/worlds`'s `current` is non-null.
- **Step 7 — swap doors** (C7): `_world_hero.html`'s primary button
  retarget, dashboard nudge link retarget, and the new nav-switcher
  "Change World…" row. Deliberately last per the recommended order —
  no door should point at an unfinished room, and steps 5-6 aren't done.
- **Step 8 — first-win card** (C9): dashboard.html addition, mirrors the
  runbook-banner `localStorage`-dismiss pattern.
- **Step 9 — full local test run + `CHANGELOG.md` entry**, plus the
  explicitly-skipped live/screenshot pass (no running portal/browser
  available in this environment — noted as a known gap for a human or a
  future session, per the task's own instruction to skip it and note the
  gap rather than attempt it).

## Final state (steps 1-4 only)

- **New/changed files:** `scripts/reset.sh`, `src/arail/world_mount.py`,
  `src/arail/portal/app.py`, `src/arail/portal/templates/welcome.html`,
  `tests/test_world_reset.py` (+3 tests), `tests/test_onboarding.py`
  (1 test updated), `tests/test_world_first_impression.py` (new, 16
  tests: T1-T8, T11, T12×2, T17).
- **Test suite status as of the last commit (`cfa0383`):**
  `tests/test_world_first_impression.py tests/test_world_reset.py
  tests/test_onboarding.py tests/test_world_switcher.py
  tests/test_world_mount.py tests/test_autochecks_boot.py` →
  **70 passed, 1 skipped** (T17, environment-dependent skip, documented
  above), 0 failed.
- `tests/test_default_worlds_catalog.py` has 2 pre-existing failures
  unrelated to this build (confirmed via `git stash` against pre-sprint
  `HEAD`) — caused by untracked local `lab/worlds/photography/` and
  `lab/worlds/physics/` directories already present before this session
  started. Not touched, not fixed, not caused by this build.
- No `git status --porcelain` drift into `lab/pkb/sources/world-ai/*` or
  `lab/worlds/*` was introduced by any test run in this build — all
  World-mount-lifecycle tests use `tmp_path` + the
  `_default_data_dir`/`_default_pkb_root`/`_default_worlds_dir`
  monkeypatch idiom; the one test that touches the real repo-rooted
  `lab/data/.world-prompt-seen` (T17) skips in this environment rather
  than writing it.
