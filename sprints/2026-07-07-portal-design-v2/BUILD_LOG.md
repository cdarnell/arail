# BUILD_LOG — 2026-07-07-portal-design-v2

## Phase 0 — Prep (done)
- Branch `qukaizen/portal-design-v2` off `qukaizen/stoic-almeida-335982` (main-equivalent).
- Deleted dead `chat.legacy.html` (64K, no route; only two comment references remained).
- `.claude/launch.json` created (single uvicorn, port 8080, no reload — OOM caution). Local-only (`.claude/` is gitignored).
- Baseline pytest attempt surfaced a **pre-existing suite-hanging bug** (below).

## Found & fixed in passing: SSE cross-thread wakeup bug (commit 82ad76e)
`ActivityLog.emit()` fanned out with `asyncio.Queue.put_nowait` from whatever
thread called it. asyncio queues are not thread-safe: the event was enqueued
but an **idle** subscriber loop was never woken, so SSE delivery stalled until
unrelated traffic woke the loop. Under pytest (idle loop) the recolor QA suite
hung **forever** at `test_real_sse_route_streams_live` — confirmed pre-existing
against the pristine main checkout. Fix: subscribers register `(queue, loop)`;
cross-thread emits go through `loop.call_soon_threadsafe`. The E2E test now
drives the raw ASGI app with `wait_for`-bounded reads (starlette's TestClient
buffers entire responses and can never open an infinite SSE stream), plus a new
direct regression test for the cross-thread wakeup.

## Phase A — Foundation (commit afda0d4)
- **A3 `ui_theme.py`**: `UITheme` = 12 semantic color slots per scheme
  (`ThemeColors`; `light` slot present but None → light-READY), `personality`
  (technical/scholarly/playful) → frozen `_PERSONALITY` scalar table
  (radius/scanline/glow/motion/label/rail). `theme_css()` emits semantic
  tokens + `-rgb` companions + legacy aliases (`--green→positive`,
  `--blue→accent2`, `--amber→warn`, `--red→danger`, `--purple→info`,
  `--text-hi/--border-hi/--muted`). Glow strings + alpha tiers moved to CSS
  composition. 4 presets re-expressed; public API unchanged
  (`load_ui_theme`/`list_ui_themes`/`default_ui_theme`; `accent`/`preview_*`
  became derived properties).
- **A2 `style.css`**: `:root` now carries REAL default values (killed the 13
  circular `--x: var(--x)` placeholders) — pages render correctly even if the
  middleware injection fails; injected block is an override by source order.
  Added semantic tokens, composed glows (`--glow-accent` from
  `--glow-blur/--glow-alpha` primitives), CSS-derived alpha tiers, permanent
  legacy alias block, personality scalars (technical defaults). Deleted
  `html[data-theme]` blocks + `.theme-picker` styles. Scanlines now driven by
  `--motif-scanline-alpha`.
- **A4 fonts**: vendored JetBrains Mono 400/500/600/700 + Inter variable
  (roman+italic) woff2 into `static/fonts/` with OFL licenses; `@font-face`
  in style.css; Google Fonts `@import` removed (airgap fix). `--font-sans` /
  `--font-mono` stacks; legacy `--font` → mono.
- **A5 client-theme retirement**: nav.js theme module + FAB deleted; one-time
  `localStorage['arail-theme']` cleanup; chat.html FOUC guard + stale
  `data-theme` attr removed. Theme truth: mounted World → `LAB_UI_THEME` →
  default.
- **A6 tests**: `test_world_recolor.py` literal-guard rewritten to the v2
  contract (:root defaults must AGREE with the default theme; accent literals
  banned outside :root). New `tests/portal/test_base_template_smoke.py`
  (all page routes: 200, one theme block, nav present, no external fonts).
- Theme/identity/brand/switcher suites: **92 passed**.

## Phase A1 — base.html (in progress)
- `templates/base.html` created (title/head/nav/content/scripts blocks;
  documented Jinja pitfalls: comments don't nest, top-level `set` feeds
  `_nav.html`).
- Pilot migrated + smoke-tested: mission, graph (conditional-nav preview mode
  via `{% block nav %}{{ super() }}`), dictionary, docs_hub, plugins.
- Remaining ~19 templates: fanned out to 7 parallel agents
  (workflow `migrate-templates-to-base`), disjoint file groups, mechanical
  recipe + per-route TestClient verification. welcome.html exempt by design.

## Phase B — design panel (running)
- Workflow `design-panel-v2`: 4 independent concept mockups
  (precision-instrument / warm-observatory / editorial-lab / aurora-console)
  → 3 judge lenses (first-impression, technical-edge, systemization)
  → synthesis into `design-panel/STYLE-SPEC.md` + `winner-refined.html`.
  Mockups are token-native (v2 names) so winning values port directly into
  `ui_theme.py`.
