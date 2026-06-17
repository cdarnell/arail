# DaC → ARAIL handoff: emit the World-driven siblings in the canonical export

**For the `qukaizen-dac` session.** ARAIL now consumes three World-driven signals from a mounted
WorldBundle — **capabilities**, **model recommendation**, and **palette** — but today only ARAIL's
*vendored test fixtures* carry them. For the *canonical* DaC export (what real users mount) to light up
the same behavior, `qukaizen-dac` must emit these in its bundle. This doc is the exact contract; it
requires NO ARAIL change (ARAIL already reads them).

## Current gap (verified 2026-06-17, read-only)
- `qukaizen-dac/data/worlds/` has **no `physics`** World (only horticulture, ml-engineering, …).
- No `dist/bundles/physics/` and **no `export-bundle` script** emitting the siblings.
- So: the physics World must be **authored + committed** in `qukaizen-dac`, and its exporter must emit
  the seal-exempt siblings below.

## The WorldBundle contract (what a bundle dir must contain)
**7 SEALED files** (already the DaC convention — listed in `manifest.files{}`, hashed into
`world_sha256`): `manifest.json`, `terms.json`, `spec.json`, `roster.json`, `drift-report.json`,
`agenda.json`, `face.json`.

**+ 2 SEAL-EXEMPT siblings (NEW — emit these):** `capabilities.json`, `model.json`.
- **Seal-exempt = MUST NOT be added to `manifest.files{}` or `world_sha256`.** Verified against the
  canonical physics seal `b91d525a…`: `files{}` = the 6 non-manifest sealed files only. ARAIL reads the
  siblings as optional, mount-non-blocking; a missing sibling just means "no capabilities / no model hint"
  (graceful), and adding them must NOT change the seal (so existing seals stay valid).

**+ `face.json` palette:** set `"palette_hint": "slate-violet"` for physics (the canonical palette; ARAIL's
fixtures already use it, so the real export should match — today the upstream face may still say
`blue-cyan-lab`). `palette_hint` only selects one of ARAIL's preset ids
(`blue-cyan-lab | emerald-terminal | night-amber | slate-violet`); unknown → default, graceful.

## The two drop-in siblings (self-contained, in this dir)
- **`dac-physics-capabilities.json`** → place as `<bundle>/capabilities.json`. Declares `speech-to-text`
  + `equation-ocr` (`dac.world-capabilities/v1`). ARAIL provisions the adapter if installed (else degrades).
- **`dac-physics-model.json`** → place as `<bundle>/model.json` (`dac.world-model/v1`). Recommends the
  ~2B Gemma generalist `qkz-project-aware-2b` with a fallback chain; ARAIL surfaces a one-tap suggestion
  in the model picker on mount.

## `export-bundle` change (DaC side)
When exporting a World, copy `capabilities.json` and `model.json` (if present in `data/worlds/<slug>/`)
into the output bundle dir **as-is, seal-exempt** — i.e. AFTER computing `world_sha256` over `terms.json`
and the `files{}` map; do NOT include them in either. (Same handling as a README would get — they ride
alongside, unsealed.) If absent for a World, emit nothing (optional by design).

## Consumer contract — which ARAIL reader each file feeds
| Bundle file | ARAIL reader | Effect on mount |
|---|---|---|
| `terms.json` (sealed) | `mounted_terms` / dictionary | sourced, cited dictionary |
| `face.json` (sealed) — name/tagline/domain_framing | `effective_identity()` | brand + theme + Buddy/Researcher framing flip |
| `face.json` `palette_hint` | `ui_theme` + recolor middleware | every page repaints to the World palette |
| `capabilities.json` (seal-exempt) | `current_capabilities` + the chat mic/📷 gating | declares STT/OCR; ARAIL lights them up if the adapter is installed |
| `model.json` (seal-exempt) | `current_model_hint` + the model picker | one-tap "this World recommends <model>" suggestion |

## Verification (end-to-end, once DaC ships the export)
Mount the real DaC export in ARAIL and confirm the consumer contract lights up:
```
./arailctl world verify  <dac>/dist/bundles/physics      # seal OK (siblings don't affect it)
./arailctl world mount    <dac>/dist/bundles/physics
```
- dictionary serves the sourced physics terms; the lab recolors slate-violet; the nav shows ◆ Physics World;
- `GET /api/worlds` lists it; the model picker shows the `qkz-project-aware-2b` suggestion;
- if a World declares `equation-ocr`/`speech-to-text`, the chat mic/📷 gate on the resolved capability.
A bundle WITHOUT the siblings still mounts fine (knowledge + theme only) — the siblings are additive.

## Scope note
This is the DaC-side spec ONLY — no ARAIL change is needed (the readers shipped in #78/#87/#89). The
Gemma model artifact itself (`qkz-project-aware-2b` weights/Ollama base) + the "Built with Gemma"
disclosure are the separate G1/G2 items (see `../2026-06-14-world-model-hint/handoff/`).
