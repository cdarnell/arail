# ARAIL Portal Design Overhaul — "Modern Lab, Technical Edge" + DaC World Themes

## Context

ARAIL's portal currently wears a dark "1337 terminal-hacker" skin (mono-only type, CRT scanlines, neon glows) — impressive but not inviting, and structurally fragile: no base template (~25 standalone HTML templates duplicate the page shell), three overlapping theme mechanisms that fight each other, heavy inline styles, and per-page CSS with hardcoded colors that silently breaks world recoloring.

Goal: a complete visual overhaul that is **inviting, intuitive, modern, and impressive**, designed via ultracode (multi-agent design panels), with the **DaC Worlds plugin driving the design**: one consistent layout, per-world themes carried as data — a "Hello Kitty"-style world ships pink + playful, an AI/ML world ships sharp + technical.

**User decisions (locked):**
1. Aesthetic: modern lab with technical edge (sans for reading, mono for data, generous spacing, subtle motion; keep the gradient "rail" signature; drop CRT/neon noise). Default theme = the sharp AI/ML look.
2. World theming: worlds ship validated theme data in `face.json` (hex-only colors + personality axis), falling back to existing `palette_hint` presets.
3. Light mode: dark-first, light-READY token architecture (light ships later).
4. Scope: all portal surfaces; Knowledge Canvas React iframe deferred.

**Key existing seam (reuse, don't rebuild):** `face.json:palette_hint` → `identity.py:effective_identity()` (per-request) → `ui_theme.py:theme_css()` → `inject_ui_theme` middleware (`app.py:429`) injects `<style id="ui-theme-vars">` into every HTML page — the lab already recolors live on world mount. Today it only selects among 4 hardcoded dark presets; worlds cannot ship colors (XSS-safety by construction — that guarantee must survive via strict validation).

**Verified landmines:**
- `style.css` `:root` has 13 circular accent placeholders (`--green: var(--green)`); real accent values live only in `ui_theme.py` and arrive via middleware injection.
- `nav.js` client theme toggle (`localStorage['arail-theme']`, `html[data-theme]` blocks at `style.css:~2578–2643`) fights the server theme at higher specificity — must be retired.
- Per-page CSS (`agents.css` 53K, `research.css` 39K, `knowledge.css` 29K) hardcodes `rgba(0,255,65,…)` — doesn't recolor with worlds.
- JetBrains Mono loads from **Google Fonts** — broken on the airgapped default; must self-host.
- Inline styles: tuning 62, admin 47, dashboard 39, chat 23, knowledge 22 `style=` attrs.
- `chat.legacy.html` (64K) has no route — dead, delete.
- Worlds are **sealed** bundles (`face.json` is hash-verified by `world_mount.py:verify_seal`); editing a shipped world's face.json breaks its seal — reseal happens in the sibling `../qukaizen-dac` repo; ARAIL ships fixtures.
- Stack is FastAPI, not Flask (docs drift — fix in passing).

## Execution model — ultracode as the designer

Design decisions are made by multi-agent workflows, not a single pass:

- **Design panel (start of Phase B):** a Workflow generates 3–4 independent full design concepts as self-contained HTML mockups of the dashboard + chat + world switcher (each from a different angle: e.g. "precision instrument", "warm observatory", "editorial lab"), a parallel judge panel scores them against inviting/intuitive/modern/impressive + technical-edge criteria, and the winner is synthesized with the best ideas of the runners-up into the final style spec. User sees the mockups before Phase B implementation begins.
- **Per-surface fan-out (Phase C):** parallel agents restyle disjoint surface groups under a frozen-`style.css` ownership rule.
- **Adversarial verify (Phases D/E):** hostile world-theme bundles + multi-lens review (security, contrast/accessibility, recolor regression).
- Workspace conventions kept: sprint artifacts (ARCHITECTURE.md, BUILD_LOG.md, REVIEW.md, TEST_REPORT.md) in `sprints/<id>/`, `qukaizen/` branches, architect review + QA gates.

## Phases

```
Phase 0 prep → Phase A foundation (sequential) → Phase B design panel + default theme
                                        └→ Phase D world theme block (needs only A3)
Phase B → Phase C per-surface fan-out (parallel) → Phase E tests → Phase F docs
```

### Phase 0 — Prep
- Sprint dir `sprints/2026-07-07-portal-design-v2/`; branch `qukaizen/portal-design-v2`.
- Delete `src/arail/portal/templates/chat.legacy.html` (confirm no refs: `grep -rn "chat.legacy" src/`).
- Create `.claude/launch.json`: `.venv/bin/python -m uvicorn arail.portal.app:app --port 8080`, env `PYTHONPATH=src` — **no --reload, one instance** (OOM history on this machine).
- Baseline: full pytest run + preview screenshots of the ~10 biggest surfaces for before/after.

### Phase A — Foundation (single-owner; nothing else touches style.css/ui_theme.py)
- **A1 `base.html`:** new `templates/base.html` with `title/head/body_class/nav/content/scripts` blocks; children use `{% extends "base.html" %}{% set active = 'x' %}` (top-level `set` runs before parent body, so `_nav.html` sees `active`). Migration is mechanical only (no restyling). Pilot on 5 small pages (`mission`, `docs_hub`, `plugins`, `dictionary`, `graph`) then sweep; `chat.html` last; `welcome.html` stays bespoke (nav-less) on an allowlist.
- **A2 token contract v2 in `style.css`:** real default values in `:root` (kill circular placeholders — pages render even if middleware fails; injected block becomes an override that wins by source order), semantic tokens (see below), legacy alias block, alpha tiers derived in CSS as `rgba(var(--accent-rgb), .08)`, delete `html[data-theme]` blocks + theme-picker FAB styles, remove the Google Fonts `@import`.
- **A3 `ui_theme.py` restructure:** `UITheme{id, name, description, env_value, personality, dark: ThemeColors, light: ThemeColors|None}` where `ThemeColors` = 12 hex slots (`bg, surface, surface2, border, text, muted, accent, accent2, positive, warn, danger, info`). `theme_css(theme, scheme="dark")` emits semantic tokens + `-rgb` companions + legacy names (`--green→positive`, `--blue→accent2`, `--amber→warn`, `--red→danger`, `--purple→info`, `--text-hi→text-strong`, etc.) during migration. Re-express the 4 presets; keep `list_ui_themes()/default_ui_theme()/load_ui_theme()` signatures. Light = second block later under `:root[data-scheme="light"]` — names are scheme-neutral.
- **A4 self-hosted fonts:** vendor woff2 into `static/fonts/` — JetBrains Mono (400–700) + Inter (or IBM Plex Sans), both OFL. `--font-mono` / `--font-sans` stacks with system fallbacks; legacy `--font` aliases to mono. Closes the airgap landmine.
- **A5 retire nav.js theming:** delete the theme module + FAB; one-time `localStorage.removeItem('arail-theme')` cleanup. Theme source of truth: mounted world → `LAB_UI_THEME` env → default. (Optional stretch: admin dropdown writing `LAB_UI_THEME` via the existing env-writer.)
- **A6:** update `tests/test_world_recolor*.py` to assert v2 + legacy tokens.
- **Exit gate:** pytest green; every page renders equivalent; zero visual redesign yet.

### Phase B — Design panel + new default theme (single-owner on style.css)
- Run the **ultracode design panel** (above); user reviews mockups; winning direction becomes the style spec in ARCHITECTURE.md.
- Retune default theme (`blue-cyan-lab` → sharp AI/ML: deep neutrals, confident cyan/electric accent, `personality: technical`).
- Component pass in `style.css`: nav + rail gradient (`--rail-from/to`), status bar, cards, buttons (solid primary / ghost), inputs, tables (`tabular-nums`), modals, toasts, badges, scrollbars, `:focus-visible` rings.
- Kill default neon: scanlines via `--motif-scanline-alpha` (0.02 whisper for technical, 0 elsewhere); glows only on live indicators; `body` → `--font-sans`, data components stay mono.
- Motion tokens `--dur-1/2/3`, easings; all decorative animation behind `prefers-reduced-motion`.

### Phase C — Per-surface fan-out (parallel agents, disjoint file sets)
**Ownership rule:** `style.css`, `_nav.html`, `ui_theme.py` are frozen; one integrator lands shared-component additions. Each agent owns its templates + per-page CSS only.
Per surface: tokenize raw hex/rgba (fixes world-recolor debt), hoist inline `style=` attrs, sweep legacy `--green/--blue` → semantic names in touched files, adopt sans/mono split.
Groups: **C1** dashboard+mission+admin · **C2** chat.html alone (166K; use `docs/chat-studio.spec.md`) · **C3** agents.html+agents.css+_skills_panel · **C4** knowledge+graph (+css) · **C5** research+teacher+tuning · **C6** long tail (wiki, docs, dictionary, notebooks×4, terminal, plugins, welcome).

### Phase D — World theme block (Sprint 2; depends only on A3)
- **Schema** (optional, additive to `dac.world-face/v1`):
```json
"theme": {
  "schema": "dac.world-theme/v1",
  "personality": "playful | scholarly | technical",
  "dark": { "bg": "#1a0f16", "surface": "#241521", "surface2": "#2e1b2a",
            "border": "#3d2438", "text": "#eedbe8", "muted": "#a487a0",
            "accent": "#ff6fae", "accent2": "#8fd3ff", "positive": "#7ee2a8",
            "warn": "#ffc46b", "danger": "#ff5c7a", "info": "#8fd3ff" },
  "light": null
}
```
All 12 dark keys required; unknown keys rejected; `palette_hint` stays populated as graceful degradation.
- **Validator — new `src/arail/world_theme.py`** (mirrors `skills_loader.py` containment posture): `parse_world_theme(raw) -> WorldThemeSpec | None`; rejects non-dict, >4KB, bad personality, missing/extra keys, any color failing `re.fullmatch(r"#[0-9a-fA-F]{6}", v)`; **contrast enforcement** (WCAG: text:bg ≥ 4.5, muted:bg ≥ 3.0, accent:bg ≥ 3.0) → reject-to-fallback with reason surfaced in switcher. Never raises into the request path; no raw face.json string ever reaches CSS. Theme failure ≠ mount failure (world still mounts, default-colored).
- **Integration:** `identity.py:effective_identity()` resolution becomes validated `face.theme` → `palette_hint` preset → default (~10 lines).
- **Switcher previews:** extend `WorldInfo` (`world_mount.py:~195`) with `theme_preview {start, end, accent, personality}` (read through the same validator — unmounted face.json is equally untrusted); `to_dict()` + `/api/worlds` carry it; `nav.js` renders swatches via CSSOM `setProperty`, never innerHTML.
- **Personality → token map** (frozen `_PERSONALITY` dict): radii 4/6/10px (technical) · 6/10/14 (scholarly) · 10/14/20 (playful); scanline alpha .02/0/0; glow tight/minimal/soft; durations 100–280/120–320/140–380ms; playful gets spring easing; technical gets uppercase mono section labels. **Layout/spacing/type-scale never theme-modulated — hard rule, kept out of `theme_css()`.**
- **Seals:** don't hand-edit shipped worlds; demo world resealed via qukaizen-dac later. Add `tests/world_bundle_builder.py` (`make_bundle(tmp_path, face_overrides=…)` computing sha256s at test time) for all theme fixtures — no hardcoded-hash maintenance.
- Ship one playful demo fixture world (kawaii-pink, no branded IP) to prove the Hello-Kitty-style case.

### Phase E — Test hardening
### Phase F — Docs
Rewrite `docs/portal-design.md` (token contract v2, personality table, world-theme spec, ownership rules); update `design.md`, `/docs/design.md`, `docs/chat-studio.spec.md`; fix Flask→FastAPI drift in CLAUDE.md; write `docs/world-theme-contract.md` as the cross-repo ADR handoff for `../qukaizen-dac` (their ADR-0004 gets a sibling: face.json `theme` field, validation rules, reseal requirement).

## Token contract v2 (names)

**Server-emitted per theme:** `--bg --surface --surface2 --surface3 --border --border-strong --text --text-strong --text-muted --accent --accent2 --positive --warn --danger --info` (+ auto `-rgb` companions) plus personality scalars `--radius-s/m/l/pill --motif-scanline-alpha --glow-accent/positive/warn/danger --dur-1/2/3 --ease-accent --heading-font --label-transform --label-tracking --rail-from --rail-to`.
**CSS-only (never themed):** spacing `--s-1..7`, type scale `--fs-xs..2xl`, `--lh-*`, `--elev-1/2`, `--font-sans/--font-mono`, derived alpha tiers.
**Legacy aliases (permanent this sprint, dropped after C-sweep + lint hits zero):** `--green→--positive`, `--blue→--accent2`, `--amber→--warn`, `--red→--danger`, `--purple→--info`, `--border-hi`, `--text-hi`, `--muted`, `--radius`, `--font`, glow + alpha-tier aliases.

## Top risks

| Risk | Mitigation |
|---|---|
| base.html migration breaks bespoke heads (chat.html 166K) | Mechanical-only diffs; 5-page pilot; chat last; route-parametrized smoke test |
| Cascade shift from deleting circular vars / data-theme blocks | A2 bakes current values into `:root` before B retunes; recolor tests assert injected block still wins |
| World theme → CSS injection | Fail-closed validator, hex regex, closed key set, adversarial suite, CSSOM-only swatches |
| Unreadable user palettes | WCAG contrast enforcement, reject-to-fallback with visible reason |
| style.css contention in parallel Phase C | Freeze rule + single integrator; disjoint file ownership |
| Seal breakage | Optional field; shipped worlds untouched; programmatic fixtures; reseal in qukaizen-dac |
| OOM during visual passes | Single uvicorn via launch.json, no reload, stop between passes |

## Verification

- **Smoke:** new `tests/portal/test_base_template_smoke.py` — every HTML route: 200, exactly one `ui-theme-vars` block, nav present (except welcome), no `fonts.googleapis.com`.
- **Recolor regression:** extend `tests/test_world_recolor*.py` — semantic + personality tokens flip on mount/unmount across representative pages.
- **Validator unit tests** `tests/test_world_theme_validator.py`: every rejection rule parametrized.
- **Adversarial** `tests/test_world_theme_adversarial.py` (modeled on `test_world_skill_qa_adversarial.py`): `</style><script>`, `url(javascript:)`, `expression()`, homoglyph hex, 1MB blocks, wrong types → fallback theme renders, payload bytes absent from response, mount still succeeds.
- **Token-compliance lint** `tests/portal/test_token_compliance.py`: regex-scan templates/CSS for raw hex/rgba + inline `style=` against a checked-in ratchet-down baseline; per-surface exit = baseline hits zero.
- **Visual pass per phase gate:** preview server (launch.json) → screenshots + `preview_inspect` of computed styles across all surfaces in default theme, then mount the playful fixture world and re-verify 6 key pages + switcher swatches; stop server after.

## Sprint / branch structure

1. **Sprint 1** `sprints/2026-07-07-portal-design-v2/` on `qukaizen/portal-design-v2` — Phases 0, A, B (incl. design panel), C, smoke/recolor/lint tests, design-system docs.
2. **Sprint 2** `sprints/<date>-world-theme-data/` on `qukaizen/world-theme-data` — Phase D, adversarial suite, world-theme docs, qukaizen-dac ADR note + demo-world reseal coordination.

## Critical files

- `src/arail/portal/static/style.css` (85K — token contract, components)
- `src/arail/ui_theme.py` (theme structure + `theme_css`)
- `src/arail/identity.py` (`effective_identity` resolution, ~L164)
- `src/arail/portal/app.py` (`inject_ui_theme` middleware ~L429; `/api/worlds` ~L2731)
- `src/arail/portal/templates/base.html` (new) + `_nav.html` + ~25 page templates
- `src/arail/portal/static/nav.js` (theme retirement, switcher swatches)
- `src/arail/world_theme.py` (new validator) + `src/arail/world_mount.py` (`WorldInfo`)
- Per-page CSS: `agents.css`, `research.css`, `knowledge.css`, `wiki.css`, `graph.css`
