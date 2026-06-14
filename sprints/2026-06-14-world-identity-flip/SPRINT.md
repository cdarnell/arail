# Sprint: 2026-06-14-world-identity-flip

**Repo:** arail · **Branch:** qukaizen/arail-world-identity-flip · **Worktree:** ../arail-verify (isolated, off origin/main)
**Owner:** Charlie D · **Opened:** 2026-06-14

## Intent

Make a mounted DaC World flip ARAIL's **entire identity** — completely and instantly. Three owner
decisions drove it: (1) the **brand** (name/logo) flips to the World too, not just theme/dictionary;
(2) the flip is **instant** — no `.env` write, no `./arailctl restart`; (3) the built-in **AI/ML default**
stays the baseline when nothing is mounted. Default = AI/ML lab; mount physics → the whole lab becomes
physics; unmount → back to AI/ML.

## Win conditions — all MET (QA PASS)

- **Brand flips:** mounted → `LAB_NAME`/`LAB_LOGO` are the World's (`Physics — Measurement & Units`,
  `⟨Physics — Measurement & Units⟩`); unmounted → operator brand.
- **Instant, no restart:** identity resolves from the mount sidecar at REQUEST time. Proven live in one
  process: GET dashboard (AI/ML) → `mount()` → GET again → physics — with **no `.env` write, no restart**.
- **AI/ML default preserved:** unmounted == today's behavior (operator `LAB_NAME`/defaults, generated
  dictionary, AI theme); an operator's own `LAB_NAME`/`LAB_INTENT` still wins unmounted.

## Scope decisions

- The `.env` face-flip path was **removed entirely** (the source of the restart requirement): deleted
  `world_mount._write_face_env`, dropped `apply_face`/`env_path` from `mount`/`swap`, removed the
  `--apply-face` CLI flag + restart hint. The sidecar (`world-mount.json`) is the single source of truth.
- Mounting **is** the consent now (replacing `--apply-face`) — the owner's full-immersion decision.
- **OUT (ROADMAP):** full per-page UI-palette CSS injection. `effective_identity()` returns the correct
  `UITheme` (`blue-cyan-lab`), but only `welcome.html` injects `ui_theme_css`; other pages use static
  `style.css`. So brand/theme/intent/dictionary/Buddy-framing flip on mount, but the dashboard **colors do
  not visibly recolor yet**. Wiring the palette into every template `<head>` is a follow-up.

## Phase ledger

| Phase | Artifact | Status |
|---|---|---|
| plan (architect) | ARCHITECTURE.md | DONE 2026-06-14 — `effective_identity()` resolver; env-flip removal; call-site inventory |
| build (builder) | BUILD_LOG.md | DONE 2026-06-14 — 7 phases (interrupted by API drop after phase 5; phases 6–7 finished + verified by orchestrator) |
| review (architect) | — | folded into QA |
| test (qa) | TEST_REPORT.md | DONE 2026-06-14 — WEAK_PASS → **PASS** after the one test-only blocker fix |
| ship | — | ready (QA-clean; not pushed) |

## Ledger notes

- **NEW `src/arail/identity.py`** — `effective_identity(data_dir) -> Identity` (name, logo, theme, intent,
  intent_name/description, vocabulary_register, ui_theme, world, mounted; `.brand()` back-compat). Mounted
  → from `mounted_face()` + manifest, per-field fallback to operator brand/default; unmounted →
  `load_brand()` + built-in AI/ML defaults. Resolved per request (no cache — mirrors the dictionary flip).
- **`portal/app.py`** — killed module-level `_BRAND`/`_UI_THEME`; new per-request `_identity_ctx()` spread
  into identity-rendering routes (FastAPI title, dashboard/mission, nav brand, welcome, admin,
  `/api/system/theme`, `/api/brand`, bootstrap goal, banner). **`researcher.py`** sources intent (+ the
  `other` gate) from the resolver → reframes live. Buddy `_world_framing_block` already flips live (untouched).
- **Security:** mounting = consent; DATA-not-instructions boundary intact — terms stay template-only; face
  text reaches a prompt only via Buddy's delimited, length-capped framing block. QA's hostile-face probe
  (name/`domain_framing` = "ignore previous instructions…", `<script>` in name) → inert display text,
  HTML-escaped, never an instruction, no XSS. Missing/invalid face → per-field graceful fallback.
- **QA blocker (fixed, `c7289f5`):** `test_brand.py::test_portal_templates_expose_brand` still asserted the
  removed module-level Jinja `brand` global; rewritten to the per-request `_identity_ctx()` contract (the
  global intentionally NOT reintroduced — it was the restart bug). QA confirmed the rewritten
  `test_world_face.py` was **strengthened**, not weakened.
- **Tests:** touched-area slice 101 passed; identity suite 23 passed; brand suite 7 passed. The one prior
  slice failure (`test_stt_chat_ui::test_mic_enabled`) is pre-existing ordering bleed (passes in isolation;
  present at origin/main).
- **Commits** on `qukaizen/arail-world-identity-flip` (off origin/main): `5fd2d5b` resolver · `e272342`
  env-flip removal · `a3a199e` portal reroute · `027bc00` researcher · `f908238` tests · `9323c42` docs ·
  `c7289f5` QA fix. NOT pushed.

## Notes / next

- **PR base:** `main` (this branch forked origin/main, which has the merged #77/#78/#81 via #84).
- **Demo (instant flip, no restart):** mount `tests/fixtures/world-bundles/world-caps-both` → the dashboard
  title, nav brand, mission card, dictionary, and Buddy/Researcher framing read "Physics — Measurement &
  Units" immediately; unmount reverts to "Autoresearch AI Lab". (Page colors flip = the ROADMAP follow-up.)
- **ROADMAP:** per-page UI-palette CSS injection (visible recolor everywhere); optionally a default AI/ML
  *World bundle* (owner chose to keep the built-in default for now).
