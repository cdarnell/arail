# TEST_REPORT — 2026-07-07-portal-design-v2

**Verdict: PASS** (design-system overhaul + World-theme pipeline). Two
unrelated pre-existing failures documented below; spun off separately.

## Automated

Full portal + theme + world suite (`tests/portal/`, `tests/test_world_*`,
`tests/test_brand.py`): **437 passed, 2 failed**.

New/updated coverage this sprint:
- `tests/portal/test_base_template_smoke.py` — every page route: 200, exactly
  one injected `ui-theme-vars` block, shared nav present (welcome exempt),
  complete document, no external font fetch. (25 routes.)
- `tests/portal/test_token_compliance.py` + `token_compliance_baseline.json`
  — ratchet: raw color literals / inline `style=` counts per file may only
  decrease. Portal-wide color literals: **54 → 2** (both false positives —
  an `rgba(var(...))` builder and a `&#9656;` glyph).
- `tests/test_world_theme_validator.py` (22) — every rejection rule for the
  `dac.world-theme/v1` validator: bad hex forms, injection payloads in color
  slots, missing/extra keys, bad personality, oversize, contrast failures.
- `tests/test_world_theme_adversarial.py` (13) — seal-valid hostile bundles
  mount successfully, render with the fallback theme, leak zero payload bytes;
  valid + hacker-personality themes flow end-to-end.
- `tests/test_world_recolor.py` / `_qa.py` — updated to derive expected values
  from `ui_theme.py` (no pinned hex); the SSE cross-thread wakeup regression
  guards.
- qukaizen-dac side (PR #21): `tests/arail-theme.test.ts` (29) — lockstep
  validator mirror.

### Fixed in passing (real bugs this work surfaced)
- **SSE missed-wakeup hang** (`activity.py`): `emit()` from a foreign thread
  enqueued but never woke an idle subscriber loop → the recolor QA suite hung
  forever. Fixed with `call_soon_threadsafe`. (commit 82ad76e)
- **Card-count regex** + **SSE `_run` event-loop ownership**: two tests the
  Phase C sweep / combined ordering surfaced; hardened. (commit cf8fe77)

### Pre-existing failures (NOT this sprint — spun off)
- `test_opencode_config_lifecycle.py::...OPENCODE_CONFIG_DIR_env`
- `test_opencode_lifecycle.py::...log_rotation_at_10mb`
Both fail identically on a pristine `main` checkout; a `fake_popen` signature
drift + log-rotation issue in the opencode service, unrelated to the portal.

## Visual (single uvicorn, OOM-safe)

Preview at 1280×900, screenshots + `preview_inspect` computed styles:
- **Default (Warm Observatory)** — dashboard & chat: warm-indigo ground
  (`#110e1c`), Inter prose, amber primary buttons with dark ink, cyan
  links/live-data/model-names, mono tabular status bar, the gradient rail,
  glow budget respected. `body` font-family = Inter; `.btn-primary` bg
  `#ffb35c` with dark ink; logo = mono chip on `--surface2`, no glow.
- **AI World mounted (hacker skin)** — dashboard & agents: full flip to
  near-black `#0a0a0f`, green accent `#00ff41`, mono headings, scanline +
  glow personality; brand → "⟨AI & Machine Learning⟩", identity + knowledge +
  look all swap from one mount. `/agents` (heaviest per-page CSS, formerly
  non-recoloring) recolors correctly — the core Phase C debt is closed.
- Unmount reverts cleanly to the default.

## Not covered / follow-ups
- Light scheme: architected (scheme-neutral tokens, `ThemeColors.light` slot)
  but not shipped — dark-first per plan.
- Knowledge Canvas React/Tailwind iframe island: out of scope, unchanged.
- `docs/design.md` (root philosophy) + `chat-studio.spec.md`: light touch
  pending; `docs/portal-design.md` fully rewritten to v2.
