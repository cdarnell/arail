# TEST_REPORT — UI recolor (world-identity-flip follow-up)

**Persona:** qa (paranoid) · **Scope:** the per-page UI-palette recolor middleware + the slate-violet
fixture retarget. **Verdict: PASS.** (Adversarial checks run directly by the orchestrator after the QA
subagent hit a transient server rate-limit; the highest-risk item — streaming/SSE — was the first probe.)

## 1. SSE / streaming NOT broken (the key risk) — PASS
A body-buffering middleware is the classic way to break Server-Sent Events. Verified the **ordering is
gate-before-drain**: `inject_ui_theme` (app.py:406) calls `call_next`, reads `content-type`, and at
**app.py:410-411 returns non-`text/html` responses UNTOUCHED** ("JSON, SSE, static, downloads, redirects")
*before* any `body_iterator` drain. The two streaming endpoints — chat `text/event-stream`
(`openai_compat.py:405`) and `activity_stream` (`app.py:2433`) — are `text/event-stream`, so they never
enter the buffering branch and continue to flush incrementally. SSE is safe **by construction**, not by
luck. Content-Length is recomputed on the modified path (`app.py:467`, "stale length is the one trap");
the unmodified passthrough re-emits the original bytes+headers.

## 2. Recolor correctness (incl. no-identity-context routes) — PASS
Live via TestClient on `/skills` (a route that passes NO `_identity_ctx()`):
- UNMOUNTED → `<style id="ui-theme-vars">` present, `--bg: #0a0a0f` (default blue-cyan).
- MOUNT physics (`world-caps-both`) → `--bg: #0d1018` (slate-violet); recolor reaches a page that
  previously had no identity context — the middleware approach is why.
- UNMOUNT → reverts to `#0a0a0f`. Idempotent (welcome.html's inline block not doubled); empty-CSS /
  no-`</head>` → inert no-op (verified in code + the 26-case suite).

## 3. Re-seal integrity — PASS
The 3 edited bundles (`physics`, `world-caps-both`, `world-caps-stt`) mount cleanly (`verify_seal` ok,
`palette_hint='slate-violet'`). The re-seal did NOT disable the check: a 1-byte tamper of `face.json`
(manifest unchanged) → `SealResult(ok=False, "Seal mismatch on face.json")` and `mount()` **refuses** with
`SealMismatch`, naming the file + both hashes. Tamper detection intact.

## 4. XSS / injection — PASS
`palette_hint` only **selects a closed preset id** (exact match against the frozen theme map); raw
`face.json` text never reaches the emitted CSS. Mounting the `hostile` fixture → injected CSS contains
ONLY preset variable values (`:root { --bg: #0a0a0f; … }`), zero raw face text. The `<style>` content is
preset-derived and can't break out of the tag. Safe by construction.

## 5. Regression — PASS (no new failures from the middleware)
- recolor + identity + face + brand suites: **56 passed**.
- prior instant-flip + world/dictionary/capability/STT/OCR: **61 passed** — the middleware did not regress
  the prior sprint's behavior.
- Touched-area slice (builder): 266 passed / 1 skipped / 1 failed — the 1 failure is the pre-existing
  `test_stt_chat_ui::test_mic_enabled_when_stt_available` ordering bleed (passes in isolation; present at
  origin/main), NOT introduced here.

## Residual risks (non-blocking, ROADMAP)
- **R1 (cosmetic, pre-existing):** some `style.css` accent glows hard-code `rgba(0,212,255,…)` literals
  (not `var()`-driven) and the alpha-tier vars are self-referential/broken in the static CSS — these do NOT
  repaint on mount. The structural palette (bg/surface/text/accent/links/nav) does. A design-system
  follow-up should make the remaining accents var-driven. Not introduced by this sprint.
- **R2:** the vendored physics fixtures now declare `slate-violet` while the upstream DaC
  `dist/bundles/physics` still declares `blue-cyan-lab` — a vendored-vs-source divergence; the upstream
  palette is DaC's to update (parallel repo, not touched).

— qa (orchestrator-run after rate-limit), 2026-06-14. No `src/` edits; no test weakened.
