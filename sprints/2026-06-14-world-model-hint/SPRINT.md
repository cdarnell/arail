# Sprint: 2026-06-14-world-model-hint

**Repo:** arail · **Branch:** qukaizen/arail-world-model-hint (off main) · **Owner:** Charlie D · **Status:** DESIGN (review before build)

## Intent
The capstone of World-driven labs: **a World declares its ideal brain.** A mounted World flips knowledge/
theme/agents/capabilities/colors — but today the inference model stays the weak 1B default. Add a
bundle-declared **`model_hint`** (sibling to `palette_hint`/`capabilities`): on mount ARAIL **suggests/
loads** the World's recommended model (consent-gated); the default (no World) becomes a capable ~2B Gemma
generalist (the owner's `qkz-project-aware-2b`).

## Owner decisions
- Direction: **design the World-declared model** (model_hint) — visionary + architect pass (this sprint).
- Default generalist: the owner's **Gemma 2B `qkz-project-aware-2b`** (built in the parallel session).
- Wedge: ARAIL **READS** a seal-exempt, mount-non-blocking model_hint and **SUGGESTS** via the existing
  picker (no silent download); plus the 2B-Gemma default-floor. Auto-load/pinning = ROADMAP.

## Design (DONE — VISION.md + ARCHITECTURE.md)
- **`model.json`** seal-exempt bundle sibling, `dac.world-model/v1` (`recommended.id` + family/size_gb/
  good_at/rationale/fallback[]; fully optional; DATA, never prompt-injected; id allowlist-validated).
  DaC emits; ARAIL only reads. Mirrors `capabilities.json` exactly.
- **`world-model.json` sidecar** + `current_model_hint()`/`_resolve_and_write_model_hint()` wired
  post-pointer into mount/swap/unmount (log-only, never fails mount). States: recommended_installed /
  recommended_available / recommended_unknown / none — installed-check derived at READ time (portal
  gallery), off the mount hot-path (a hung Ollama can't slow a mount).
- **Suggest-UX:** the existing chat model picker — additive `model_hint` block on `gallery_view()` →
  a dismissible per-mount banner: one-tap Switch (installed) / consent Install+Switch (available, size
  shown) / advisory (unknown). Never silent, never blocks, per-(world,id) dismissal, airgapped-graceful.
- **Default floor:** catalog row `qkz-project-aware-2b` (gemma) + `setup.sh` MODEL_NAME, with a
  sentinel-fallback to `llama-ai-eng` so a fresh clone is never model-less until the weights land.

## Ship-gates (carried from the visionary)
- **G1 — cross-repo:** the `model.json` field + the `qkz-project-aware-2b` weights/Ollama modelfile live
  in the parallel `qukaizen-dac`/other session. Phase B depends on them; do not assume they exist.
- **G2 — "Built with Gemma" disclosure:** Gemma Terms + Prohibited Use Policy in `licenses/`, NOTICE +
  README + Modelfile attribution (parallel to the Llama exception) — blocks the default swap. Open item:
  pin the exact Gemma name-prefix rule from the live Gemma Terms.

## Build order (architect) — Phase A ships independent of the Gemma artifact
- **Phase A (READ+SUGGEST):** world_mount trio → gallery_view extension → banner → vendored fixture
  bundle with a `model.json` → tests T1–T6. Zero dependency on the Gemma weights or G2. **Off-ramp-safe.**
- **Phase B (default floor):** catalog row → G2 disclosure → setup.sh swap → only when G1+G2 green.

## Next
Owner to confirm: build **Phase A** now (proves the concept, ARAIL-only, fixture-tested), and coordinate
G1 (DaC `model.json` + Gemma weights) + G2 (disclosure) for Phase B with the parallel session.
