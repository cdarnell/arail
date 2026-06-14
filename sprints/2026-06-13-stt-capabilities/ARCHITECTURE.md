# ARCHITECTURE — Capability registry + on-device speech-to-text (STT)

**Sprint:** `2026-06-13-stt-capabilities` · **Repo:** `arail` (ARAIL-only) · **Mode:** architect / DESIGN
**Builds on:** the merged world-mount feature (`src/arail/world_mount.py`, PR #77).
**Status legend:** **[BUILT]** = ships this sprint · **[ROADMAP]** = registered/stubbed, not implemented (Standing Rule 1).

This is the build contract. The builder implements it with **zero new decisions**. Where reality
contradicted the brief I designed against reality and recorded it under **Contradictions** (§0).

---

## 0. Contradictions with the brief / VISION (recorded, designed-against)

1. **The world-mount cross-reference path is wrong.** VISION and this prompt cite
   `/Users/netsushi/ProJects/arail/sprints/2026-06-13-integrate-dac-into-arail/ARCHITECTURE.md`
   and `/Users/netsushi/ProJects/sprints/2026-06-13-integrate-dac-into-arail/...`. **Neither
   exists.** The merged code itself (`src/arail/world_mount.py`) and its tests
   (`tests/test_world_mount.py`, fixtures under `tests/fixtures/world-bundles/{physics,tampered,hostile}`)
   are real and are the authoritative source of conventions. I designed against the code, not the
   missing doc. No action needed from the builder; just don't go looking for that file.

2. **`capabilities.json` is seal-EXEMPT, by construction of the merged code.** `world_mount.py`
   verifies sha256 over a *fixed frozenset* `_BUNDLE_FILES` (agenda, drift-report, face, roster,
   spec, terms) and `manifest.files{}`. A new sibling `capabilities.json` is **not** in that set and
   **not** in `manifest.files{}`, so it is neither sealed nor required. That is exactly what makes it
   bundle-OPTIONAL (WC-D) for free — but it also means **capabilities.json is unsigned**. We accept
   this for v1 because it carries *declared needs only*, never truth/instructions (it cannot inject a
   prompt; it only selects which ARAIL-owned adapters light up). The integrity caveat is recorded in
   §7 (Security). Do **not** add capabilities.json to `_BUNDLE_FILES` or `manifest.files{}` — that
   would break the seal of every existing fixture and require re-sealing, and DaC owns sealing, not us.

3. **VISION §WC-A says the note lands in `lab/pkb/research/` OR inbox; the prompt says verify
   against real sections.** Verified: `pkb.scaffold()` creates a top-level `research/` dir and
   `pkb.browse()` lists `research` first in the sidebar tree; `world_mount` stages bundle files under
   `pkb/sources/world-<slug>/`. The autoresearch/agent writers use `agents/<kind>/`. **Decision: RAW
   STT notes land in `lab/pkb/research/voice-notes/` (NOT inbox, NOT sources/world-*).** Rationale in
   §4. `inbox/` is a *staging* area that `ingest()` empties into `sources/`; a finished transcript is
   not raw intake to be re-sorted, it is a user-authored research note. `sources/world-<slug>/` is
   reserved for sealed bundle artifacts and must not be polluted with user data.

4. **`equation-ocr` example uses Apple Vision, not OCR-of-equations-as-a-thing.** WC-C only needs a
   *second declared id with no adapter*. We register **no** `equation-ocr` adapter (that's the whole
   point), so there is nothing Apple-specific to contradict. Fine as-is.

---

## 1. THE HARD GATE — RESOLVED (spike run on this machine, 2026-06-13)

VISION flagged this as blocking and demanded a real spike. I ran one. **Verdict: GO for the macOS STT
backend.** Evidence below is reproducible.

### 1.1 Python → on-device Apple Speech: **decision = a tiny bundled Swift helper binary (option b).**

| Option | Spike result | Verdict |
|---|---|---|
| (a) pyobjc + `pyobjc-framework-Speech` | `import Speech` / `import objc` / `import AVFoundation` all **fail** — pyobjc is **not installed** and is **not** an ARAIL dependency. Adding it pulls ~12 wheels (`pyobjc-core` + per-framework shims) onto every clean machine for one capability. Async `SFSpeechRecognizer` callbacks driven from Python need a CFRunLoop pump — fiddly from a uvicorn worker thread. | **Rejected for v1.** Heavy dep + runloop friction; disconfirming-evidence #2 risk. |
| **(b) bundled Swift helper binary** | `swiftc`, `swift`, `xcrun` all present (`/usr/bin/...`, full Xcode at `MacOSX26.5.sdk`). `Speech.framework` + `AVFoundation.framework` present in SDK. A 1-file Swift probe importing `Speech` **compiles and links with the stock toolchain** (`swiftc spike.swift -o spike`, no Xcode project, no signing). Running it printed `recognizer=true onDevice=true`. | **SELECTED.** No new Python deps; OS-native; on-device confirmed. |
| (c) already-present option | None. No STT anywhere in the repo. | n/a |

**On-device, zero-network confirmed:** the probe reported `supportsOnDeviceRecognition == true` on
macOS 26.5 / Apple Silicon. The helper sets `request.requiresOnDeviceRecognition = true`, so the
recognizer **never** contacts Apple servers — works under `LAB_MODE=airgapped`. (Belt-and-suspenders:
the helper is a separate process; ARAIL's `egress.py` guard does not even need to cover it, but we
assert zero egress in test — see §6.)

**The helper contract** (`[BUILT]`, lives at `src/arail/capabilities/backends/macos/stt_helper.swift`,
compiled to `lab/bin/arail-stt` at setup/first-use):

```
arail-stt --audio <path> --locale en-US [--timeout 120]
  → stdout: a single JSON object, exit 0:
      {"ok": true, "transcript": "...", "segments": [{"text":"...","ts":0.0}], "confidence": 0.0-1.0, "on_device": true}
  → on failure, exit non-zero, stderr: JSON {"ok": false, "error": "<code>", "message": "<actionable>"}
     error codes: "permission_denied" | "no_speech" | "model_unavailable" | "decode_failed" | "timeout" | "unsupported_audio"
```

The helper:
- Reads the audio file via `AVAudioFile`/`SFSpeechURLRecognitionRequest` (file-in, not live mic).
- Sets `requiresOnDeviceRecognition = true`; if `recognizer.supportsOnDeviceRecognition == false`
  or `recognizer == nil`, exits with `model_unavailable` (do NOT silently fall back to network).
- Requests `SFSpeechRecognizer.requestAuthorization`; if denied/restricted, exits `permission_denied`.
  (NOTE: this is the *speech-recognition* TCC class, distinct from *microphone* — see §1.2; because we
  capture in the browser, ARAIL's process only ever needs the speech-recognition grant, requested by
  the helper, which prints an actionable message the portal surfaces.)
- Empty/garbage → exits `no_speech` (we treat a 0-word result as a graceful "nothing heard").

**Build/setup impact (`[BUILT]`, 30%-weighted QA concern):** compiled **lazily on first use** by
`backends/macos/stt_backend.py::_ensure_helper()` — it shells `xcrun swiftc <helper>.swift -o lab/bin/arail-stt`
once, caches the binary, and re-uses it. No build step is added to `scripts/setup.sh` (keeps clean-machine
setup unchanged; the cost is paid the first time the user taps the mic, behind the activity log). If
`xcrun`/`swiftc` is absent (Xcode CLT not installed), `_ensure_helper()` raises `CapabilityUnavailable`
with message: *"Speech-to-text needs Apple's command-line tools. Run: `xcode-select --install`, then try
again."* — actionable, no hang. This is the only new host requirement and it is Apple-CLT, already
present on any machine that compiled aerollm.

### 1.2 Microphone capture: **decision = BROWSER capture (`getUserMedia` + `MediaRecorder`), POST the blob.**

This is the pivotal call and it is the one that makes WC-A work on a clean machine.

- **Browser capture** uses the *browser's* mic permission (Safari/Chrome prompt the user the normal
  way for `http://127.0.0.1:8080`). ARAIL's uvicorn process **never** needs a macOS TCC *microphone*
  entitlement — which it cannot cleanly obtain as a headless server process (disconfirming #3). The
  page records, stops, and POSTs an audio blob the backend transcribes on-device. **Selected.**
- **Native AVFoundation/CoreAudio capture** in the helper would require ARAIL's process context to
  hold a mic TCC grant; from a server launched by `./arailctl start` this is the "silent hang / can't
  trigger the prompt" failure VISION pre-committed to killing on. **Rejected.**

**Audio format across the seam (pinned, no conversion, no ffmpeg):**
- The portal records with `MediaRecorder` and POSTs **whatever the browser produces**. On Safari/macOS
  that is **`audio/mp4` (AAC in an m4a container)**; on Chrome it is `audio/webm;codecs=opus`.
- **Apple's `AVAudioFile`/`SFSpeechURLRecognitionRequest` decodes m4a/AAC natively** — so for the
  primary target (Safari on the user's Mac) **no transcoding is needed at all.** The spike confirmed
  `afconvert` (system binary, always present) handles m4a/aac/wav/flac but **NOT webm/opus**.
- **Rule for the frontend (`[BUILT]`):** request `audio/mp4` first
  (`MediaRecorder.isTypeSupported('audio/mp4')`), fall back to `audio/aac`, then `audio/wav`. **Do not
  emit webm.** If the only supported type is webm (non-Safari browsers), the backend returns a clear
  `unsupported_audio` error telling the user to use Safari for voice notes in v1. **No ffmpeg
  dependency is added** (heavy, not on the box). Chrome/webm support is **[ROADMAP]**.
- The audio MIME the client used is sent as a form field `mime`; the backend writes the blob to a temp
  file with the right extension (`.m4a`/`.wav`) so AVFoundation sniffs it correctly.

### 1.3 Off-ramp wiring (pre-committed, per VISION disconfirming #1/#2/#3 and #4)

The spike passed, so we build STT. But the build order (§8) puts the **registry + seams + graceful
absence FIRST** so that *if the live-mic / quality bar fails during the build*, WC-B/C/D still land and
only the STT backend defers. And per disconfirming #4: the registry is designed to make WC-C **cost
near-zero** (a second declared id with no adapter is the *default* resolution path, not a special case)
— so we keep the registry. If the builder finds WC-C is NOT cheap (it will be), the fallback is "drop
the registry, ship STT as a direct adapter behind the two seam interfaces" — but that contingency
should not fire given this design.

---

## 2. Capability registry (`src/arail/capabilities/` — NEW) `[BUILT]`

### 2.1 Package layout

```
src/arail/capabilities/
  __init__.py            # re-exports: Adapter, CapabilitySpec, Resolution, ResolvedCapability,
                         #             registry, resolve_capabilities, CapabilityUnavailable, CapabilityError
  errors.py              # CapabilityError, CapabilityUnavailable, CapabilityNotImplemented
  spec.py                # CapabilitySpec dataclass + parse_capabilities_file() (reads capabilities.json)
  adapter.py             # Adapter ABC + AudioCaptureAdapter / SpeechToTextAdapter sub-ABCs
  registry.py            # the id→adapter map; register(); resolve(); platform selection
  backends/
    __init__.py
    macos/
      __init__.py
      audio_backend.py   # MacOSAudioCapture (browser-capture passthrough; see §3)
      stt_backend.py     # MacOSSpeechToText (shells the Swift helper)
      stt_helper.swift   # the helper source (compiled lazily to lab/bin/arail-stt)
    linux/
      __init__.py
      audio_backend.py   # LinuxAudioCapture — registered, raises CapabilityNotImplemented
      stt_backend.py     # LinuxSpeechToText — registered, raises CapabilityNotImplemented
```

**Hard rule (WC-B):** the strings `AVFoundation`, `Speech`, `SFSpeechRecognizer`, `pyobjc`, `objc`,
`swiftc`, `xcrun` may appear **only** under `capabilities/backends/macos/`. Nowhere else in the repo.
The QA grep in §6 enforces this.

### 2.2 The Adapter ABC (`adapter.py`)

```python
class Adapter(ABC):
    id: str          # the capability id this adapter provides, e.g. "speech-to-text"
    platform: str    # "darwin" | "linux"  (matches platform.system().lower())
    purpose: str     # human string for the UI

    @abstractmethod
    def is_available(self) -> bool:
        """Cheap probe. True iff invoke() can plausibly succeed on this host RIGHT NOW.
        macOS STT: returns (platform=='darwin') and xcrun/swiftc present.
        Linux stub: returns False (never available)."""

    @abstractmethod
    def invoke(self, **kwargs) -> Any: ...
```

Two typed sub-ABCs pin the interface contracts (inputs/outputs) for the two seams:

```python
class AudioCaptureAdapter(Adapter):
    id = "audio-capture"
    # invoke(audio_bytes: bytes, mime: str) -> AudioArtifact
    #   AudioArtifact = {path: Path (temp file on disk), mime: str, duration_s: float|None}

class SpeechToTextAdapter(Adapter):
    id = "speech-to-text"
    # invoke(audio: AudioArtifact, locale: str = "en-US") -> Transcript
    #   Transcript = {text: str, segments: list[{text,ts}], confidence: float, on_device: bool}
```

### 2.3 The registry (`registry.py`)

A module-level singleton `registry` with:

```python
def register(adapter: Adapter) -> None        # called at import time by each backend module
def adapters_for(capability_id: str) -> list[Adapter]   # all registered, any platform
def select(capability_id: str) -> Adapter | None
    # platform-aware: prefer an adapter whose .platform == platform.system().lower()
    #   AND .is_available(); else return the platform-matched-but-unavailable adapter (so the
    #   caller gets a CapabilityNotImplemented with the RIGHT message); else None (no adapter at all).
```

**Registration happens at import** of `arail.capabilities` (its `__init__` imports both backend
packages, each of which calls `registry.register(...)` at module scope). The macOS backends register
unconditionally; their *availability* (not registration) is platform-gated via `is_available()`. The
Linux backends also register unconditionally and are **selected only when `platform.system()=='Linux'`**,
or when a test force-selects them.

**WC-B test hook:** `select()` honors an override `ARAIL_FORCE_PLATFORM` env (e.g. `=linux`) so a test
on macOS can force-select the Linux STT backend and assert it raises
`CapabilityUnavailable("speech-to-text: no backend for linux")`. (The Linux stub's `invoke()` raises
`CapabilityNotImplemented`, a subclass of `CapabilityUnavailable`, with that exact message.)

### 2.4 Resolution at mount — the three states (WC-C is the default path)

```python
@dataclass
class ResolvedCapability:
    id: str
    purpose: str
    desired: bool                 # from capabilities.json (desired vs optional)
    state: str                    # "available" | "declared_unavailable" | "unknown"
    adapter_platform: str | None  # which backend, if any
    message: str                  # operator-facing line

def resolve_capabilities(specs: list[CapabilitySpec]) -> list[ResolvedCapability]:
    for each spec.id:
      adapter = registry.select(spec.id)
      if adapter is None:                      -> state="declared_unavailable"   # WC-C path, ZERO code
            (no adapter registered for this id at all, e.g. equation-ocr)
      elif adapter.is_available():             -> state="available"
      else:                                    -> state="declared_unavailable"   # registered, wrong platform / CLT missing
```

There is **no `"unknown"` produced by an unrecognized id** in v1 — an id we have never heard of is
indistinguishable from one whose adapter isn't installed, and both should "degrade gracefully." The
`"unknown"` enum value is reserved for a future allowlist of *known capability ids*; for v1
`resolve_capabilities` never emits it. **This is what makes WC-C cost zero:** declaring `equation-ocr`
(no adapter) flows down the identical `adapter is None → declared_unavailable` branch as any future
unimplemented capability. Adding a second declared id requires **no code change** — proven by the
fixture in §6, not by a new branch.

---

## 3. The two seams `[BUILT macOS + ROADMAP linux]`

### Seam A — audio/mic capture
- **Interface:** `AudioCaptureAdapter.invoke(audio_bytes, mime) -> AudioArtifact`.
- **macOS impl (`MacOSAudioCapture`):** capture happens in the **browser** (§1.2), so this adapter's
  job is *validation + materialization*, not device access: it writes `audio_bytes` to a temp file
  under `lab/data/cache/stt/<uuid>.<ext>` (ext from `mime`), rejects mime types AVFoundation can't
  decode (`unsupported_audio` for webm/opus), and returns the `AudioArtifact`. `is_available()` →
  `platform=='darwin'`. This keeps a real seam even though there is no native CoreAudio call today —
  a future native-capture macOS impl slots in here without changing callers.
- **Linux stub (`LinuxAudioCapture`):** registered; `is_available()` → `False`; `invoke()` raises
  `CapabilityNotImplemented("audio-capture: no backend for linux")`. **[ROADMAP]** → ALSA/PulseAudio/PipeWire.

### Seam B — speech-to-text
- **Interface:** `SpeechToTextAdapter.invoke(audio, locale) -> Transcript`.
- **macOS impl (`MacOSSpeechToText`):** `_ensure_helper()` compiles/caches `lab/bin/arail-stt`; runs it
  via `subprocess.run([helper, "--audio", artifact.path, "--locale", locale, "--timeout","120"],
  capture_output=True, timeout=180)`; parses the JSON; maps non-zero exits to typed errors
  (`permission_denied`→`CapabilityUnavailable`, `model_unavailable`→`CapabilityUnavailable`,
  `no_speech`→returns an empty `Transcript` with `text=""`, others→`CapabilityError`). `is_available()`
  → `platform=='darwin'` and `shutil.which('xcrun')`. **No Python Apple bindings.**
- **Linux stub (`LinuxSpeechToText`):** registered; `is_available()`→`False`; `invoke()` raises
  `CapabilityNotImplemented("speech-to-text: no backend for linux")`. **[ROADMAP]** → whisper.cpp/faster-whisper.

**Discipline test (WC-B):** adding a working Linux backend = implement `invoke()` in
`backends/linux/stt_backend.py` only. The World contract, `capabilities.json` schema, `world_mount.py`,
`pkb*.py`, and the portal route are untouched. Verified by construction: none of them import a backend
module — they go through `registry`/`resolve_capabilities`/the adapter ABC only.

---

## 4. Mount integration `[BUILT]`

**Additive, non-breaking.** Do **not** modify `verify_seal`, `_BUNDLE_FILES`, `_stage_files`, or the
mount ordering. Add:

1. **`capabilities.py` read in `world_mount`** (new small helper, or in `capabilities/spec.py` imported
   by `world_mount`): after a successful `mount()`/`swap()` (step 5, pointer written), read
   `bundle_dir/capabilities.json` **iff present**:
   - **absent →** `resolved = []`. Mount proceeds exactly as today (**WC-D**, no regression, no new
     required file).
   - **present but malformed JSON / wrong schema →** log a warning, `resolved = []`, **mount still
     succeeds** (a bad capabilities file must never block knowledge mount — failure-mode grace). Record
     a `capabilities_error` string in the sidecar (below) so the operator sees it.
   - **present & valid →** `specs = parse_capabilities_file(...)`; `resolved = resolve_capabilities(specs)`.

2. **Persist resolution in a SIDECAR, not the sealed mount record.** Do **not** add fields to
   `MountRecord` (it round-trips via `to_dict`/`from_dict` and the world-mount tests assert its exact
   shape — changing it risks regression). Instead write
   `DATA_DIR/world-capabilities.json` atomically (temp+`os.replace`, same pattern as `_write_record`):
   ```json
   {"world": "<slug>", "resolved_at": "<iso>",
    "capabilities": [{"id","purpose","desired","state","adapter_platform","message"}],
    "capabilities_error": null}
   ```
   `unmount()` removes this sidecar alongside the pointer. A `current_capabilities(data_dir) ->
   list[ResolvedCapability]` reader mirrors `current_mount`.

3. **Call site:** add `_resolve_and_write_capabilities(bundle_dir, dd)` as the **last** best-effort step
   of `mount()` and `swap()` (after `wiki.schedule_rebuild()`), wrapped in try/except → log only. It is
   strictly additive; any failure inside it cannot fail the mount.

**Why a sidecar and not the record:** preserves the merged atomic-pointer contract and its tests
verbatim; resolution is *derived* state (recomputable from the bundle + the host), so it doesn't belong
in the signed pointer anyway.

---

## 5. The STT user flow → RAW note (WC-A) `[BUILT]`

### 5.1 Portal surface — the mic affordance
- **Location: the Chat page** (`templates/chat.html`), as a small mic button in the composer row.
  Rationale: Chat is where "capture a thought" already lives mentally; the dashboard is a monitor, not
  an input surface. (VISION allows chat or dashboard; chat is the better fit and chat.html already
  POSTs to the backend.) The button is **gated on a mounted World that resolved `speech-to-text` to
  `state=="available"`** — if STT isn't available it renders disabled with a tooltip carrying the
  resolution `message`. This makes the *inheritance* visible: no World / World without the capability
  → no live mic.
- **Interaction (minimal, not a designed UI):** tap → `getUserMedia({audio:true})` → `MediaRecorder`
  (mime per §1.2) → tap again to stop → POST blob → toast "Voice note saved → research/voice-notes/…"
  with `[Open]`. Reuse the existing dashboard toast component pattern (`toast-container`). Errors
  (permission denied, unsupported browser, transcribe failure) raise a toast with the actionable
  backend message. No waveform, no streaming, no edit-before-save (**[ROADMAP]**).

### 5.2 Endpoint — `POST /api/stt/transcribe` (NEW, in `portal/app.py`)
Mirrors the existing `/api/pkb/upload` multipart pattern (verified at app.py:9091).
```
form: audio (file part), mime (str), locale (str, default "en-US")
flow:
  1. mount = current_mount(); if None -> 400 {"error":"no world mounted"}
  2. cap   = resolved "speech-to-text"; if state != "available" -> 409 {"error": message}
  3. audio_adapter = registry.select("audio-capture"); artifact = audio_adapter.invoke(bytes, mime)
  4. stt_adapter   = registry.select("speech-to-text"); transcript = stt_adapter.invoke(artifact, locale)
  5. if transcript.text.strip() == "" -> 200 {"ok":false,"reason":"no_speech"} (toast: "Didn't catch anything")
  6. note_path = _land_raw_voice_note(transcript, mount.world)
  7. delete the temp audio artifact (finally:) ; return {"ok":true,"path": rel, "words": N}
errors: CapabilityUnavailable/CapabilityError -> 4xx/5xx with .user_message-style message; never 500-with-traceback.
```

### 5.3 Landing the RAW note (`_land_raw_voice_note`)
- **Section: `lab/pkb/research/voice-notes/` (decided in §0.3).** Filename:
  `<YYYY-MM-DD_HH-MM-SS>_voice-note.md`.
- **Content (DATA, never instructions):**
  ```markdown
  ---
  title: Voice note — <YYYY-MM-DD HH:MM>
  section: research
  kind: raw
  source: user-captured (speech-to-text, on-device)
  sourced: false
  world: <slug>
  confidence: <0.0-1.0>
  ---

  <transcript text>
  ```
  `sourced: false` + `kind: raw` mark it UNSOURCED/RAW — it is an observation to research, **not**
  gate-passed truth, and must never be promoted automatically (**[ROADMAP]** = promotion).
- **Index it** via the existing seam, exactly like the agent writers do:
  `from arail.pkb_index import ensure_ready, schedule_upsert; ensure_ready(root); schedule_upsert(path, pkb_root=root)`
  (wrapped in try/except — indexing failure must never lose the note; mirrors `pkb.write_agent_research`).
  `_source_kind_for_path` will map `research/...` to `"user"` — correct (user-captured).
- **Then** `wiki.schedule_rebuild()` (best-effort) so the SSE "Wiki rebuilt" event refreshes the KB tree
  (same mechanism the upload endpoint and mount use).

### 5.4 DATA-not-instructions boundary
The transcript text is written to a file and indexed for retrieval **only**. It is **never** passed into
a system prompt, never concatenated into Buddy's instructions. Buddy may *mention* "a new voice note
landed in research/" (a notification about a file) but the transcript bytes are not injected as
commands. This mirrors the world_mount security boundary ("terms.json is DATA; it never enters a
prompt"). The QA test in §6 asserts the transcript string never reaches any prompt-builder.

---

## 6. Failure-mode grace (setup 30% / security 20% weighting) `[BUILT]`

| Failure | Graceful behavior |
|---|---|
| Mic permission denied (browser) | `getUserMedia` rejects → toast: "Microphone access is needed for voice notes. Allow it in your browser's site settings for 127.0.0.1." No hang. |
| Speech-recognition TCC denied (helper) | helper exits `permission_denied` → 409 → toast with the macOS-settings guidance. Mount/lab unaffected. |
| No on-device model / language pack absent | helper exits `model_unavailable` (we never fall back to network) → 409 toast: "On-device speech model unavailable for <locale>." STT button stays usable for other locales. |
| Empty / garbage transcript | helper exits `no_speech` (or empty text) → no file written → 200 `{ok:false,reason:"no_speech"}` → toast "Didn't catch anything — try again." |
| Airgapped (`LAB_MODE=airgapped`) | **Works** — on-device, zero egress (§1.1). Asserted in test. |
| Capability declared, adapter unavailable | `resolve_capabilities` → `declared_unavailable`; mic button disabled w/ tooltip; **lab keeps working** (WC-C). |
| `capabilities.json` malformed | mount logs warning, `resolved=[]`, **mount succeeds**, `capabilities_error` recorded in sidecar. |
| Very long audio | helper `--timeout 120`; subprocess `timeout=180`; on timeout → `timeout` error → toast "Recording too long — keep voice notes under ~2 minutes for v1." (Long-form is [ROADMAP].) |
| Xcode CLT absent | `_ensure_helper()` raises `CapabilityUnavailable` with the `xcode-select --install` message; STT resolves `declared_unavailable`. |

---

## 7. Security / boundary `[BUILT]`

- **On-device only, zero cloud, no tokens, works airgapped.** Helper sets
  `requiresOnDeviceRecognition = true`; no network call exists in the STT path. **No secrets are
  written** (nothing sensitive → the `0600 secrets.env` convention does not apply here).
- **Egress assertion (test, §6):** run the transcribe path under `LAB_MODE=airgapped` with
  `egress.install_guard()` active and assert **no block is recorded** (because nothing tried to egress)
  — i.e. transcription completes with zero network attempts.
- **Audio blob & transcript are user data.** The audio temp file lives under
  `lab/data/cache/stt/<uuid>` and is **deleted in a `finally:`** after transcription (success or
  failure). The transcript persists only as the RAW note the user asked for. No audio is retained.
- **Transcript-as-RAW boundary:** §5.4. Never enters a prompt; `sourced:false` / `kind:raw`.
- **`capabilities.json` is unsigned (§0.2 caveat).** It cannot inject truth or instructions (it only
  selects ARAIL-owned adapters), so an adversarial/tampered capabilities.json can at most (a) ask for a
  capability we don't have → `declared_unavailable` (harmless), or (b) ask for `speech-to-text` →
  enables a button the user must still actively press. **No code-execution or data path opens from it.**
  Path-safety: `parse_capabilities_file` reads from `bundle_dir/capabilities.json` only (no paths from
  inside the JSON are ever opened). Recorded as accepted risk for v1.
- **Don't regress the airgap gate:** the STT path adds **no** new outbound-capable code; the existing
  `egress.py` guard is untouched.

---

## 8. capabilities.json schema + vendored fixtures

**Schema id `dac.world-capabilities/v1`** (defined here because DaC will later emit it; **ARAIL only
READS it**, never writes it, never edits qukaizen-dac):
```json
{
  "schema": "dac.world-capabilities/v1",
  "capabilities": [
    {
      "id": "speech-to-text",
      "purpose": "Transcribe spoken observations into the lab knowledge base.",
      "desired": true,
      "interface": { "inputs": ["audio"], "outputs": ["transcript", "segments", "confidence"] }
    }
  ]
}
```
`parse_capabilities_file` is **tolerant**: unknown top-level keys ignored; an entry missing `purpose`/
`interface` still parses (defaults: `purpose=""`, `desired=true`); a non-list `capabilities` or missing
`schema` → treated as malformed (→ `capabilities_error`, `resolved=[]`, mount still succeeds). The
`interface` block is descriptive metadata for the operator UI; ARAIL's actual contract is the adapter
ABC, not this JSON (the JSON can't widen what an adapter accepts).

**Vendored fixtures** (`tests/fixtures/world-bundles/`, same vendoring pattern as `physics/`). Build them
by **copying the existing sealed `physics/` bundle** (so seals stay valid) and adding an unsealed
`capabilities.json` sibling — since capabilities.json is seal-exempt (§0.2), the physics seal still
verifies. Three fixtures:
1. `world-caps-stt/` = physics + `capabilities.json` declaring **only** `speech-to-text`. (WC-A backend path.)
2. `world-caps-both/` = physics + `capabilities.json` declaring **`speech-to-text` AND `equation-ocr`**. (WC-C.)
3. `world-no-caps/` = physics with **no** `capabilities.json`. (WC-D.) (May reuse `physics/` directly.)
4. A small fixed audio sample `tests/fixtures/audio/hello.m4a` (~2–3 s clear speech) for the STT path.

---

## 9. Test strategy (arail QA: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression)

The Buddy-quality 30% here reads as **capability-resolution + the inherited-affordance behavior** (the
"lab partner gains a power" surface), since STT is the Buddy-adjacent capability. Tests in
`tests/test_capabilities.py` + `tests/test_stt_flow.py`. **The Apple Speech boundary is injectable:**
`MacOSSpeechToText` takes an optional `_runner` callable (default = the real subprocess) so tests inject
a fake transcript without invoking the live helper. A **live** test is gated behind a new pytest marker
`@pytest.mark.live_mic` (added to `[tool.pytest.ini_options].markers`) and skipped in CI.

**Setup (30%)**
- `test_resolve_no_capabilities_file_mounts_clean` — WC-D: mount `world-no-caps`, sidecar absent/empty, mount OK, no regression vs `test_world_mount.test_mount_clean`.
- `test_resolve_malformed_capabilities_mounts_clean` — corrupt JSON → mount succeeds, `capabilities_error` set, `resolved=[]`.
- `test_ensure_helper_missing_clt` — monkeypatch `shutil.which('xcrun')→None` → `is_available()` False → resolves `declared_unavailable` with the `xcode-select` message.
- `test_helper_compiles_once` (marked `live_mic`/skippable) — `_ensure_helper()` produces `lab/bin/arail-stt`, second call is a no-op.

**Buddy / capability-resolution (30%)**
- `test_wc_c_second_declared_id_zero_code` — mount `world-caps-both`: `speech-to-text`→`available` (or `declared_unavailable` off-Mac), `equation-ocr`→`declared_unavailable`, **lab still works, nothing raised**. Asserts no `equation-ocr` adapter exists in the registry. **This is the WC-C proof.**
- `test_registry_resolution_states` — the three states map correctly.
- `test_wc_b_linux_selected_raises_clean` — `ARAIL_FORCE_PLATFORM=linux`, `registry.select("speech-to-text").invoke(...)` raises `CapabilityUnavailable("speech-to-text: no backend for linux")`.
- `test_stt_lands_raw_note` — fake `_runner` returns a transcript → `/api/stt/transcribe` writes `research/voice-notes/*.md` with `kind:raw`,`sourced:false`, and `schedule_upsert` was called.

**Security (20%)**
- `test_no_apple_symbols_above_seam` (WC-B grep) — `grep -rE 'AVFoundation|SFSpeechRecognizer|pyobjc|\bobjc\b|swiftc|xcrun' src/ --exclude-dir=backends/macos` returns nothing; also assert no `import Speech`-equivalent outside macos backend.
- `test_no_domain_strings` (WC-A.2) — `grep -ri 'psychology' src/arail/capabilities src/arail/portal/app.py` clean.
- `test_transcribe_zero_egress_airgapped` — `LAB_MODE=airgapped` + guard installed; fake runner; assert `egress.read_recent_blocks()` shows **no** new block (nothing tried to egress).
- `test_transcript_not_in_prompt` — assert the transcript string is not passed to any prompt-builder (data-not-instructions boundary): the note is written, but Buddy's system-prompt assembly never receives it.
- `test_audio_temp_cleaned` — after transcribe, `lab/data/cache/stt/` holds no leftover blob.

**Happy path (10%)**
- `test_stt_end_to_end_fake_runner` — mount `world-caps-stt`, POST `hello.m4a`, get `{ok:true,path,words}`, file exists, searchable via `pkb.search`.

**Regression (10%)**
- `test_world_mount_unchanged` — existing `tests/test_world_mount.py` still passes (MountRecord shape unchanged); mounting a bundle with capabilities.json does not alter staging or the pointer.
- `test_unmount_removes_sidecar` — `unmount()` deletes `world-capabilities.json`.

---

## 10. Build order (each step has a done-condition mapped to a win condition)

Registry + seams + graceful-absence FIRST (cheap; prove WC-B/C/D and survive an STT-spike failure),
THEN the macOS STT backend + portal flow (WC-A).

1. **Scaffold `capabilities/` package** — `errors.py`, `adapter.py` (ABC + 2 sub-ABCs), `spec.py`
   (`CapabilitySpec`, tolerant `parse_capabilities_file`), `registry.py`.
   *Done:* importable; `registry.select("x")` returns `None`.
2. **Linux stubs + macOS stub-registration** — register both backends; `is_available()` correct;
   Linux `invoke()` raises `CapabilityNotImplemented` with the exact message; `ARAIL_FORCE_PLATFORM`
   override works. *Done (WC-B):* `test_wc_b_linux_selected_raises_clean` + the apple-symbol grep pass.
3. **`resolve_capabilities` + sidecar wiring in `world_mount`** (additive last-step in `mount`/`swap`,
   `current_capabilities`, `unmount` cleanup) + the three vendored fixtures.
   *Done (WC-C, WC-D):* `test_wc_c_second_declared_id_zero_code`, `test_resolve_no_capabilities_file_mounts_clean`, malformed-json test, and `test_world_mount_unchanged` all pass. **— off-ramp safe point: WC-B/C/D shippable even if step 4–6 stall.**
4. **Swift helper + `MacOSSpeechToText` + `MacOSAudioCapture`** — helper source, `_ensure_helper()`
   lazy compile to `lab/bin/arail-stt`, subprocess runner with injectable `_runner`, error-code mapping,
   temp-file lifecycle. *Done:* fake-runner unit tests pass; `live_mic` compile test passes locally.
5. **`POST /api/stt/transcribe` + `_land_raw_voice_note`** — endpoint per §5.2, RAW note per §5.3,
   index via `schedule_upsert`, `wiki.schedule_rebuild`, temp cleanup. *Done:* `test_stt_lands_raw_note`,
   `test_stt_end_to_end_fake_runner`, `test_audio_temp_cleaned`, egress + not-in-prompt tests pass.
6. **Chat mic affordance** — mic button in `chat.html` gated on resolved `speech-to-text=="available"`,
   `MediaRecorder` (mime per §1.2, no webm), POST, toast with `[Open]`, error toasts.
   *Done (WC-A):* manual local run — mount `world-caps-stt`, tap mic, speak ~30s, note lands in
   `research/voice-notes/`, indexed, searchable, zero egress, <15s end-to-end on the clear sample.

---

## 11. Tech-debt / ROADMAP register (Standing Rule 1)
- **[ROADMAP]** Linux backends (audio + STT) — registered-unimplemented only.
- **[ROADMAP]** Chrome/webm-opus audio support (needs a decoder; deliberately no ffmpeg dep in v1).
- **[ROADMAP]** `equation-ocr` adapter (only its `declared_unavailable` resolution ships — WC-C).
- **[ROADMAP]** streaming/live transcription, edit-before-save, waveform, diarization, multi-language, long-form (>~2 min).
- **[ROADMAP]** auto-promotion of a voice note out of RAW.
- **[DEBT]** `capabilities.json` is unsigned (§0.2) — revisit if/when it ever carries more than declared needs.
- **[DEBT]** lazy `swiftc` compile on first use moves a (small) build cost off setup; if it proves flaky, promote to an optional setup.sh step behind a flag.
```

---

## Addendum A — whisper local STT backend (replaces Apple Speech)

**Mode:** architect / DESIGN · **Date:** 2026-06-13 · **Repo:** arail (ARAIL-only)
**Status legend unchanged:** **[BUILT]** ships this addendum · **[ROADMAP]** registered/stubbed.

### A.0 Why this addendum exists, and why it's clean

The macOS Apple-Speech backend is **dead**. BUILD_LOG DELTA 1 proved on this machine that a bare
`swiftc`-compiled CLI binary **SIGABRTs** when it calls `SFSpeechRecognizer.requestAuthorization` —
macOS refuses the speech-recognition TCC grant to any process that is not a code-signed `.app` bundle
with an `Info.plist` usage-description. A section-embedded plist was insufficient. Shipping a signed
`.app` + signing pipeline is a redesign the owner has **rejected**.

**Owner decision (made): swap the speech-to-text backend to local Whisper.** This sidesteps Apple's
permission/signing wall entirely: there is **no Apple Speech framework, no TCC grant, no code-signing,
no app microphone access**. Mic capture stays in the **browser** (`getUserMedia`/`MediaRecorder`,
browser permission) exactly as built; the backend receives an **audio file** and transcribes it.

**The swap is entirely BELOW the existing adapter seam.** UNCHANGED and PRESERVED:
- the registry (`registry.py`) and `select()`/`adapters_for()` contract,
- the `SpeechToTextAdapter` / `AudioCaptureAdapter` ABCs and the `invoke(audio, locale) -> Transcript`
  / `invoke(audio_bytes, mime) -> AudioArtifact` signatures,
- `POST /api/stt/transcribe` and `_land_raw_voice_note` (the RAW note → `lab/pkb/research/voice-notes/`),
- the chat mic UI (MediaRecorder mp4-first, no webm),
- the **injectable `_runner` seam** boundary contract (a callable taking the helper-arg list, returning
  `(rc, stdout, stderr)`), so the existing fake-runner tests keep passing **without** real audio/model.

This swap **proves the seam was worth building**: only the body of one backend module changes.

**Bonus — win condition 3 (Linux off the stub).** Whisper is cross-platform. The new backend is
**platform-agnostic** (CPython + a pip wheel), so it serves **both** macOS and Linux. Decision in §A.4.
Apple-symbol cleanliness (WC-B) is **trivially** preserved: Whisper is not an Apple framework, so the
new backend contains **zero** `AVFoundation`/`Speech`/`swiftc`/`xcrun` strings (grep re-run below).

### A.1 SPIKE on this machine (Darwin / Apple Silicon, 2026-06-13) — REAL results

> All commands run for real; transcripts and latencies below are measured, not projected. This is the
> WC-A.4 proof the Apple-Speech spike never reached: a **real transcript** from a **local** model.

**1. Audio decode without ffmpeg — CONFIRMED.** The browser posts m4a/AAC (Safari). Whisper wants
16 kHz mono 16-bit WAV PCM. The system `afconvert` (always present, no install) does this:

```
$ say -o spike.m4a --data-format=aac "Hello, this is a test of the local whisper speech to text backend ..."
$ afconvert -f WAVE -d LEI16@16000 -c 1 spike.m4a spike.wav        # ← the EXACT command the backend runs
$ afinfo spike.wav  →  mono 16000 Hz, ~8.07 s     (exit 0)
```

`afconvert` handles m4a/aac/wav/flac. It **cannot** decode webm/opus (Chrome) — so Chrome stays
**[ROADMAP]** (unchanged from §1.2). If only a WAV is available it passes straight through (we still
re-encode to the canonical 16 kHz mono so the model never sees an unexpected rate/channel/depth).

**2. Whisper mechanism — chose (b) `faster-whisper` (CTranslate2). Installed and ran it for real.**

| Option | Spike result | Verdict |
|---|---|---|
| (a) `pywhispercpp` | bundles whisper.cpp; on Apple Silicon the Metal path generally needs a **local compile / cmake toolchain** for the prebuilt extension to light up — adds clean-machine compiler risk (the very wall we're fleeing). | Rejected — compiler friction vs 30%-weighted setup. |
| **(b) `faster-whisper`** | `pip install faster-whisper` pulled **all-arm64 prebuilt wheels** (`ctranslate2`, `av`, `onnxruntime`) in **~6 s**, **zero compiler**. Reuses the already-present `huggingface-hub` base dep for model download. Transcribed the WAV correctly (below). | **SELECTED.** |
| (c) build whisper.cpp from source → `lab/bin/` (Metal, lazy `cmake`) | mirrors the dead Swift-helper lazy-compile pattern, but reintroduces a **compiler dependency on first use** — exactly the clean-machine friction we are removing. | Rejected for v1 (kept as a perf [ROADMAP] if CPU latency ever bites). |

**Judged against the arail bar:** *setup-on-clean-machine (30%)* — (b) wins decisively: prebuilt wheels,
**no compiler**, no Xcode CLT. *airgapped* — model is pre-fetchable, then runs with **zero network**
(proven below). *Apple-Silicon perf for ~30 s memos* — sub-second on CPU int8 (below); Metal not needed.
*dep weight* — one pip dep, wheels only.

**Real transcription (the WC-A.4 proof):**

```
tiny.en  (78 MB) : transcribe 0.72 s for 8.1 s audio →
  "Hello, this is a test of the local whisper speech to text back in for the Arial Lab.
   The quick brown fox jumps over the lazy dog."
base.en (148 MB) : transcribe 0.31 s for 8.1 s audio →
  "Hello, this is a test of the local whisper speech to text backend for the ARL lab.
   The quick brown fox jumps over the lazy dog."
```

`tiny.en` mis-rendered "backend"→"back in" and "arail"→"Arial" (homophone/proper-noun); `base.en` got
"backend" right and only stumbled on the coined word "arail"→"ARL". **Decision: ship `base.en`** — the
smallest model that clears the WC-A.4 ≥90%-words bar on ordinary English, at **148 MB** and **~0.3 s for
8 s of audio** (CPU int8, well under the <15 s budget even extrapolated to a 2-minute memo: ~5 s). No
GPU, no Metal, no compiler.

**3. Airgapped behavior — CONFIRMED both directions:**

```
HF_HUB_OFFLINE=1  + local model dir present   → transcribes fine, ZERO network.
HF_HUB_OFFLINE=1  + model ABSENT              → raises LocalEntryNotFoundError (CATCHABLE, no hang).
```

The backend does not even rely on that exception: it checks for `model.bin` on disk **first** (pure
filesystem stat, never touches HF), and if absent + airgapped returns `model_unavailable` gracefully.

### A.2 Model management `[BUILT]`

- **Model:** `base.en` (faster-whisper / CTranslate2 conversion, English-only).
- **Size:** ~148 MB on disk (`model.bin`, `config.json`, `tokenizer.json`, `vocabulary.txt`).
- **Location:** `lab/models/whisper/base.en/` — verified against the real convention
  (`config.MODELS_DIR = LAB_ROOT/"models"`, and `lab/models/` already holds per-model subdirs like
  `Qwen2.5-7B-Instruct-4bit/`). `lab/models/` is git-ignored — **no model is committed.**
- **Fetch:** **first-use lazy download** with a clear activity-log line, mirroring the old lazy
  `swiftc` compile. On the first transcribe (or first `is_available()` that opts to warm), if
  `lab/models/whisper/base.en/model.bin` is absent **and** not airgapped, call
  `faster_whisper.download_model("base.en", output_dir=<that dir>)`, logging
  `"[stt] downloading whisper base.en (~148 MB, one time)…"`. Subsequent uses are a filesystem hit.
- **Airgapped / no model present:** if `model.bin` is absent **and** (`is_airgapped()` **or** the
  download fails for any reason), the adapter reports `model_unavailable` **gracefully** with an
  actionable message — **never crashes, never hangs, never a 500**:
  *"On-device speech model not installed. Run `./arailctl setup` with network once, or place the
  Whisper base.en model under `lab/models/whisper/base.en/`."* This makes STT resolve
  `declared_unavailable` (mic button disabled w/ tooltip) — the lab keeps working (WC-C property).

### A.3 The backend (the build contract) `[BUILT]`

A **single new platform-agnostic backend module** replaces both `backends/macos/stt_backend.py`'s
Apple path and `backends/linux/stt_backend.py`'s stub (see §A.4 for placement). Class:

```python
class WhisperSpeechToText(SpeechToTextAdapter):
    id = "speech-to-text"           # unchanged capability id
    platform = <see A.4>            # registered for both darwin and linux
    purpose = "Transcribe spoken observations into the lab knowledge base (on-device, local Whisper)."

    def __init__(self, runner: Optional[Runner] = None):
        self._runner = runner or _default_runner   # SAME injectable seam — CI mocks WITHOUT model/audio
```

**`is_available()`** — cheap, no model load, no network:
`return _whisper_importable() and _afconvert_present() and _model_present_or_fetchable()`
where:
- `_whisper_importable()` = `importlib.util.find_spec("faster_whisper") is not None` (do **not** import
  the heavy module here);
- `_afconvert_present()` = `shutil.which("afconvert") is not None` **on darwin**; on Linux, the
  equivalent decode check (see §A.4 — `ffmpeg`/`av`-decode availability);
- `_model_present_or_fetchable()` = `model.bin` exists on disk **OR** `not is_airgapped()`
  (fetchable). Pure filesystem + mode check — **no model load, no network in the probe.**

**The transcribe path** (`invoke(audio, locale="en-US")`), kept behind `_runner`:

The `_runner` is the **injectable seam** (unchanged contract: takes the arg list, returns
`(rc, stdout, stderr)` JSON, identical to the old helper shape). The **default `_runner`** now:
1. `afconvert -f WAVE -d LEI16@16000 -c 1 <audio.path> <tmp.wav>` (subprocess; on failure → JSON
   `{"ok":false,"error":"decode_failed",...}` rc≠0). On Linux, decode via `av`/`ffmpeg` (§A.4).
2. Lazy-load the model from `lab/models/whisper/base.en/` (fetch-on-first-use per §A.2; if absent +
   airgapped → `{"ok":false,"error":"model_unavailable",...}`).
3. `model.transcribe(tmp_wav, language="en", beam_size=1)`; join segments → transcript; emit JSON
   `{"ok":true,"transcript":...,"segments":[{"text","ts"}],"confidence":<avg_logprob→0..1>,"on_device":true}`.
4. `finally:` delete `tmp.wav`.

`invoke()` itself (the part **above** `_runner`, identical structure to today) parses the JSON and maps
error codes to typed errors — **the existing mapping block is reused verbatim**:
`no_speech`→empty `Transcript` (graceful), `model_unavailable`/`permission_denied`→`CapabilityUnavailable`
(409), `timeout`→`CapabilityError`, `unsupported_audio`→`CapabilityError`, else `CapabilityError`. The
signal-kill→`permission_denied` special-case (the old TCC hack) is **removed** (no TCC anymore).

**Where real model/binary lookups live so tests don't hit them:** model load, `afconvert`, and
`faster_whisper.download_model` all live **inside `_default_runner`** (and small module helpers
`_model_dir()`, `_ensure_model()`). Tests inject a fake `_runner` returning canned JSON → **no
afconvert, no model, no download** in CI. `is_available()` is monkeypatch-friendly (each probe is a
named helper). This is exactly the property that keeps the existing fake-runner tests green.

**Lookup-location constants:**
```python
def _model_dir() -> Path:                # lab/models/whisper/base.en
    from arail.config import MODELS_DIR
    return Path(MODELS_DIR) / "whisper" / "base.en"
WHISPER_MODEL = "base.en"
```

### A.4 Registration: platform-agnostic, and the dead Apple path

**Decision: register the Whisper backend for BOTH `darwin` and `linux`** (two `registry.register(...)`
calls with the same class, one instance per platform tag — or a tiny subclass setting `.platform`). The
registry's `select()` is platform-matched, so it picks the right-tagged instance; both delegate to the
same Whisper logic. This advances **WC-3 (Linux no longer a stub)** with the macOS work, for free.

- **macOS decode** = `afconvert` (system, present). **Linux decode** = the `av` wheel (PyAV, already
  pulled in transitively by faster-whisper) or `ffmpeg` if present; `is_available()` on Linux gates on
  the decode path being importable. (Linux audio-**capture** stub stays ROADMAP — capture is in the
  browser regardless, so Linux STT works today via the same `/api/stt/transcribe` file-in path.)

**Dead Apple-Speech path — REMOVE it (recommended, and chosen).**
- **DELETE** `src/arail/capabilities/backends/macos/stt_helper.swift` and the Apple-Speech body of
  `backends/macos/stt_backend.py`. Rationale: keeping dead Apple symbols around (even
  "registered-unavailable") risks WC-B grep regressions and carries a signing-wall liability for **zero**
  user value — the Whisper backend fully replaces it.
- **`backends/macos/audio_backend.py` STAYS** — it is the browser-audio **materialization +
  mime-validation** seam (writes the temp file, rejects webm/opus). It contains **no** Apple symbols and
  is still correct. (A `linux/audio_backend.py` equivalent already exists as the capture stub; the
  materialization logic can be shared/lifted to a platform-agnostic helper if convenient, but that's
  optional — not required for this addendum.)
- **Placement of the new STT module:** put `WhisperSpeechToText` in a new platform-neutral location,
  e.g. `src/arail/capabilities/backends/whisper_stt.py`, imported and registered (for both platforms)
  from `backends/__init__.py`. Replace the old `macos/stt_backend.py` registration and the
  `linux/stt_backend.py` stub registration with it. Keep `macos/audio_backend.py` (and the linux audio
  stub) registering as today.
- **WC-B is now trivially clean:** after removal, the Apple-symbol grep matches **nothing anywhere** (it
  already returns exit 1 / no output even before removal — re-verified 2026-06-13):
  `grep -rEn 'AVFoundation|SFSpeechRecognizer|pyobjc|\bobjc\b|swiftc|xcrun' src/ --exclude-dir=macos`
  → clean. After deleting the Swift helper, drop the `--exclude-dir=macos` and it's **still** clean.

### A.5 Dependency + setup impact `[BUILT]`

- **One new dep:** add `"faster-whisper>=1.2.0"` to **`pyproject.toml` base `dependencies`** (STT is a
  `minimalist`-tier capability; the registry/seam already ships in base). It brings prebuilt
  `ctranslate2`, `av`, `onnxruntime` wheels (all arm64/x86_64, **no compiler**). `huggingface-hub` —
  used for the model download — is **already** a base dep, so no new fetch machinery.
- **`scripts/setup.sh`:** **no change** (pure first-use lazy download, mirroring the old lazy compile)
  to keep clean-machine setup friction minimal — the ~148 MB model is fetched the first time the user
  taps the mic, behind the activity log, **not** at install. *Optional follow-up (not required):* a
  `--with-stt-model` prefetch flag for users who want airgapped STT provisioned at setup; default stays
  lazy. Justification: setup is 30%-weighted; forcing a 148 MB download on every clean install (most of
  whom won't use voice notes) is the wrong default.

### A.6 Failure modes (extends the §6 table) `[BUILT]`

| Failure | Graceful behavior (never a 500) |
|---|---|
| `afconvert` missing / fails (corrupt m4a) | `_runner` emits `decode_failed` → `CapabilityError` → toast: "Couldn't read that recording. Try again." |
| Unsupported input codec (webm/opus from Chrome) | rejected **upstream** in `MacOSAudioCapture` (unchanged) → `unsupported_audio` → toast: "Use Safari for voice notes in v1." Chrome = **[ROADMAP]**. |
| Model absent + airgapped (or download fails) | `_model_present_or_fetchable()` False → `is_available()` False → resolves `declared_unavailable`; if reached at invoke → `model_unavailable` → 409 toast with the `./arailctl setup` / place-model guidance. **Never hangs** (no network attempt when airgapped). |
| `faster_whisper` import / CTranslate2 runtime error | caught in `_runner` → `model_unavailable` (env-level) → 409 toast: "On-device speech engine isn't available; reinstall with `./arailctl setup`." |
| Empty / garbage transcript | join → empty/whitespace text → `no_speech` → no file written → 200 `{ok:false,reason:"no_speech"}` → toast "Didn't catch anything — try again." |
| Very long audio | cap at ~2 min: `invoke` checks WAV duration (afinfo / `info.duration`) and rejects >150 s with `timeout`-class message "keep voice notes under ~2 minutes for v1." subprocess `timeout=180` is the backstop. Long-form = **[ROADMAP]**. |

### A.7 Security / airgapped — re-confirmed, UNCHANGED `[BUILT]`

- **On-device, zero network at inference, no tokens.** Proven in §A.1.3 (`HF_HUB_OFFLINE=1` + local dir
  → transcribes, zero egress). The only network event in the whole feature is the **one-time model
  download** in non-airgapped mode, which is exactly the same posture as any other model pull and is
  **blocked** under `LAB_MODE=airgapped`. No API keys, no `secrets.env` involvement.
- **Temp lifecycle:** the uploaded audio temp (`lab/data/cache/stt/<uuid>`, written by the audio
  adapter) and the intermediate 16 kHz `tmp.wav` are **both deleted in `finally:`** — confirmed still
  holds; the endpoint's existing `finally:` cleanup of the audio artifact is unchanged, and the new
  `tmp.wav` is cleaned inside `_runner`'s own `finally:`.
- **Transcript is RAW / UNSOURCED DATA** (`kind:raw`, `sourced:false`), written to
  `research/voice-notes/` and indexed for retrieval only — **never** injected into a prompt
  (§5.4 unchanged). The `test_transcript_not_in_prompt` assertion still applies verbatim.
- **Egress assertion** (`test_transcribe_zero_egress_airgapped`) unchanged: airgapped + guard installed +
  model present + fake/real runner → no egress block recorded.

### A.8 Tests to add/adjust (arail 30/30/20/10/10) `[BUILT]`

Keep the `speech-to-text` capability id, the vendored fixtures, and the fake-`_runner` end-to-end test
**as-is** — they were written against the seam, not the Apple backend, so they survive the swap.

- **KEEP (no change):** `test_stt_end_to_end_fake_runner`, `test_stt_lands_raw_note`,
  `test_audio_temp_cleaned`, `test_transcribe_zero_egress_airgapped`, `test_transcript_not_in_prompt`,
  the registry-resolution / WC-C / WC-D tests, and the world-mount regression set. The fake `_runner`
  returns the same JSON shape, so they pass unchanged.
- **ADJUST:** `test_stt_backend.py` — drop the Swift-compile / `live_mic` (`_helper_compiles_once`) and
  the TCC-signal-kill mapping tests (Apple path deleted). Rename `live_mic` marker → **`live_stt`**.
  WC-B grep test: **drop `--exclude-dir`** — Apple symbols now match nothing anywhere (trivially clean).
- **ADD:**
  - `test_backend_available_model_present` / `test_backend_unavailable_model_absent_airgapped` —
    `is_available()` True when `model.bin` exists; False (→ `declared_unavailable`) when absent +
    `is_airgapped()`. Pure filesystem/mode, no download.
  - `test_afconvert_conversion` — feed a fixture m4a (or `say`-synthesized WAV), assert the produced WAV
    is **16 kHz mono 16-bit** (parse the RIFF header / `afinfo`). Gated `live_stt` if it shells
    afconvert; or unit-test the arg-list construction without shelling.
  - `test_real_transcription` *(marked `@pytest.mark.live_stt`, skipped in CI)* — run **real**
    `base.en` (or `tiny.en` for speed) on a tiny committed-or-synthesized WAV and assert a **non-empty**
    transcript containing an expected token (e.g. "hello"). This is the standing WC-A.4 proof.
  - `test_airgapped_graceful_unavailable` — `is_airgapped()` True + model absent → invoke raises
    `CapabilityUnavailable("model_unavailable")` with the actionable message; **no network, no crash.**
  - `test_no_apple_symbols_anywhere` — the WC-B grep over **all** of `src/` (no exclude) returns clean.

### A.9 Build order (zero new decisions; done-conditions → WC-A / WC-3)

1. **Add the dep + delete the dead Apple path.** Add `faster-whisper>=1.2.0` to base `dependencies`;
   delete `backends/macos/stt_helper.swift` and the Apple body of `macos/stt_backend.py`; remove its
   registration. *Done (WC-B):* `pip install -e .` succeeds; `grep -rEn 'AVFoundation|SFSpeechRecognizer|pyobjc|\bobjc\b|swiftc|xcrun' src/`
   (no exclude) is clean.
2. **Add `backends/whisper_stt.py` (`WhisperSpeechToText`).** `is_available()` (import + decode + model
   probe, no load), `_model_dir()`, `_ensure_model()` (lazy fetch with log line; airgapped-graceful),
   default `_runner` (afconvert→WAV→model→JSON, `tmp.wav` cleaned in `finally:`), and the **reused**
   error-code mapping in `invoke()` (drop the TCC special-case). *Done:* the KEPT fake-`_runner` tests
   pass unchanged (proves the seam held).
3. **Register for both platforms; retire the Linux STT stub.** Register `WhisperSpeechToText` (darwin +
   linux) from `backends/__init__.py`; remove the `linux/stt_backend.py` stub registration. *Done
   (WC-3):* on a forced `ARAIL_FORCE_PLATFORM=linux`, `select("speech-to-text")` returns the Whisper
   backend (available iff a decode path + model exist), **not** a `CapabilityNotImplemented` — Linux is
   off the stub.
4. **Adjust + add tests** (§A.8): rename `live_mic`→`live_stt`; add availability, afconvert, real-
   transcription (`live_stt`), and airgapped-graceful tests; broaden the WC-B grep test. *Done:* new +
   kept STT/capabilities tests green; `test_no_apple_symbols_anywhere` clean.
5. **First-use model fetch UX.** Confirm the activity-log line on first download; confirm no
   `scripts/setup.sh` change. *Done (WC-A.4):* on this Mac, mount `world-caps-stt`, tap mic in Safari,
   speak ~30 s → note lands in `research/voice-notes/`, indexed, searchable, **zero egress at inference**,
   `<15 s` end-to-end (measured ~0.3 s/8 s decode+transcribe; well within budget).

### A.10 Spike artifacts (provenance)

Measured on Darwin 25.5 / Apple Silicon, `arail/.venv` (Python 3.11.15), `faster-whisper 1.2.1`:
afconvert m4a→16 kHz-mono-WAV exit 0; `tiny.en` 78 MB / 0.72 s, `base.en` 148 MB / 0.31 s on 8.1 s
audio, both correct transcripts; `HF_HUB_OFFLINE=1` + local dir → transcribes with zero network; model
absent + offline → catchable `LocalEntryNotFoundError` (no hang). WC-B Apple-symbol grep clean.