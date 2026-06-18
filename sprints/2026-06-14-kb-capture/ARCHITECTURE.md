# ARCHITECTURE — Capture-to-Knowledge (voice/image ingest in the KB)

**Sprint:** 2026-06-14-kb-capture · **Repo:** arail (worktree ../arail-verify, branch qukaizen/arail-kb-capture off main)

## Goal (owner decisions, final)
Add 🎤 (voice→text) and 📷 (image→OCR) **to the Knowledge Base ingest area**. The output lands as a
markdown file in `lab/pkb/inbox/` and flows through the **existing compile pipeline** (inbox watcher →
sources/ → wiki/compiled) — voice/image become first-class **raw sources**, like a dropped PDF.
- **Gating:** available whenever the lab's **adapter toolchain is present** (decoupled from World mount) —
  a general ingest utility, NOT gated on a mounted World declaring the capability.
- **Scope:** voice **and** image-OCR together.
- **Chat composer 🎤/📷:** KEEP unchanged (World-gated, lands in `research/` as RAW notes). This sprint
  is additive — do not touch the chat capture or its endpoints.

## Reuse (do not reinvent)
- **Adapters:** `src/arail/capabilities/backends/whisper_stt.py` (STT) + `backends/macos/ocr_backend.py`
  (OCR), behind their injectable `_runner`. Same on-device, airgapped behavior.
- **Registry:** `src/arail/capabilities/registry.py` — `for_id(id)` / the resolution helper. To probe
  "is this adapter installed on this machine" WITHOUT a World: get the platform adapter for the id and
  call `is_available()`. Add a tiny helper `available_capability(id) -> Adapter|None` if not present
  (returns the platform adapter iff `is_available()`), and `installed_capabilities() -> {id: bool}`.
- **Inbox pipeline:** files land in `lab/pkb/inbox/`; `process_inbox`-style endpoint (app.py ~9053) +
  the multipart upload endpoint (~9361) + the background watcher already turn inbox files into sources.
  Reuse the inbox path resolution + trigger processing after writing.
- **Capture JS:** the chat mic's `getUserMedia`/`MediaRecorder` + `pickMime()` pattern (chat.html) and
  the OCR file-upload pattern (ocr) — mirror them for the KB buttons.

## Backend
1. **Availability probe** `GET /api/capabilities/installed` → `{"speech-to-text": bool, "equation-ocr": bool}`
   — resolves each adapter via the registry on this platform and reports `is_available()`. Decoupled from
   any mounted World. Used by the KB UI to enable/disable the affordances.
2. **Voice ingest** `POST /api/kb/voice-ingest` (multipart audio, mirrors `/api/stt/transcribe`'s
   validation): require the STT adapter `is_available()` (else 409 `unavailable`, actionable message —
   NOT World-gated); transcribe on-device via the whisper adapter + `_runner`; write the transcript to
   `lab/pkb/inbox/voice-memo-<ISO>.md` (front-matter: `source: voice-memo`, captured-at, a title); then
   trigger inbox processing (reuse the process-inbox call). Return `{ok, path, reveal}`. Temp audio
   deleted in `finally:`.
3. **Image ingest** `POST /api/kb/scan-ingest` (multipart image, mirrors `/api/ocr/extract`'s
   validation — PNG/JPEG allowlist + magic-byte + 12MB cap): require the OCR adapter `is_available()`
   (else 409); OCR via the Vision adapter + `_runner`; write to `lab/pkb/inbox/scan-<ISO>.md`
   (front-matter: `source: image-ocr`, captured-at, original filename); trigger inbox processing; return
   `{ok, path, reveal}`. Temp image deleted in `finally:`.
4. **Boundary:** transcript/OCR text is RAW user data → it's a normal raw source the compile pipeline
   already handles; no new injection surface (it never enters a prompt as instructions here — same as a
   dropped doc). On-device/airgapped/no-tokens. Path-jail: filenames are server-generated (timestamped),
   never from user input.

## Frontend (knowledge.html, the ingest toolbar — beside 📤 Upload / ⚡ Process inbox)
- Add two buttons: **🎤 Voice memo** (`id=kb-voice-btn`) and **📷 Scan** (`id=kb-scan-btn`) — `📷` uses a
  hidden `<input type="file" accept="image/png,image/jpeg" capture>`; voice uses `getUserMedia`/
  `MediaRecorder` (mirror chat's `pickMime()`; Safari m4a, Chrome webm rejected → reuse the caveat).
- On page load: `GET /api/capabilities/installed` → enable each button iff its adapter is available; when
  unavailable, disable with a tooltip ("Install the speech model / Xcode CLT to enable voice/scan
  ingest") — NOT a "mount a World" message (this is toolchain-gated).
- Voice: tap → record → tap → POST `/api/kb/voice-ingest` → on ok, show the existing `kb-reveal-toast`
  with a [Reveal] link to the inbox file; the inbox watcher/compile then picks it up.
- Scan: tap → file picker → POST `/api/kb/scan-ingest` → same toast.
- Keep it consistent with the existing toolbar button styling (`btn btn-sm btn-ghost`).

## Tests (arail weights 30 setup / 30 Buddy / 20 security / 10 happy / 10 regression) — `tests/test_kb_capture.py`
- availability probe shape; adapter-present → button enabled path; adapter-absent → 409 graceful (mock
  `is_available()`); voice-ingest with a fake `_runner` → markdown lands in `inbox/` with front-matter +
  inbox processing triggered; scan-ingest likewise; mime-spoof/oversized image → 422; temp files deleted
  on a raising runner; airgapped zero-egress; **NOT World-gated** (works with NO World mounted — assert a
  capture succeeds when `current_mount()` is None but the adapter is available). Regression: the chat
  `/api/stt/transcribe` + `/api/ocr/extract` + their research/ landing are UNCHANGED.

## Build order (atomic commit per step)
1. Registry helpers `available_capability` / `installed_capabilities` + `GET /api/capabilities/installed`.
2. `POST /api/kb/voice-ingest` (adapter-gated, inbox landing, trigger process).
3. `POST /api/kb/scan-ingest` (same).
4. knowledge.html toolbar buttons + JS (capability-probe enable/disable, capture, toast).
5. `tests/test_kb_capture.py`.
6. BUILD_LOG.

## Constraints
ARAIL-repo (this worktree) ONLY; additive — do NOT change the chat capture / its endpoints / the
capability-inheritance gating for chat. Reuse adapters/registry/inbox pipeline. On-device/airgapped.
ROADMAP: a unified capture component shared by chat + KB; Chrome/webm voice.
