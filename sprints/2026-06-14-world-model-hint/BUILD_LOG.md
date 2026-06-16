# BUILD_LOG — World `model_hint` Phase A (READ + SUGGEST)

**Sprint:** 2026-06-14-world-model-hint
**Repo/branch:** arail-verify · `qukaizen/arail-world-model-hint`
**Persona:** builder · **Scope:** Phase A ONLY (build-order items 1–5 + T1–T6)
**Spec:** `sprints/2026-06-14-world-model-hint/ARCHITECTURE.md`

> **Phase B NOT built — gated on G1/G2.** The Gemma default-floor (catalog row,
> `setup.sh` `MODEL_NAME` swap, sentinel-fallback, "Built with Gemma" disclosure /
> `licenses/`+NOTICE+README+Modelfile, tests T7–T9) is deliberately untouched.
> It depends on external artifacts: G1 = the `qkz-project-aware-2b` weights +
> Ollama Modelfile handoff from `qukaizen-dac`, and G2 = the Gemma Terms /
> Prohibited Use Policy disclosure. None of that is in this build.

---

## Per-step status (ARCHITECTURE §8 Phase A)

| # | Item | Status |
|---|---|---|
| 1 | `world_mount.py`: `MODEL_SIDECAR_NAME`, `current_model_hint()`, `_resolve_and_write_model_hint()`, `_remove_model_hint_sidecar()` + wiring into mount/swap/unmount | DONE |
| 2 | `chat/__init__.py`: `_resolve_hint_for_gallery()` + `gallery_view()` `model_hint` block; `app.py` fallback dict gains `"model_hint": None` | DONE |
| 3 | `chat.html`: dismissible per-mount banner above the picker (Switch / Install+cmd / advisory), localStorage dismissal, airgapped grace | DONE |
| 4 | Vendored fixtures: `world-model-available` (id `gemma3:4b`, real catalog id) + `world-model-unknown` (bogus id + bogus fallbacks); `model.json` NOT sealed | DONE |
| 5 | Tests T1–T6 in `tests/test_world_model_hint.py` | DONE (23 tests) |

## Files added

- `tests/test_world_model_hint.py` — T1–T6 (23 test functions).
- `tests/fixtures/world-bundles/world-model-available/` (copy of `world-no-caps` + `model.json`).
- `tests/fixtures/world-bundles/world-model-unknown/` (copy of `world-no-caps` + `model.json`).

## Files edited

- `src/arail/world_mount.py` — constants (`MODEL_SIDECAR_NAME`, schema string,
  id allowlist regex `^[A-Za-z0-9][A-Za-z0-9._:/-]{0,128}$`, rationale cap 280),
  the reader/parser/resolver/remover trio, and the three post-pointer wire-ins
  (mount, swap, unmount), each log-only try/except. `model.json` is NOT added to
  `_BUNDLE_FILES`. **Swap clears the old sidecar before re-resolving** so swapping
  to a World without `model.json` doesn't leave a stale hint.
- `src/arail/chat/__init__.py` — `_resolve_hint_for_gallery()` (pure + total) and
  the `gallery_view()` `model_hint` block; volatile installed/available state is
  derived HERE at read time (§2.2 / §3.2), behind the existing 1.5s-timeout
  installed-detection. Catalog wins display fields; hint supplies advisory
  rationale.
- `src/arail/portal/app.py` — `model_hint: None` added to the `gallery_view()`
  error-fallback dict (~7081).
- `src/arail/portal/templates/chat.html` — `renderModelHintBanner()` rendered at
  the top of `renderPicker()`; per-(world,id) localStorage dismissal; Switch
  reuses `selectModel()`, Install reveals the existing catalog install-command
  surface (NEVER auto-pulls), unknown is advisory-only, airgapped degrades to
  "install when online". `rationale` is `escapeHtml`'d (DATA, never a prompt).

## Design decisions honored / one resolved gap

- **Mount never fails:** all hint logic is post-pointer + log-only try/except;
  T2's `test_t2_mount_non_blocking_when_resolve_raises` proves a raising
  resolver still mounts.
- **`model.json` seal-exempt:** verified — `python -m arail.world_mount verify
  world-model-available` returns `OK` with `model.json` present; T1 asserts
  `"model.json" not in _BUNDLE_FILES`.
- **Resolved gap (recorded, not improvised around the spec):** ARCHITECTURE §2.5
  lists only mount/swap/unmount wiring. On swap, `_resolve_and_write_model_hint`
  writes nothing when the new World lacks `model.json`, which would leave the old
  World's sidecar stale. I added a `_remove_model_hint_sidecar(dd)` call
  immediately before the swap re-resolve. This is within the spec's intent
  ("swap re-resolves to the new World's hint", T6) and is covered by
  `test_t6_swap_to_no_model_clears_stale_sidecar`.

## End-to-end walk (inproc; READ + SUGGEST proven)

```
1. mount world-model-available
2. current_model_hint(): gemma3:4b | catalog_state: in_catalog
3. gallery model_hint block:
   state: recommended_available | name: Gemma 3 4B | size_gb: 3.3 | has install cmd: True
4. simulate installed → switch path
   state now: recommended_installed (Switch reuses installed select path)
5. unmount removes sidecar
   current_model_hint: None
```

Mount → `current_model_hint()` returns the recommendation → the gallery payload
shows the right state/banner data (available with size + install cmd; flips to
installed when the model is present) → unmount removes the sidecar. **Works
end-to-end.**

## Test counts + adjudication

- **New:** `tests/test_world_model_hint.py` — **23 passed** (T1–T6 + resolver +
  parser sub-cases). Security T2 is the heaviest: 9 malicious/malformed id
  cases rejected, rationale cap, fallback-drop, malformed-file-still-mounts,
  raising-resolve-still-mounts.
- **Regression slice (pre-existing, must be green):**
  `test_world_mount + test_capabilities + test_world_recolor + test_world_loader
  + test_world_switcher + test_world_dictionary` → **110 passed**.
  `test_chat_default + test_chat_model_sync + test_chat_ui` → **27 passed**.
- **Pre-existing-vs-introduced:** all warnings are pre-existing FastAPI
  `on_event` / Starlette `httpx` deprecations, unrelated to this change. No new
  failures introduced.

## Not committed (not authored by this build)

The worktree had pre-existing unstaged edits to `docs/prompt-caching.md` and
`src/arail/lab_brain.py` (owned by a parallel concern). Per the brief ("only
commit files you author"), these were **left unstaged and uncommitted**.
