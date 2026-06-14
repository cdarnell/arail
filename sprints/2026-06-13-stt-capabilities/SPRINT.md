# Sprint: 2026-06-13-stt-capabilities

**Repo:** arail
**Branch:** qukaizen/arail-stt-capabilities
**Owner:** Charlie D
**Opened:** 2026-06-13

## Intent

The SECOND half of the "DaC 2.0 × ARAIL: World-Driven Labs" program (PROGRAM.md win
conditions 2 & 3): a mounted World inherits **capabilities**, not just knowledge. A WorldBundle
DECLARES capability needs (`capabilities.json`); ARAIL owns a **capability registry** (declared id →
installed adapter) and provisions them. v1 ships the registry AND one real adapter — **STT
(Speech-to-Text)** — so the demo is: mount a World → tap the mic → speak → an **on-device** transcript
lands as a **RAW note** in the World's KB, zero cloud, zero domain-specific ARAIL code. Apple-first,
Linux-ready by construction.

## Scope decisions

- **ARAIL-repo ONLY** (a parallel session owns qukaizen-dac). `capabilities.json` is BUNDLE-OPTIONAL
  (graceful absence) and exercised via VENDORED fixtures under `tests/`. No qukaizen-dac edits.
- **Backend pivot (owner decision):** Apple Speech framework was blocked — an unsigned Swift CLI helper
  can't get the macOS speech-recognition TCC grant (needs a signed `.app`, rejected). Swapped to a
  local **Whisper** backend (`faster-whisper` + `base.en`): the browser captures the mic (browser
  permission), the backend transcribes the audio FILE — no app mic access, no Apple Speech, no TCC, no
  signing. The swap happened entirely BELOW the adapter seam (proving the seam was worth building) and
  took **Linux off the stub** (Whisper serves darwin + linux → advances WC-3).
- **OUT:** equation-ocr / vision / other modalities (declared-only, prove the registry), cloud STT,
  Chrome/webm-opus (ROADMAP — Safari/m4a first), real-time streaming transcription.

## Win conditions (falsifiable) — all MET

- **WC-A** — mount → mic → on-device transcript → RAW note (`kind:raw`/`sourced:false`,
  `lab/pkb/research/voice-notes/`), indexed; zero cloud, zero domain code. **Live proof:** real
  `say`→m4a→afconvert→whisper `base.en` transcription, 1 passed in 161s (one-time 138 MB model fetch),
  transcript accurate; subsequent inference local/airgapped.
- **WC-B** — no `.swift` files; no Apple framework symbols anywhere in `src/` (Whisper isn't Apple);
  OS-specifics stay below the adapter interface.
- **WC-C** — a second declared id `equation-ocr` resolves to `declared_unavailable` (no adapter) with
  ZERO code — proves the registry is real, not an N=1 wrapper.
- **WC-D** — a bundle with no `capabilities.json` mounts clean (graceful absence); MountRecord/seal
  untouched.

## Phase ledger

| Phase | Artifact | Status |
|---|---|---|
| think (visionary) | VISION.md | DONE 2026-06-13 — PROCEED, four falsifiable WCs |
| plan (architect) | ARCHITECTURE.md (+ Addendum A) | DONE 2026-06-13 — registry/seams + the Whisper backend, both spiked on-machine |
| build (builder) | BUILD_LOG.md | DONE 2026-06-13 — all 6 steps + Whisper swap (interrupted by API drop; finished + verified by orchestrator) |
| review (architect) | — | folded into QA gate |
| test (qa) | TEST_REPORT.md | DONE 2026-06-13 — WEAK_PASS → **PASS** after the B1 one-line fix |
| ship | — | ready (QA-clean; not pushed) |

## Ledger notes

- **Capability registry** (`src/arail/capabilities/`): Adapter ABC + seam sub-ABCs, platform-aware
  registry, `resolve_capabilities` whose default `adapter is None → declared_unavailable` branch makes
  WC-C cost zero code. Mount integration is ADDITIVE — resolved capabilities persist to a SIDECAR
  (`DATA_DIR/world-capabilities.json`), NOT the MountRecord (preserves the merged atomic-pointer/seal
  tests). `capabilities.json` is seal-EXEMPT (not in `_BUNDLE_FILES`).
- **Whisper STT** (`backends/whisper_stt.py`): behind the injectable `_runner`; `afconvert -f WAVE -d
  LEI16@16000 -c 1` (system, no ffmpeg) → `faster-whisper` `base.en`; lazy first-use model fetch to
  `lab/models/whisper/` with a log line; airgapped + absent → graceful `model_unavailable` (no network,
  no crash). One new dep `faster-whisper>=1.2.0` (prebuilt arm64 wheels, no compiler); no `setup.sh`
  change. Dead Apple/Swift path deleted; `macos/stt_backend.py` is a 22-line no-Apple alias.
- **STT flow:** mic button in Chat gated on the resolved `speech-to-text` capability →
  `POST /api/stt/transcribe` → RAW note via the existing `pkb_index` (`ensure_ready`/`schedule_upsert`)
  + `wiki.schedule_rebuild()`. Transcript is RAW DATA, never injected into a prompt (QA probe proves a
  hostile transcript lands inert and reaches no `_compose_prompt`). Audio + WAV temp files deleted in
  `finally:` (QA probe proves no leak even when the runner raises).
- **QA gate:** independently reproduced all four WCs. One BLOCKER B1 (false-green airgapped test —
  `_ensure_model` stat'd `model.bin` directly instead of the patchable `_model_present()`); production
  degrade was already correct; fixed in one line (`5e91a31`) + added QA probes. **Full suite: 17 failed
  / 2339 passed — the 17 are the exact pre-existing baseline; ZERO new failures, none in
  capabilities/stt/world.** WC-B Apple-symbol grep clean.
- **Commits** on `qukaizen/arail-stt-capabilities`: `d439219`→`8a68cde` (registry/seams/endpoint/UI/
  off-ramp), `eb28cdf`+`b765969` (Whisper swap + finishing pass), `2c409b6` (BUILD_LOG + artifacts),
  `5e91a31` (QA B1 fix + probes). **Not pushed.** Unrelated prior-sprint files left untouched.

## Notes / next

- **Demo (Safari):** `python -m arail.world_mount mount tests/fixtures/world-bundles/world-caps-stt`
  → `./arailctl start` → Chat → 🎤 (enabled when the capability resolves) → speak → RAW voice note in
  `lab/pkb/research/voice-notes/`. First tap fetches `base.en` once unless airgapped (fetch online once).
- **ROADMAP:** Chrome/webm-opus support (needs an opus decode step); a second real adapter
  (`equation-ocr` via Apple Vision / a local OCR) to exercise the registry with a 2nd live modality;
  the DaC side emitting real `capabilities.json` in bundles (the parallel qukaizen-dac session).
- **PR base:** like the world-mount PR, target `qukaizen/arail-kv-available-budget` (this branch forks
  its committed tip); retarget to `main` after that merges.
