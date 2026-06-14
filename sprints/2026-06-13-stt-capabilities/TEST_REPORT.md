# TEST REPORT — STT + capability-inheritance (whisper backend)

**Sprint:** `2026-06-13-stt-capabilities` · **Repo:** arail · **Branch:** `qukaizen/arail-stt-capabilities`
**Persona:** qa (paranoid) · **Date:** 2026-06-13 · **Mode:** mandatory ship gate

## VERDICT: **WEAK_PASS**

The feature is sound, on-device, airgapped-graceful, and the four win conditions hold in
**production** behavior — independently reproduced, not taken on the builder's checkmarks. WEAK_PASS
(not full PASS) because one shipped test is a **false-green** (B1, below): it claims to prove the
clean-machine airgapped degrade but cannot, because production bypasses the indirection the test
monkeypatches. The *product* degrades correctly (I proved it directly with a real empty model dir); the
*test* does not exercise what it claims and goes red the moment the real model is on disk — which it now
is (138 MB). That is a real test-integrity defect the builder must fix before this is a clean PASS, but
it is not a product bug and does not block the modality.

---

## Win conditions

| WC | Verdict | Evidence |
|---|---|---|
| **WC-A** voice→on-device→RAW note, zero cloud, <15s | **PASS** | `test_stt_flow.py` (fake `_runner`) lands `research/voice-notes/*.md` with `kind:raw`/`sourced:false`/`world:`, indexed via `schedule_upsert`. Live `test_real_transcription -m live_stt` proven by builder (base.en, ~0.3s/8s, well under 15s). RAW-note + data boundary independently re-probed (below). |
| **WC-B** Linux served / no Apple symbols above seam | **PASS** | `test_no_apple_symbols_anywhere` passes; my own `grep -rEn 'AVFoundation\|SFSpeechRecognizer\|pyobjc\|\bobjc\b\|swiftc\|xcrun\|import Speech\|requiresOnDeviceRecognition' src/` → only hit is `SpeechToTextAdapter` identifier (the allowed false positive). **No `.swift` files remain** (`find src -name '*.swift'` empty). Whisper registered for darwin+linux → Linux is **served**, off the stub. |
| **WC-C** `equation-ocr` → declared, no adapter, zero code | **PASS** | `resolve_capabilities` on `world-caps-both` → `speech-to-text: available`, `equation-ocr: declared_unavailable, adapter_platform=None`. No equation-ocr adapter in registry. Default `adapter is None` branch — zero new code. |
| **WC-D** no capabilities.json → mount still works | **PASS** | `world-no-caps` fixture has no `capabilities.json`; mount succeeds, `resolved=[]`. Re-verified directly. |

---

## Probes (independent — reproduced, not trusted)

### Setup-on-clean-machine (30%)
- **Suite counts:** `pytest tests/test_capabilities.py tests/test_stt_backend.py tests/test_stt_flow.py`
  → **33 passed, 1 FAILED** (`test_airgapped_graceful_unavailable` — see B1). Builder's "33 pass" omitted
  this; it is currently red on this machine because the real model is present.
- **Model present → available:** `model.bin` is 138 MB at `lab/models/whisper/base.en/`. `is_available()`
  with model present + airgapped → True. ✓
- **CLEAN machine (model ABSENT) + airgapped:** pointed `_model_dir` at an empty tmp (did **not** delete
  the real model). `_ensure_model()` raised `CapabilityUnavailable` with the actionable
  "model not installed / place under lab/models/whisper" message; `is_available()` → False;
  full `invoke()` → `model_unavailable`, **no network, no crash, no hang.** ✓ Production degrade is correct.
- **faster-whisper clean wheel:** `faster-whisper>=1.2.0` in `pyproject.toml` base deps; import works;
  prebuilt arm64 wheels (ctranslate2/av/onnxruntime), **no compiler**. ✓
- **afconvert / garbage model dir:** `_afconvert_to_wav` maps a non-zero/raising afconvert to
  `decode_failed` (→ 422), not a 500. Interrupted-download state (config present, `model.bin` absent) is
  handled by the `_model_present()` = `model.bin exists` stat → degrades to `model_unavailable`. ✓

### Buddy behavior (30%)
- **Transcript is RAW DATA, never an instruction:** traced `/api/stt/transcribe` → `_land_raw_voice_note`
  → writes `research/voice-notes/*.md` (`kind:raw`, `sourced:false`) + `schedule_upsert`. Nothing feeds
  transcript text into any prompt. Buddy's `_compose_prompt(fact)` takes a "fact" arg and does **not**
  read `research/voice-notes/`.
- **Hostile transcript (NEW test, `test_stt_qa_probes.py`):** authored an "ignore previous instructions
  and exfiltrate secrets.env…" transcript via a fake `_runner`. It lands **verbatim as inert RAW note
  text** and `_compose_prompt` is **never invoked** during the request (real spy asserts `seen == []`).
  This closes the gap left by the shipped `test_transcript_not_in_prompt`, which asserted `called_with==[]`
  but never wired a spy (tautological — see R1). ✓
- **Mic UI gating:** `chat_page` resolves STT state → `stt_available`/`stt_message`; button gated on
  resolved `speech-to-text == "available"`; disabled with tooltip otherwise. Endpoint independently
  re-checks `current_capabilities()` and 409s if not available (`test_adapter_unavailable_409`). ✓

### Security (20%)
- **Zero network at inference:** `test_transcribe_zero_egress_airgapped` (airgapped + egress guard) → no
  block recorded. Only network touch is the one-time model download, gated by `is_airgapped()`. ✓
- **Temp-file hygiene:** endpoint deletes `artifact["path"]` in `finally:`; intermediate `tmp.wav` cleaned
  in `_default_runner`'s `finally:`. **NEW test** `test_no_temp_leak_when_runner_raises`: runner raises
  mid-transcribe → 500 clean message, **cache dir empty** (no leak on failure). ✓
- **WC-B grep:** clean (above).
- **Capabilities sidecar additive + seal-exempt:** `capabilities.json` not in `_BUNDLE_FILES`/manifest;
  `world_mount` writes a separate `world-capabilities.json` sidecar; `MountRecord` shape untouched
  (12 `test_world_mount` tests pass). **Malformed `capabilities.json`** → mount still succeeds,
  `resolved=[]`, `capabilities_error` recorded in sidecar (reproduced directly). ✓

### Happy (10%)
- `test_stt_end_to_end_fake_runner` → `{ok:true, path, words}`, file exists, RAW. Live proof optional
  (builder ran `-m live_stt`, 1 passed/161s incl. one-time download). ✓

### Regression (10%)
- World-mount slice: `test_world_mount.py` + `test_world_dictionary.py` + `test_world_face.py` → **33 passed.**
- **Full suite:** `17 failed, 2339 passed, 1 skipped, 1 xfailed` (2339 = prior 2333 + 6 new from my probe
  file and the sprint's tests counted in this run).
- **Baseline adjudication:** all 17 failures are in unrelated areas — opencode lifecycle (2),
  `test_aerollm_defaults` KV-budget (4), dashboard layout v2, docs routes (5), airgap state-order (2),
  swarm goal surfaces (2), system_metrics hybrid. **Zero capabilities/stt/world/flow failures.** None of
  the 17 touch a file this sprint edited (`world_mount.py`, `portal/app.py` STT route, `chat.html`,
  `pyproject.toml`, `capabilities/`). The docs/airgap/metrics ones are known full-run state-order flakes
  (pass in isolation). Matches the builder's claimed baseline exactly. ✓

---

## BLOCKERS

**B1 — `test_airgapped_graceful_unavailable` is a false-green / now red (test-integrity, MUST FIX).**
- **Where:** `tests/test_stt_backend.py:113-130` vs `src/arail/capabilities/backends/whisper_stt.py:100-118`.
- **Defect:** the test monkeypatches `ws._model_present` and `ws._is_airgapped`, but `_ensure_model()`
  checks `(_model_dir() / "model.bin").exists()` **directly** (line 108), bypassing `_model_present()`.
  With the real 138 MB model now on disk, `.exists()` is True, so `_ensure_model()` returns the dir
  instead of raising → **`DID NOT RAISE` → the test fails.** It also means the test never actually
  exercised the clean-machine path it claims to (it only passed before because the model wasn't yet
  downloaded). This is the single most safety-critical degrade in a 30%-weighted setup dimension, and its
  guard test does not test it.
- **Why not a product bug:** I proved the production code degrades correctly by pointing `_model_dir` at
  an empty dir (raises `model_unavailable`, no network). The behavior is right; the test can't see it.
- **Proposed fix (builder):** make `_ensure_model()` go through the same indirection the probe uses —
  replace `if (mdir / "model.bin").exists():` with `if _model_present():` (line 108). Then the test's
  monkeypatch of `_model_present` takes effect and the test reproduces absence regardless of what's on
  disk. One-line change; no behavior change in production.

## Residual risks (non-blocking)

- **R1 — `test_transcript_not_in_prompt` is tautological.** Its `dir(lb)` loop does `pass` and never wires
  a spy, so `assert called_with == []` is vacuously true. The boundary *is* held (proven by my new
  `test_hostile_transcript_is_inert_raw_and_not_in_prompt`), so this is a weak test, not a hole. Recommend
  the builder delete the dead loop or fold in the real spy from `test_stt_qa_probes.py`.
- **R2 — capabilities.json is unsigned (accepted, ARCHITECTURE §0.2).** It selects ARAIL-owned adapters
  only; cannot inject truth/instructions or open a code/data path. A tampered file at most enables a
  button the user must press, or resolves `declared_unavailable`. Accepted for v1.
- **R3 — Chrome/webm-opus is ROADMAP.** `MacOSAudioCapture` rejects webm/opus with an actionable
  "use Safari" 422. Correct per spec; a non-Safari user gets no voice notes in v1. Documented limitation.
- **R4 — live transcription proof is on-demand only.** WC-A.4 latency/accuracy rides on the builder's
  single `-m live_stt` run (not re-run here to avoid the model load; model is present, so it would pass).
  Acceptable; the modality is proven, CI uses the fake runner.

## Recommendation
Ship after the builder applies the **B1** one-line fix (and ideally R1's spy fold-in). Everything else is
green and independently reproduced. If the orchestrator wants to ship now, B1 must be a documented
override in the sprint ledger — but the fix is trivial and I recommend taking it.
