# Sprint: 2026-06-14-kb-capture

**Repo:** arail · **Branch:** qukaizen/arail-kb-capture (off main) · **Owner:** Charlie D · **Opened:** 2026-06-14

## Intent
Capture-to-knowledge: bring 🎤 (voice→text) and 📷 (image→OCR) into the **Knowledge Base ingest area**,
where users drop raw files. Output lands as markdown in `lab/pkb/inbox/` and flows through the **existing
compile pipeline** (inbox watcher → sources/ → wiki/compiled) — voice/image become first-class **raw
sources**, like a dropped PDF. Owner insight: capture belongs with knowledge ingest, not (only) chat.

## Owner decisions (final)
- **Gating: toolchain-present, NOT World-mount.** Available whenever ARAIL's STT/OCR adapter
  `is_available()` on this machine — a general ingest utility, decoupled from any mounted World. (The
  adapter is ARAIL's; Worlds still *declare* needs for the chat/agent surfaces.)
- **Scope:** voice AND image-OCR.
- **Chat composer 🎤/📷: kept unchanged** (World-gated, lands in `research/` as RAW notes). Additive sprint.

## What shipped (5 commits, build order 1–6)
- **Registry probes** (`available_capability(id)`, `installed_capabilities()`) + `GET /api/capabilities/installed`
  → `{"speech-to-text":bool,"equation-ocr":bool}` — World-decoupled toolchain availability.
- **`POST /api/kb/voice-ingest`** — STT-adapter-gated (409 with a speech-model hint, never "mount a
  World"); on-device transcribe; writes `lab/pkb/inbox/voice-memo-<ISO>.md` (front-matter `source:
  voice-memo`, captured-at, `kind: raw`); triggers inbox processing; temp audio deleted in `finally:`.
- **`POST /api/kb/scan-ingest`** — OCR-adapter-gated; PNG/JPEG allowlist + magic-byte + 12 MB cap;
  server-generated timestamped filename (path-jail); writes `inbox/scan-<ISO>.md`; triggers processing.
- **`knowledge.html`** toolbar: 🎤 Voice memo + 📷 Scan (`btn btn-sm btn-ghost`), enabled per the
  capability probe with TOOLCHAIN tooltips (not "mount a World"); MediaRecorder mirrors chat's
  `pickMime()` (Safari m4a; Chrome webm → caveat); existing `kb-reveal-toast` with [Open]/[Reveal].

## Phase ledger
| Phase | Artifact | Status |
|---|---|---|
| plan (architect) | ARCHITECTURE.md | DONE 2026-06-14 |
| build (builder) | BUILD_LOG.md | DONE 2026-06-14 — 6 steps, 18 tests |
| test (qa) | inline | 18 kb-capture tests + E2E (no-World ingest proven; chat unchanged; WC-B clean) |
| ship | — | ready to PR to main |

## Validation (orchestrator)
- `tests/test_kb_capture.py`: **18 passed.**
- **E2E with NO World mounted:** `GET /api/capabilities/installed` → `{speech-to-text:False (no model
  here), equation-ocr:True}` — proves the probe is toolchain-real, not World-declared. scan-ingest passes
  its gate (Vision present); voice-ingest 409s gracefully (model absent). **Chat `/api/stt/transcribe`
  still World-gated (400 no World) — unchanged.** WC-B Apple-symbol grep clean.
- Builder caught + fixed a registry docstring tripping the WC-B grep. Pre-existing flake:
  `test_stt_chat_ui::test_mic_enabled` (cross-file ordering, reproduced at branch-point — not ours).

## Notes / next
- **PR base:** main (independent of the open #86 switcher + #85-merged foundation).
- **ROADMAP:** a unified capture component shared by chat + KB; Chrome/webm voice (KB 🎤 Safari-only,
  same caveat as chat).
