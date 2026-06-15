# Sprint: 2026-06-14-world-switcher

**Repo:** arail · **Branch:** qukaizen/arail-world-switcher · **Worktree:** ../arail-verify (isolated, off main)
**Owner:** Charlie D · **Opened:** 2026-06-14

## Intent

The founding thesis made tangible: **load/unload DaC Worlds like LLMs** from the portal. The loader
primitives (`mount`/`unmount`/`current_mount`) already existed; this sprint adds the **catalog + UI**, plus
a **top-bar reorganization** so the lab stays uncluttered as Worlds become first-class.

## What shipped

### A. World switcher (load/unload like LLMs)
- **Catalog:** new `WORLDS_DIR` (`config.py`, default `lab/worlds/`, env `ARAIL_WORLDS_DIR`). New
  `list_available_worlds()` + `WorldInfo` in `world_mount.py` — scans the folder, light-validates each via
  `load_bundle()` (not full `verify_seal`, which runs at mount), marks invalid dirs `valid:false` with a
  reason, de-dupes by slug, appends the current CLI-mounted World if outside the folder. Drop a
  DaC-exported bundle into `lab/worlds/` and it appears — exactly like model files in `lab/models/`.
- **Endpoints:** `GET /api/worlds` (`{worlds, current}`) + `POST /api/worlds/select` (`{slug|path|"default"}`)
  — CSRF envelope mirroring `post_airgap_toggle`; slug path-jailed via `_SLUG_RE`, `path` confined under
  `WORLDS_DIR`; bundle/seal errors → 409 (not 500), traversal → 400. Every selection uses `mount(B)`
  (atomic, re-stages KB + re-resolves the capabilities sidecar); "default" → `unmount`.
- **UI:** the nav `◆ <World> World` badge became a `<details>` dropdown (`_nav.html` + a `world-switcher`
  IIFE in `nav.js`): lists "AI Lab (default)" + available Worlds (active marker, disabled invalid rows),
  selecting → `POST select` → `window.location.reload()` (identity re-resolves per request). Unmounted shows
  a `◇ AI Lab ▾` affordance so the picker is always reachable.

### B. Top-bar reorganization → one global status bar
- Moved all live/dynamic indicators OFF the crowded top nav into a **uniform full-width status bar**
  (`_nav.html`), shown on **every page**: `⬤ Airgapped` · work-window · the full metric set (Net saved,
  Tokens, Cloud equiv, Energy, Inferences, Backend, Avg resp) · `⏸ Halt`. **Airgapped + Halt are the two
  global buttons.** A self-contained script polls `/api/system/costs` + `/api/jobs/state` globally.
- **Removed the dashboard's duplicate** `meter-bar` markup + its `refreshCosts`/`refreshJobsState`/
  `toggleMeterMore` JS + the dead meter CSS. The status bar is the single home for metrics. Top nav is now
  just brand/World-name + World switcher + nav links.

## Phase ledger

| Phase | Artifact | Status |
|---|---|---|
| plan (architect) | ARCHITECTURE.md | DONE 2026-06-14 — catalog/endpoints/dropdown design |
| build (builder) | (BUILD_LOG below) | DONE 2026-06-14 — 5 switcher commits (interrupted by API drop, finished by orchestrator) + the status-bar reorg per owner UI feedback |
| test (qa) | inline | 17 switcher tests + 52-test touched-area pass; live render verified (switcher loads/unloads; status bar global; no dup) |
| ship | — | ready to PR to main |

## Ledger notes
- **Switcher tests:** `tests/test_world_switcher.py` (17) — discovery (valid/invalid/empty), `GET /api/worlds`
  shape, `POST select` mount→flip + "default" unmount→revert, nav dropdown render, security (tampered bundle
  → 409 seal refusal; slug traversal rejected). Recolor tests updated for the badge-as-switcher trigger.
- **Status-bar consolidation:** verified the full metric set + window + halt render on non-dashboard pages
  (`/chat` etc.); dashboard `meter-bar` count = 0 (no duplicate); dashboard/chat/knowledge/agents/admin all
  still 200.
- **Owner UI decisions (2026-06-14):** consolidate all metrics into the status bar; Airgapped + Halt the
  only two global buttons; Physics palette = slate-violet (set on the vendored fixtures).
- **Commits** on `qukaizen/arail-world-switcher` (off main): `7520189` config · `e012285` discovery ·
  `46edb2b` endpoints · `17a873a` nav `<details>` trigger · `45f67f8` nav.js IIFE · `723d6a2` tests ·
  `2dfbf8d` status bar · `7b29ef2` metrics consolidation (+ CSS sweep). NOT pushed.

## Notes / next
- **PR base:** `main` (off updated main with the instant-flip foundation).
- **ROADMAP:** live-update-without-reload on select; prior-stage cleanup on swap; upstream DaC
  `dist/bundles/physics/face.json` palette → slate-violet (qukaizen-dac, parallel repo); optional
  "More ▾" grouping if the 7-metric strip reads busy.
