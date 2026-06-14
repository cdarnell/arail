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
