# BUILD_LOG — Capture-to-Knowledge (voice/image ingest in the KB)

**Sprint:** 2026-06-14-kb-capture · **Repo:** arail (worktree ../arail-verify) ·
**Branch:** qukaizen/arail-kb-capture · **Builder persona**

Implements ARCHITECTURE.md's 6-step build order exactly. Purely additive — chat
🎤/📷, `/api/stt/transcribe`, `/api/ocr/extract`, and their `research/` landing
are UNCHANGED.

## Per-step status

### Step 1 — Registry helpers + `GET /api/capabilities/installed` ✅
- **Edited** `src/arail/capabilities/registry.py`:
  - `available_capability(id) -> Adapter|None` — returns the platform adapter iff
    `is_available()`, decoupled from any World; flaky probe degrades to None.
  - `installed_capabilities() -> {id: bool}` over `_INSTALLABLE_CAPABILITY_IDS`
    (`speech-to-text`, `equation-ocr`).
- **Edited** `src/arail/portal/app.py`: `GET /api/capabilities/installed` →
  `{"speech-to-text": bool, "equation-ocr": bool}`.
- Commit: `kb-capture step 1: registry available_capability + installed_capabilities helpers`
  (amended to reword a docstring — see DELTA 1).

### Step 2 — `POST /api/kb/voice-ingest` ✅
- **Edited** `app.py`. Toolchain-gated via `registry.available_capability("speech-to-text")`;
  absent → **409** `{ok:false, reason:"toolchain_unavailable", message:…}` with an
  actionable speech-model hint (NOT a "mount a World" message). Materializes audio
  via the existing `audio-capture` adapter, transcribes via the whisper adapter +
  `_runner`, writes `lab/pkb/inbox/voice-memo-<ISO>.md` (front-matter `source:
  voice-memo`, `captured-at`, title, confidence), triggers inbox processing,
  returns `{ok, path, reveal}`. Temp audio deleted in `finally:`.

### Step 3 — `POST /api/kb/scan-ingest` ✅
- **Edited** `app.py`. Toolchain-gated via `available_capability("equation-ocr")`;
  absent → 409 with an `xcode-select --install` hint (not World). Reuses the chat
  OCR validation (`_OCR_MIME_EXT` allowlist + `_sniff_image` magic-byte +
  `_OCR_MAX_BYTES` 12 MB). OCR via the Vision adapter + `_runner`, writes
  `inbox/scan-<ISO>.md` (front-matter `source: image-ocr`, `captured-at`,
  `original-filename`), triggers processing, returns `{ok, path, reveal}`. Temp
  image deleted in `finally:`. **Filename is server-generated/timestamped** — the
  client filename is recorded only as inert metadata (path components stripped) →
  path-jail.
- Shared helpers added in `app.py`: `_land_inbox_capture()` (writes the markdown
  raw source into `inbox/`, server-generated name) and `_trigger_inbox_processing()`
  (calls the same `pkb.ingest()` the ⚡ Process inbox button/watcher uses, then
  `wiki.schedule_rebuild()`; a processing failure does NOT lose the inbox file).
- Steps 1–3 endpoints landed in one commit (`kb-capture steps 1-3: …`) because
  they share `_land_inbox_capture`/`_trigger_inbox_processing`; splitting them
  would have produced non-compiling intermediate states. Registry helper (step 1)
  is its own commit.

### Step 4 — `knowledge.html` toolbar buttons + JS ✅
- **Edited** `src/arail/portal/templates/knowledge.html`:
  - **🎤 Voice memo** (`#kb-voice-btn`) + **📷 Scan** (`#kb-scan-btn`), both
    `btn btn-sm btn-ghost`, beside 📤 Upload / ⚡ Process inbox. Both start
    `disabled`. 📷 uses a hidden `<input type=file accept=image/png,image/jpeg>`.
  - 🎤 uses `MediaRecorder` mirroring chat's `pickMime()` (Safari `audio/mp4`;
    Chrome webm/opus rejected with the same caveat surfaced via the toast).
  - On load: `GET /api/capabilities/installed` enables each button iff its
    toolchain is present; else leaves it disabled with a **TOOLCHAIN** tooltip
    ("install the speech model `./arailctl setup`" / "`xcode-select --install`") —
    never a "mount a World" message.
  - On capture → POST the relevant KB endpoint → existing `kb-reveal-toast` via
    `renderRevealToast(...)` with `[Open]`/`[Reveal]` (`slot: 'inbox'`) to the
    inbox file.
- Commit: `kb-capture step 4: 🎤 Voice memo + 📷 Scan buttons in the KB toolbar`.

### Step 5 — `tests/test_kb_capture.py` ✅
- **18 tests**, arail weights (30 setup / 30 Buddy / 20 security / 10 happy /
  10 regression). Adapter boundary injected via fake `_runner`; the new endpoints
  resolve adapters through `registry.available_capability`, so the fakes patch
  that (not `registry.select`).
- Coverage: probe shape (both present / none present); voice + scan land inbox
  markdown with front-matter and trigger inbox processing; **NOT World-gated**
  (assert capture succeeds with `current_mount(...)` None but adapter available);
  adapter-absent → 409 with TOOLCHAIN (asserts `"world" not in message`);
  no-speech/no-text → `{ok:false}`; mime-spoof → 422; oversized → 422;
  server-generated filename path-jail (evil `../../../` filename can't escape
  inbox/); temp audio + temp image deleted on a raising runner; airgapped
  zero-egress; regression: chat `/api/stt/transcribe` + `/api/ocr/extract` still
  World-gated (400) and `_land_raw_voice_note`/`_land_raw_ocr_note` intact.
- Commit: `kb-capture step 5: tests for KB voice/image ingest`.

### Step 6 — BUILD_LOG ✅ (this file)

## TestClient walk (real, with auth + lab tree pointed at a tmp dir)

```
GET /api/capabilities/installed -> {'speech-to-text': True, 'equation-ocr': True}
voice-ingest -> 200 {'ok': True, 'path': 'inbox/voice-memo-2026-06-15T12-32-15Z.md',
                     'reveal': 'inbox/voice-memo-2026-06-15T12-32-15Z.md'}
scan-ingest  -> 200 {'ok': True, 'path': 'inbox/scan-2026-06-15T12-32-15Z.md',
                     'reveal': 'inbox/scan-2026-06-15T12-32-15Z.md'}
inbox files: ['scan-2026-06-15T12-32-15Z.md', 'voice-memo-2026-06-15T12-32-15Z.md']
--- voice md ---
---
title: Voice memo — 2026-06-15 12:32 UTC
kind: raw
source: voice-memo
captured-at: 2026-06-15T12:32:15Z
sourced: false
confidence: 0.90
---

battery delta v notes
```

Both ingest paths land a timestamped markdown raw source in `lab/pkb/inbox/` and
trigger the existing inbox processing — confirmed end-to-end with the injectable
runner (no real mic/whisper/Vision/swiftc touched). `swiftc`/whisper-model were
not exercised live (relied on the injectable-runner tests per the spec's fallback).

## Test counts + pre-existing-vs-introduced adjudication

- **`tests/test_kb_capture.py`: 18 passed.**
- Regression suites run together (`test_stt_flow`, `test_ocr_flow`,
  `test_stt_backend`, `test_ocr_backend`, `test_capabilities`, `test_stt_chat_ui`,
  `test_ocr_chat_ui`): all chat STT/OCR flow + backend tests pass.
- **Two failures observed in the mixed 7-file batch — adjudicated:**
  1. `test_capabilities::test_wc_b_no_apple_ocr_symbols_above_seam` — **was
     INTRODUCED by me, now FIXED.** My first registry.py docstring said "Apple
     Vision"; the WC-B grep (`Vision|VNRecognizeTextRequest|AppKit|swiftc|xcrun`)
     flags any such symbol above the `backends/macos/` seam. Reworded to "image-text
     backend"; the step-1 commit was amended. **Passes now.**
  2. `test_stt_chat_ui::test_mic_enabled_when_stt_available` — **PRE-EXISTING,
     NOT mine.** Reproduced on a pristine `git worktree` of the branch-point commit
     (HEAD~4, zero of my changes): the same 7-file batch fails identically
     (`1 failed, 67 passed`). It passes in isolation and when its own file runs
     alone — a cross-file test-ordering pollution that predates this sprint. Out of
     scope; left for QA / a separate fix.

## Deltas / ROADMAP

- **DELTA 1 (resolved):** registry docstring leaked an Apple OCR symbol above the
  WC-B seam → reworded + amended. Lesson: prose mentioning a platform symbol
  trips the seam grep, not just code.
- **DELTA 2 (noted, not mine):** pre-existing `test_stt_chat_ui` cross-file
  pollution — see adjudication above.
- ROADMAP (carried from ARCHITECTURE): a unified capture component shared by chat
  + KB; Chrome/webm voice support (KB 🎤 currently Safari-only, same caveat as chat).

## Files

- Edited: `src/arail/capabilities/registry.py`,
  `src/arail/portal/app.py`,
  `src/arail/portal/templates/knowledge.html`
- Added: `tests/test_kb_capture.py`, this BUILD_LOG.

## Commits (not pushed)

1. `kb-capture step 1: registry available_capability + installed_capabilities helpers` (amended)
2. `kb-capture steps 1-3: capability probe + KB voice/scan ingest endpoints`
3. `kb-capture step 4: 🎤 Voice memo + 📷 Scan buttons in the KB toolbar`
4. `kb-capture step 5: tests for KB voice/image ingest`
5. (this BUILD_LOG)
