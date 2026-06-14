# Sprint: 2026-06-14-equation-ocr

**Repo:** arail
**Branch:** qukaizen/arail-equation-ocr
**Owner:** Charlie D
**Opened:** 2026-06-14

## Intent

The THIRD capability-program sprint: the **second live capability** (`equation-ocr` — image-text OCR),
proving the capability-inheritance engine is **general**, not an N=1 STT wrapper. A mounted World that
declares `equation-ocr` lets the lab read printed text/numbers off an image → an **on-device** transcript
lands as a **RAW note** — same registry/seam/sidecar/RAW-note machinery as STT, **zero domain-specific
ARAIL code**. Physics-World fit: snap/upload a photo of a constants table or equation → RAW note to verify.

## Scope decisions

- **v1 = printed image-text OCR**, NOT equation→LaTeX reconstruction (LaTeX is ROADMAP — the real pain is
  error-prone numeric mantissas, not publication math). The declared id stays **`equation-ocr`** (fixture
  / WC-C continuity); its metadata was honestly narrowed (`outputs:["latex"]`→`["text"]`).
- **Backend (architect spiked on-machine):** **Apple Vision `VNRecognizeTextRequest` via an UNSIGNED
  `swiftc`-compiled helper** — the design STT wanted but couldn't have. Vision runs on a STATIC image with
  **no camera/TCC grant, no signing, no model download, no new deps, on-device**. Real spike: a CODATA
  table read with every mantissa/exponent exact (`1.380649e-23`, `299792458`, `7.2973525693e-3`) in
  ~0.3–0.4s, PNG/JPEG decode native, airgapped-clean.
- **Linux:** Apple Vision is macOS-only, so OCR can't serve Linux for free the way Whisper did → v1 ships a
  **registered Linux stub** (`CapabilityNotImplemented`); Tesseract/PaddleOCR is the cross-platform ROADMAP.
- **ARAIL-repo ONLY** (shared repo, parallel session active on `qukaizen/arail-multigoal-coach` in
  `../arail-multigoal` + others — their files left untouched). No qukaizen-dac edits.

## Win conditions — all MET (QA PASS, independently verified)

- **WC-A** — World declaring `equation-ocr` mounted → upload/paste an image → **on-device** Apple Vision
  OCR → RAW note (`kind:raw`/`sourced:false`, `lab/pkb/research/ocr-notes/`, `image:` provenance),
  indexed; zero cloud, zero domain code. **Live proof:** real Vision path, 0.433s, CODATA values exact.
- **WC-B** — Apple/OCR symbols (`Vision|VNRecognizeTextRequest|AppKit|swiftc|xcrun`) confined to
  `backends/macos/` only; STT Apple symbols fully gone; Linux stub raises cleanly.
- **WC-C (headline)** — the registry now resolves **TWO live capabilities** (`speech-to-text` +
  `equation-ocr`) `available` through the IDENTICAL resolve/sidecar path, with **zero edits** to
  `registry.py`/`resolve.py`/`spec.py`/`world_mount.py` (git-diff vs base empty). The engine generalizes.
- **Graceful absence** — declared-but-no-toolchain and no-World/no-capability degrade cleanly.

## Phase ledger

| Phase | Artifact | Status |
|---|---|---|
| think (visionary) | VISION.md | DONE 2026-06-14 — PROCEED; v1 text-OCR wedge, id kept |
| plan (architect) | ARCHITECTURE.md | DONE 2026-06-14 — Apple Vision unsigned-helper spiked + proven on-machine |
| build (builder) | BUILD_LOG.md | DONE 2026-06-14 — 6 steps, 7 atomic commits; two live capabilities; WC-A end-to-end |
| review (architect) | — | folded into QA gate |
| test (qa) | TEST_REPORT.md | DONE 2026-06-14 — **PASS**, no blockers |
| ship | — | ready (QA-clean; not pushed) |

## Ledger notes

- **New seam:** `ImageTextRecognitionAdapter` sub-ABC in `adapter.py`; `MacOSImageOCR`
  (`backends/macos/ocr_backend.py` + `ocr_helper.swift`, lazy-compiled via `xcrun swiftc -O` to
  `LAB_ROOT/bin/arail-ocr`) behind the injectable `_runner` (CI mocks with fake JSON — no Vision/image).
  Linux stub registered-but-unimplemented. `recognitionLevel=.accurate`, `usesLanguageCorrection=false`.
- **Endpoint** `POST /api/ocr/extract` (near-copy of `/api/stt/transcribe`): multipart image → OCR → RAW
  note. Upload validation: PNG/JPEG mime allowlist + magic-byte sniff + 12 MB cap; spoof/oversized/
  non-image/zero-byte → 422 (helper never invoked); temp image deleted in `finally:` even on a raising
  runner. Helper-compile failure → 409, never 500.
- **UI:** capability-gated `📷` upload/paste/drop in `chat.html`, gated on resolved
  `equation-ocr == available` exactly like the mic on `speech-to-text`.
- **Security (sharpest dimension — OCR text is attacker-controllable):** the mandatory
  `test_hostile_image_is_inert_raw_and_not_in_prompt` passes — an injection-payload image lands as inert
  RAW note text and reaches NO `_compose_prompt`/LLM call. Airgapped zero-egress (on-device Vision).
- **QA modified-test adjudication:** the four updated STT/capabilities tests were TIGHTENED, not weakened
  — greps moved from "asserted nowhere" to "macos-seam-only"; the WC-C tests flipped from the now-false
  "declared_unavailable" premise to the real registered reality. No assertion deleted, no security check
  removed.
- **Tests:** 72 passed + 2 `live_ocr` (real Apple Vision) passed, 0 failed in the feature slice. Full
  suite: 16 failed / 2151 passed — the known pre-existing baseline (one edited-file STT-UI test passes in
  isolation = ordering bleed); **ZERO new failures introduced**.
- **Residual risks (non-blocking, post-ship polish):** R1 — image filename / OCR text raw-interpolated
  into the note frontmatter (cosmetic; never re-parsed as instructions). R2 — a helper timeout falls to
  the 500 catch-all (practically unreachable given sub-second Vision + the size cap).
- **Commits** on `qukaizen/arail-equation-ocr` (7 + ledger; NOT pushed). Only equation-ocr files staged;
  the parallel session's uncommitted/untracked files untouched.

## Notes / next

- **Demo (macOS):** mount `tests/fixtures/world-bundles/world-caps-both` → `./arailctl start` → Chat →
  📷 (enabled when `equation-ocr` resolves) → upload an image of text/an equation → RAW note in
  `lab/pkb/research/ocr-notes/`.
- **ROADMAP:** equation→LaTeX reconstruction (pix2tex/LaTeX-OCR); a Linux OCR backend (Tesseract/Paddle);
  optional R1/R2 polish.
- **PR base:** target `qukaizen/arail-kv-available-budget` (this branch forks its committed tip, which
  has #77/#78/#79); retarget to `main` after that lands.
