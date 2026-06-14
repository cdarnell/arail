# BUILD_LOG — Complete World Flip (sprint 2026-06-14-world-identity-flip)

**Persona:** builder · **Implements:** ARCHITECTURE.md (7-phase build order) · **Worktree:** arail-verify
(isolated, branch `qukaizen/arail-world-identity-flip` off origin/main). Interrupted by an API drop after
phase 5; phases 6–7 completed + verified by the orchestrator.

## Owner goals — all MET
1. **Brand flips too (full immersion):** mounting a World makes `LAB_NAME`/`LAB_LOGO` the World's identity;
   reverts on unmount. ✓
2. **Instant flip, no restart:** identity resolves from the mount sidecar at REQUEST time — no `.env` write,
   no restart. ✓
3. **Built-in AI/ML default kept:** unmounted → operator brand + default theme + generated dictionary. ✓

## Instant-flip proof (live, single process, no restart)
| state | name | theme | intent | mounted |
|---|---|---|---|---|
| before | `Autoresearch AI Lab` | (AI tagline) | `ai` | False |
| mount physics | **`Physics — Measurement & Units`** (logo `⟨Physics — Measurement & Units⟩`) | `Physics — Measurement & Units` | `other` | True |
| unmount | `Autoresearch AI Lab` | (AI tagline) | `ai` | False |
`mount()` takes NO `apply_face`/`env_path` — the params are gone; the sidecar (`world-mount.json`) is the
single source of truth.

## Phases (atomic commits)
| # | Step | Commit | Status |
|---|---|---|---|
| 1 | NEW `src/arail/identity.py` — `effective_identity(data_dir) -> Identity` live resolver | 5fd2d5b | PASS |
| 2 | `world_mount`: remove env-flip — delete `_write_face_env`, drop `apply_face`/`env_path` from mount/swap, drop `--apply-face` CLI + restart hint | e272342 | PASS |
| 3-4 | `portal/app.py`: kill module-level `_BRAND`/`_UI_THEME`; route FastAPI title, Jinja `brand`/`ui_theme` (`_identity_ctx`), banner, bootstrap goal, welcome, dashboard/mission, admin, `/api/system/theme`, `/api/brand` through `effective_identity()` | a3a199e | PASS |
| 5 | `agents/researcher.py`: source intent (+ the `other` gate) from `effective_identity().intent`, not raw env → reframes live | 027bc00 | PASS |
| 6 | tests: NEW `test_world_identity_flip.py` + rewrite `test_world_face.py` to the no-env contract | f908238 | PASS |
| 7 | this BUILD_LOG | — | PASS |

## Files
- **NEW** `src/arail/identity.py` (resolver + `Identity` dataclass + `.brand()` back-compat view).
- **edited** `src/arail/world_mount.py` (env-flip path DELETED), `src/arail/portal/app.py` (caches removed,
  reads rerouted), `src/arail/agents/researcher.py` (intent from resolver).
- **tests** NEW `tests/test_world_identity_flip.py`; rewrote `tests/test_world_face.py` to assert the
  sidecar-driven no-env behavior (no guarantee weakened — assertions track the new correct behavior).

## Security
Mounting IS the consent (owner's full-immersion decision). DATA-not-instructions boundary unchanged:
terms.json stays template-only; face text reaches a prompt only via Buddy's delimited, length-capped
`_world_framing_block` (untouched).

## Tests
- Touched-area slice (identity + world + capabilities + STT + OCR): **113 passed, 1 failed**. The 1 failure
  is `test_stt_chat_ui::test_mic_enabled_when_stt_available` — **pre-existing ordering bleed**: it passes in
  isolation and pairs cleanly with each of my new/changed test files (identity/face/dictionary), so the
  bleed originates from an unrelated pre-existing test, not this sprint (the same flakiness QA flagged in
  the merged STT work).

## ROADMAP (flagged, NOT done this sprint)
- **Full per-page UI-palette CSS injection.** `effective_identity()` returns the correct `UITheme`
  (`blue-cyan-lab` for physics), but only `welcome.html` injects `ui_theme_css`; other pages use static
  `style.css`. Wiring the palette into every template `<head>` is a follow-up — the dashboard colors do
  NOT visibly recolor on mount yet. Brand name/logo, theme, intent, dictionary, and Buddy framing DO flip.

— builder (completed by orchestrator after an API-drop interruption), 2026-06-14.

---

## Recolor (per-page UI palette)

**Persona:** builder · **Implements:** `ARCHITECTURE-recolor.md` · same isolated worktree
(`qukaizen/arail-world-identity-flip`). UI/middleware + fixture-data only — no identity / world-mount /
capability logic touched; instant-flip preserved. Closes the prior ROADMAP item ("dashboard colors do NOT
visibly recolor on mount yet").

### Mechanism
A single FastAPI `@app.middleware("http")` (`inject_ui_theme`, `src/arail/portal/app.py`) injects
`<style id="ui-theme-vars">{theme_css(effective_identity().ui_theme)}</style>` immediately before the first
`</head>` on `text/html` responses. ONE place, zero template edits, zero route edits → every page recolors,
including the 7 routes that pass no `_identity_ctx()` (`/skills`, `/design`, `/blueprints-overview`, …),
because the middleware resolves identity itself. Registered after `presence_meter`/`metrics_counter`
(idiomatic — mirrors them). Gates: content-type (`text/html` only), `</head>`-present, idempotency
(`id="ui-theme-vars"` already present → skip, so `welcome.html`'s inline block isn't doubled),
first-occurrence-only, empty-CSS no-op, `content-length` reset on the rewritten body.

### Files changed
- **`src/arail/portal/app.py`** — `Response` added to the top-level `fastapi` import; `inject_ui_theme`
  middleware added.
- **`tests/fixtures/world-bundles/{physics,world-caps-both,world-caps-stt}/face.json`** — `palette_hint`
  `blue-cyan-lab` → `slate-violet` (contrast fix). Each bundle's **`manifest.json`** re-sealed
  (`files["face.json"]` sha256 recomputed) — see DELTA below.
- **`tests/test_world_face.py`** (the `blue-cyan-lab`→`slate-violet` physics assertion) and
  **`tests/test_world_identity_flip.py:86`** (mounted physics assertion) updated to the new correct value.
  The unmounted-default assertion (`test_default_lab_unchanged`) **stays** `blue-cyan-lab` (no regression).
- **`tests/test_world_recolor.py`** — NEW (26 tests).

### Before/after page-variable proof (TestClient GET, the `/skills` no-context route + dashboard `/`)
| state | route | injected | `--bg` | accent |
|---|---|---|---|---|
| **UNMOUNTED** | `/skills` | yes | `#0a0a0f` | `--blue: #00d4ff` |
| **UNMOUNTED** | `/` | yes | `#0a0a0f` | `--blue: #00d4ff` |
| **MOUNT physics** | `/skills` | yes | `#0d1018` | `--purple: #9e8cff` |
| **MOUNT physics** | `/` | yes | `#0d1018` | `--purple: #9e8cff` |
| **UNMOUNT** | `/skills` | yes | `#0a0a0f` (reverts) | `--blue: #00d4ff` |

`/skills` previously had NO identity context at all, so this proves the recolor reaches a page the
include-partial approach would have missed. `welcome.html` GET → exactly ONE `id="ui-theme-vars"`
(idempotency respected).

### Test counts
- `test_world_recolor.py` **26 passed** (10 pages × {injection-present, mount-recolors} + happy + 4
  regression: unmount-reverts / welcome-not-doubled / JSON-untouched / static-untouched + 1 security).
- Required suite (`recolor + world_face + brand + world_identity_flip`): **56 passed**.
- Touched-area slice (`-k "world or identity or capabilit or brand or stt or ocr or recolor or theme"`):
  **266 passed, 1 skipped, 1 failed**. The 1 failure is
  `test_stt_chat_ui::test_mic_enabled_when_stt_available` — the **same pre-existing ordering bleed** the
  prior phase documented: it passes in isolation and pairs cleanly with `test_world_recolor.py` (29 passed),
  so it is unrelated to this recolor.

### Security
XSS-safe **by construction**: the injected CSS is `theme_css(ui_theme)`, and `ui_theme` is selected from the
closed frozen `_THEMES` map via `palette_hint`, which can only *pick a preset id* (the resolver's id-match
guard, `identity.py:168-170`). Test mounts a face whose `palette_hint` is
`</style><script>alert(1)</script>` → resolver falls back to the default preset; the injected block contains
a real `:root` with hex/rgba literals authored in-repo and **no** `<script` / no attacker substring.

### DELTA from the architect's spec (per the "STOP and record" rule)
- **Sealed bundles.** The spec said "edit one field" in `face.json`. In reality the vendored bundles are
  **sealed**: `manifest.json.files["face.json"]` carries a sha256 that `mount()` verifies (`SealMismatch`).
  Editing `face.json` alone broke all `test_world_face` mounts. **Resolution (mechanical, not a redesign):**
  re-seal each of the three manifests with the recomputed `face.json` hash (`world_sha256` is keyed on
  `terms.json`, unchanged, so only the per-file hash moved). One-line diff per manifest, formatting
  preserved. This stays within "vendored-fixture change for the ARAIL demo/tests."
- **Streaming body, not `.body`.** The architect's §1 sketch read `getattr(response, "body", None)`. Under
  FastAPI's `@app.middleware` (a Starlette `BaseHTTPMiddleware`), `call_next` returns a streaming response
  whose body is **not** materialized on `.body` — it must be drained from `.body_iterator`. The bare sketch
  silently no-op'd on real page loads behind the auth chain (it appeared to "work" only on a password-less
  `TemplateResponse` smoke). **Resolution:** drain `body_iterator`, buffer (HTML pages are small, fully
  rendered by Jinja), and re-emit the buffered bytes on every early-return path so the dead stream is never
  returned. Same gates/semantics as specified; just the correct body source.

### ROADMAP (documented out-of-scope CSS limits — NOT fixed here, by the architect's instruction)
- The 15 alpha-tier vars (`--green-a08 … --purple-a28`) are **self-referentially broken** in `style.css`
  (`--x: var(--x)`) — pre-existing bug, unaffected by recolor. Do NOT emit them from `theme_css()`
  (would change the unmounted default).
- Many components hard-code `rgba(0,212,255,…)`/`rgba(0,255,65,…)`/`rgba(255,176,0,…)` literals — they will
  NOT recolor (not `var()`-driven). The structural palette (bg/surface/border/text/primary accent/links/nav)
  DOES recolor; stray default-accent glints remain in a few decorated components. Sweeping these to `var()`
  is a separate design-system sprint.
- Stripping the now-redundant inline block from `welcome.html` is harmless to leave (idempotency gate).

### Commits (atomic, not pushed)
1. `fixture(world): retarget vendored physics palette_hint to slate-violet` (3 faces + 3 re-sealed manifests
   + 2 test assertions).
2. `feat(portal): inject live World palette on every page via middleware`.
3. `test(portal): per-page UI recolor + harden middleware for streaming body`.
4. this BUILD_LOG append.

— builder, 2026-06-14.
