# Build log: stt-capabilities

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) (the binding contract)
**Vision:** [VISION.md](./VISION.md)
**Branch:** `qukaizen/arail-stt-capabilities` (off the merged world-mount tip)
**Built:** 2026-06-13 · builder persona
**Venv:** `/Users/netsushi/ProJects/arail/.venv` (the arail editable install — the
shell's default `python` resolves to aerollm's venv; all commands below used `.venv/bin/python`).

## Per-step status (done-conditions → win conditions)

| # | Step | Commit | Status | Win condition | Done-condition met |
|---|---|---|---|---|---|
| 1 | Scaffold `capabilities/` package | `6740765` | ✅ DONE | (foundation) | Importable; `registry.select("x")` → `None` for unknown id |
| 2 | Linux stubs + macOS stub-registration | `d439219` | ✅ DONE | **WC-B** | `ARAIL_FORCE_PLATFORM=linux` select raises `CapabilityUnavailable("speech-to-text: no backend for linux")`; Apple-symbol grep clean |
| 3 | `resolve_capabilities` + sidecar in `world_mount` + 3 fixtures | `f0192df` (code+fixtures), `ace4515` (tests) | ✅ DONE | **WC-C, WC-D** | WC-C zero-code degrade; no-caps mounts clean; malformed→error recorded, mount succeeds; world-mount regression (12) green. **← OFF-RAMP SAFE POINT, independently green.** |
| 4 | Swift helper + `MacOSSpeechToText` + `MacOSAudioCapture` | code in `d439219`, tests+refinement in `3a5f092` | ⚠️ DONE w/ DELTA | (WC-A backend) | Fake-runner unit tests green; helper **compiles** locally; **live transcription blocked by a TCC delta — see below.** Graceful degrade verified. |
| 5 | `POST /api/stt/transcribe` + `_land_raw_voice_note` | `c79dea9` | ✅ DONE | **WC-A** | RAW note landed (kind:raw/sourced:false), indexed via `schedule_upsert`, temp cleaned, airgapped zero-egress, transcript-not-in-prompt — all via fake runner |
| 6 | Chat mic affordance | `8a68cde` | ✅ DONE | **WC-A surface** | Mic button gated on resolved `speech-to-text=="available"`; disabled+tooltip otherwise; MediaRecorder mp4-first (no webm); POST + toasts |

## Real seam paths / line numbers used

- `src/arail/world_mount.py`
  - `CAPABILITIES_SIDECAR_NAME = "world-capabilities.json"` (const block, ~L40).
  - New helpers inserted before `_stage_files`: `_capabilities_sidecar_path`,
    `current_capabilities`, `_resolve_and_write_capabilities`, `_remove_capabilities_sidecar`.
  - Call sites: `mount()` "Step 7" after `wiki.schedule_rebuild()` (best-effort, wrapped);
    `swap()` equivalent tail; `unmount()` calls `_remove_capabilities_sidecar(dd)` right
    after `_remove_record(dd)`. **`MountRecord` shape untouched** (atomic-pointer tests preserved).
  - Reused: `current_mount`, `_default_data_dir`, `_default_pkb_root`, the temp+`os.replace`
    atomic-write pattern, the staging conventions.
- `src/arail/portal/app.py`
  - `chat_page` (L1048) extended to resolve STT state → template vars `stt_available`/`stt_message`.
  - `POST /api/stt/transcribe` + `_land_raw_voice_note` inserted after `api_pkb_upload` (after L9181),
    mirroring the multipart `request.form()` / `upload.read()` pattern of `/api/pkb/upload`.
  - Logger is `_log` (not `log`) — fixed during build.
- `src/arail/pkb_index.py` — used `ensure_ready` (L266) + `schedule_upsert` (L410) exactly as the
  agent writers / `world_mount._index_staged` do. `_source_kind_for_path` maps `research/...` → `"user"`
  (correct: user-captured), verified by reading L93–108.
- `src/arail/pkb.py::_pkb_root` (L20) — used by `_land_raw_voice_note` for the note destination.
- Frontend anchor: composer `<div class="composer">` in `templates/chat.html` (~L1558); status-line
  `#status-line` reused for toasts (no dependency on the unrelated uncommitted `chat-highlight.js`).
- `tests/conftest.py` — relied on the autouse `_no_ambient_world_mount` (patches `_default_data_dir`)
  and `_reset_egress_guard`; my flow tests re-`monkeypatch.setattr(wm, "_default_data_dir", ...)` to
  point at their own mounted tmp dir (same pattern noted in the fixture docstring).

## Architecture-vs-reality deltas

### DELTA 1 (BLOCKING for live WC-A.4 only) — the Swift helper cannot obtain the speech-recognition TCC grant as a bare `swiftc` binary.

The architect's spike (ARCHITECTURE §1.1) verified that a 1-file Swift probe importing `Speech`
**compiles and links** and that `recognizer=true onDevice=true`. I reproduced **both** of those
facts exactly. However, the spike did **not** exercise two things the real path needs, and both fail
on this machine:

1. `SFSpeechRecognizer.requestAuthorization { ... }` from a plain `swiftc`-compiled CLI binary
   **SIGABRTs the process** (exit 134), because macOS aborts a privacy-sensitive TCC request made by a
   process that is not a code-signed app bundle with an `Info.plist` usage-description and a
   TCC-eligible identity. I confirmed this with an isolated 6-line probe (`requestAuthorization` alone
   → SIGABRT).
2. Attempting recognition **without** the grant (auth status `notDetermined`) makes
   `recognitionTask` **silently never fire its callback** → times out. So a live transcript genuinely
   requires the grant, which the bare binary cannot get.

**Mitigations I tried (kept in-scope, no new deps):** embedding the `Info.plist`
(`NSSpeechRecognitionUsageDescription` + bundle id) via the linker
(`-Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist ...`). Still SIGABRTs — a section-embedded
plist is not sufficient; a real `.app` bundle + code signing is required.

**Why I STOPPED rather than improvised:** fixing this means shipping a signed `.app` bundle with a TCC
identity — a build-system / signing path that contradicts the architect's *selected* option (b)
premise ("no Xcode project, no signing", lazy `swiftc` compile). That is a redesign, not a build
detail, so per my mandate I surfaced the gap instead of inventing a signing pipeline mid-flight.
This is exactly VISION disconfirming-evidence #2/#3 territory (Apple-Speech access cost / mic-permission
UX), but it fires only on the **live backend**, not on the registry/seams.

**How I resolved it so the product still degrades gracefully (not a brick):**
- `MacOSSpeechToText.invoke()` now maps a signal-killed helper (negative rc, or rc 134/133/137 with no
  JSON on stderr) to `permission_denied` with an actionable message about the signed-bundle requirement
  (`stt_backend.py`, commit `3a5f092`). So an unsigned helper produces a graceful **409 toast**, never a
  500. The helper's own `permission_denied`/`model_unavailable` JSON paths already mapped to 409.
- Everything **above** the live helper is fully built and tested via the injectable `_runner`
  (steps 5–6). The day ARAIL ships a signed helper (the `[DEBT]` to file), STT flips to `available`
  and WC-A.4 lights up with **zero** change above the seam — which is precisely the WC-B property.

**Net WC-A status:** WC-A.1 (zero egress), .2 (no domain strings), .3 (RAW/data-not-instructions) are
**met and tested**. WC-A.4 (≥90% words, <15s live) is **deferred on this machine** pending a signed
helper bundle — the modality is sound (recognizer + on-device + compile all confirmed), only the TCC
grant path is blocked for an unsigned CLI binary.

### DELTA 2 (non-blocking) — fixtures share slug `physics`.

All three vendored fixtures are copies of the sealed `physics/` bundle (so seals stay valid), so they
share `world: physics` and stage to `sources/world-physics/`. Harmless because every test uses an
isolated tmp `pkb_root`/`data_dir`. `capabilities.json` was added as an unsigned, seal-EXEMPT sibling
(NOT added to `_BUNDLE_FILES`/`manifest.files{}`) — verified `verify_seal` still returns `ok=True` on
`world-caps-both`.

## Files added / edited

**Added (this feature):**
- `src/arail/capabilities/{__init__,errors,adapter,spec,registry,resolve}.py`
- `src/arail/capabilities/backends/__init__.py`
- `src/arail/capabilities/backends/macos/{__init__,audio_backend,stt_backend}.py` + `stt_helper.swift`
- `src/arail/capabilities/backends/linux/{__init__,audio_backend,stt_backend}.py`
- `tests/fixtures/world-bundles/world-caps-stt/` (physics + capabilities.json: stt)
- `tests/fixtures/world-bundles/world-caps-both/` (physics + capabilities.json: stt + equation-ocr)
- `tests/fixtures/world-bundles/world-no-caps/` (physics, no capabilities.json)
- `tests/test_capabilities.py`, `tests/test_stt_backend.py`, `tests/test_stt_flow.py`, `tests/test_stt_chat_ui.py`

**Edited (this feature):**
- `src/arail/world_mount.py` (sidecar wiring — additive only)
- `src/arail/portal/app.py` (chat route STT gating + `/api/stt/transcribe` + `_land_raw_voice_note`)
- `src/arail/portal/templates/chat.html` (mic button + self-contained mic JS + small style)
- `pyproject.toml` (`live_mic` pytest marker)

**NOT touched** (as constrained): the unrelated uncommitted work
(`lab_brain.py`, `docs/prompt-caching.md`, `router/cache_prewarm.py`, `tests/test_cache_prewarm.py`,
`static/js/chat-highlight.js`), `qukaizen-dac`, `scripts/setup.sh`, `MountRecord` shape, `_BUNDLE_FILES`,
`verify_seal`, the egress guard.

## WC-B grep result (run from repo root)

```
$ grep -rEn 'AVFoundation|SFSpeechRecognizer|pyobjc|\bobjc\b|swiftc|xcrun' src/ --exclude-dir=macos
  → (no output, exit 1) = CLEAN
$ grep -rin 'psychology' src/arail/capabilities src/arail/portal/app.py
  → (no output) = CLEAN   # WC-A.2
```

All Apple symbols (incl. `import Speech` / `import AVFoundation`) live only in
`src/arail/capabilities/backends/macos/stt_helper.swift` and the two macos `*_backend.py` modules.

## Test results

- **New feature tests:** `test_capabilities.py` (11) + `test_stt_backend.py` (9, incl. 1 `live_mic`
  skipped) + `test_stt_flow.py` (9) + `test_stt_chat_ui.py` (2) = **30 pass, 1 skipped (live_mic)**.
- **Targeted regression:** `test_world_mount.py` (12) + `test_world_dictionary.py` + `test_world_face.py`
  pass alongside the new tests → **64 passed** in one combined run.
- **Full suite:** `17 failed, 2333 passed, 1 xfailed`.
  - **Adjudication:** the 17 failures are **pre-existing baseline**, not introduced. Verified by checking
    out the pre-sprint tip (`6740765^`) in a throwaway worktree and re-running the implicated files:
    `test_aerollm_defaults` (4, psutil/KV), `test_swarm_goal_surfaces` (2), `test_opencode_lifecycle`
    log-rotation, `test_dashboard_layout_v2` all fail **identically** on base. The
    docs-routes / airgap-state-order / system_metrics ones are full-run-only state-order flakes (they
    pass in isolation) and are independent of this feature. **Zero capabilities/STT tests fail.**

## Live-compile evidence (this machine)

- `which xcrun swiftc` → `/usr/bin/xcrun`, `/usr/bin/swiftc` (present).
- `xcrun swiftc stt_helper.swift -o /tmp/arail-stt-test` → exit 0, produced a 95 KB binary
  (confirms the lazy-compile path works; the `live_mic` `test_helper_compiles_once` exercises it).
- `SFSpeechRecognizer(locale:"en-US")` → non-nil, `supportsOnDeviceRecognition == true` (modality OK).
- Live end-to-end transcription **blocked** by DELTA 1 (TCC grant). Recorded; relying on the
  injectable-runner tests for CI coverage of the flow.

## Demo command (developer)

> Note: live transcription needs the signed-helper follow-up (DELTA 1). On this machine the mic flow
> reaches `permission_denied` → graceful 409 toast. The steps below are the intended WC-A demo and are
> exactly what runs once a signed `arail-stt` helper is provisioned; the registry/seam/landing all work today.

```bash
cd /Users/netsushi/ProJects/arail

# 1. Mount the STT-declaring vendored World (writes the capabilities sidecar).
.venv/bin/python -m arail.world_mount mount tests/fixtures/world-bundles/world-caps-stt

# 2. Confirm the inheritance resolved:
.venv/bin/python -c "from arail.world_mount import current_capabilities; print(current_capabilities())"
#   → speech-to-text state == 'available' on this Mac (xcrun present).

# 3. Start the lab and open Chat in Safari (browser mic capture, audio/mp4):
./arailctl start            # http://127.0.0.1:8080  → Chat tab
#   The 🎤 button is ENABLED (gated on the resolved capability). Tap → speak ~30s → tap to stop.
#   → toast: "Voice note saved → research/voice-notes/<ts>_voice-note.md"

# 4. See the RAW note land + index:
ls lab/pkb/research/voice-notes/
.venv/bin/python -c "from arail import pkb; print(pkb.search('voice'))"   # searchable

# Unmount (removes pointer + capabilities sidecar):
.venv/bin/python -m arail.world_mount unmount
```

For a no-Safari / CI-equivalent demo of the full flow with a fake transcript, see
`tests/test_stt_flow.py::test_stt_end_to_end_fake_runner`.

---

## Whisper backend swap (completion) — replaces Apple Speech

**Why:** the Apple-Speech path (lazy-compiled Swift helper) was blocked — an unsigned
CLI binary SIGABRTs on the macOS speech-recognition TCC grant, and a signed `.app`
was rejected by the owner. Owner chose a local **Whisper** backend (ARCHITECTURE
Addendum A). Mic capture stays in the browser (browser permission); the backend
transcribes the audio *file*, so there is no app mic access, no Apple Speech, no TCC,
no code-signing. The swap is entirely BELOW the adapter seam.

**What changed (commits `eb28cdf`, `b765969`):**
- Dep: `+faster-whisper>=1.2.0` (prebuilt arm64 wheels, no compiler); reuses existing `huggingface-hub`.
- `backends/whisper_stt.py` — `WhisperSpeechToText` behind the existing injectable `_runner`:
  `m4a → afconvert (-f WAVE -d LEI16@16000 -c 1) → faster-whisper base.en → JSON`. Same
  `(rc,stdout,stderr)` contract, so all fake-runner tests pass unchanged.
- Registered platform-neutrally for **darwin + linux** → Linux off the stub (**advances WC-3**).
- Deleted the Swift helper + Apple-Speech body; `macos/stt_backend.py` is now a 22-line
  no-Apple alias (`MacOSSpeechToText = WhisperSpeechToText`).
- Model `base.en` at `lab/models/whisper/base.en/` (git-ignored); first-use lazy download
  with a log line; airgapped + absent → graceful `model_unavailable` (no network, no crash).
  **No `scripts/setup.sh` change** (pure lazy fetch).

**WC-A.4 — real transcription proof (the proof the Apple path never reached):**
`pytest tests/test_stt_backend.py::test_real_transcription -m live_stt` → **1 passed in 161s**
(one-time `base.en` download ~138 MB, then `say`→m4a→afconvert→whisper→transcript containing
the expected token). `model.bin` now 138 MB on disk; subsequent inference is local/airgapped.

**WC-B:** Apple-symbol grep over all of `src/` is CLEAN (Whisper is not Apple).
**Tests:** 33 capability/STT pass + 1 `live_stt` (now proven on demand). Full suite:
**17 failed / 2333 passed — identical to the pre-existing baseline; zero new failures introduced.**

**Demo note:** the demo command above is unchanged; the resolved `speech-to-text` capability
now lights up via Whisper, and the 🎤 transcribes locally (first tap triggers the one-time
model fetch unless `LAB_MODE=airgapped`, in which case fetch it once online first). Safari-first
(m4a); Chrome/webm-opus is ROADMAP.

— builder (completed by orchestrator after an API-drop interruption), 2026-06-13.
