# TEST_REPORT — equation-ocr (second live capability, on-device image-text OCR)

**Sprint:** `2026-06-14-equation-ocr` · **Repo:** `arail` · **Branch:** `qukaizen/arail-equation-ocr`
**QA persona** (paranoid). Mandatory ship gate. Reproduced independently; did NOT trust the builder's green checks.
**Base for diffs:** `qukaizen/arail-kv-available-budget`.

## VERDICT: **PASS**

Two structurally-different live adapters resolve `available` through one unchanged engine; the prompt-injection
boundary holds end-to-end; upload validation, temp cleanup, airgapped-zero-egress, and graceful-absence all
verified independently. The modified existing tests track provably-correct new behavior and weaken nothing.
Residual risks are low-severity (R1–R2) and do not block.

---

## THE KEY SCRUTINY — modified existing tests (adjudicated per-change)

All test modifications diffed against base. **None weaken a real guarantee.**

1. **`test_capabilities.py::test_registry_resolution_states`** — was `equation-ocr → declared_unavailable`
   + `adapter_platform is None`; now asserts state ∈ {available, declared_unavailable} and
   `adapter_platform ∈ {darwin, linux}`. **LEGITIMATE.** The OCR sprint registers a real backend, so the old
   "no adapter at all" state is provably gone; the new assertion still pins host-correct behavior (it does NOT
   accept the dead "no adapter" path). Not weakened — it tracks the WC-C flip.

2. **`test_capabilities.py::test_wc_b_no_apple_symbols_anywhere`** and
   **`test_stt_backend.py::test_no_apple_symbols_anywhere`** — both dropped `swiftc|xcrun` from the grep
   pattern (now `AVFoundation|SFSpeechRecognizer|pyobjc|\bobjc\b`) and added `--include`/`--exclude-dir`.
   **LEGITIMATE, and the loosening is fully compensated.** The STT *Apple-Speech* symbols
   (`AVFoundation|SFSpeechRecognizer|pyobjc|objc`) are STILL asserted absent everywhere — I confirmed zero hits
   in `src/` independently. `swiftc`/`xcrun` are legitimately reintroduced BELOW the seam by the Vision backend
   (ARCHITECTURE §1.4) and are re-locked by the NEW, tighter `test_wc_b_no_apple_ocr_symbols_above_seam`, which
   asserts `Vision|VNRecognizeTextRequest|AppKit|swiftc|xcrun` match **only** under `backends/macos/`. Net
   coverage of `swiftc`/`xcrun` is NOT lost — it moved from "nowhere" to "macos-seam-only," which is the correct
   guarantee post-OCR. I reproduced both greps by hand (see WC-B evidence).

3. **`test_capabilities.py::test_wc_c_second_declared_id_zero_code`** — was `adapters_for("equation-ocr")==[]`
   + sidecar `state == declared_unavailable`; now asserts an adapter IS registered and state ∈ {available,
   declared_unavailable}. **LEGITIMATE.** This is the exact N=1→general flip the sprint exists to make
   (ARCHITECTURE §9 step 2). The old assertion encoded the now-falsified "no adapter" premise. Not a weakening —
   a correctness update.

4. **`test_stt_chat_ui.py`** (+11 lines `test_chat_surfaces_safari_caveat_at_load`) and
   **`test_capabilities.py`** (+~100 lines of new WC-C/WC-B/availability tests) — pure ADDITIONS, no existing
   assertion touched. Verified by diff.

**No deleted assertions. No broadened grep that should have stayed tight. No removed security check.** No BLOCKER
from the test-modification review.

---

## Win conditions (independently evidenced)

- **WC-A (inheritance, 2nd modality) — PASS.** `live_ocr` real-Apple-Vision tests pass (2 passed). End-to-end
  fake-runner flow lands a `research/ocr-notes/*.md` note with `kind: raw`, `sourced: false`, `world`, `image`
  provenance, indexed via `schedule_upsert`. WC-A.1 zero-egress: `test_ocr_zero_egress_airgapped` passes. WC-A.2
  zero domain strings: grep clean. WC-A.3 inert RAW: see Security. WC-A.4 digit fidelity/latency: `live_ocr`
  real-Vision proof passes on this Mac.
- **WC-B (Linux-ready / no Apple symbols above seam) — PASS.** My own grep:
  `Vision|VNRecognizeTextRequest|AppKit|swiftc|xcrun` over `src/` hits ONLY
  `backends/macos/ocr_backend.py` + `ocr_helper.swift`. STT Apple symbols: zero hits anywhere. Linux stub raises
  `CapabilityNotImplemented("equation-ocr: no backend for linux")` (`test_wc_b_linux_ocr_raises_clean`).
- **WC-C (TWO live capabilities, zero engine code) — PASS (headline).** Ran the REAL `resolve_capabilities`
  path on this Mac: `speech-to-text: available (darwin)` AND `equation-ocr: available (darwin)`,
  `registry.select("equation-ocr") → MacOSImageOCR`. **`git diff` of `registry.py`, `resolve.py`, `spec.py`,
  `world_mount.py` vs base = EMPTY** — confirmed independently. A third undeclared id still resolves
  `declared_unavailable` (`test_wc_c_third_undeclared_id_still_declared_unavailable`). Fixture narrowed
  correctly: id unchanged, `outputs: ["latex"]→["text"]`, honest purpose.
- **WC-D (graceful absence) — PASS.** Missing CLT → `is_available()` False → `declared_unavailable` with
  `xcode-select` hint (`test_ocr_unavailable_missing_clt`). Helper compile failure → `CapabilityUnavailable` →
  409, never 500 (verified in `_ensure_helper`/`_default_runner` mapping). Off-platform (linux) →
  `declared_unavailable`. No-`capabilities.json` mount unaffected (world_mount tests green).

## Probe results

| Probe | Result |
|---|---|
| Feature suites (ocr_flow/backend/chat_ui + capabilities + stt + world) | **72 passed, 0 failed** |
| `live_ocr` real Apple Vision | **2 passed** |
| Hostile-image inert-RAW + not-in-prompt | **PASS** (payload in note body, never in any lab_brain prompt/compose call) |
| Upload validation (non-image, mime-spoof, oversized, zero-byte) | **PASS** — 422, helper never invoked |
| Temp image deleted in `finally:` incl. raising runner | **PASS** |
| Airgapped zero egress | **PASS** |
| WC-C two-live via REAL resolve path | **PASS** (darwin/darwin) |
| Engine files unchanged vs base | **PASS** (empty diff) |
| Apple-symbol greps (mine) | **PASS** (macos-seam-only; STT symbols gone) |
| Helper-compile-failure → 409 not 500 | **PASS** (CapabilityUnavailable mapping) |

## Full-suite regression adjudication

Broad suite (excl. `live_*`, `tests/portal/` parallel-session dir): **16 failed, 2151 passed.**
**NONE introduced by this sprint.** Adjudication:
- `test_stt_chat_ui::test_mic_enabled_when_stt_available` — the one failure in a file THIS sprint modified.
  **Passes in isolation (3/3).** Test-ordering/env-bleed, not introduced; the sprint's edit to that file is a
  pure addition.
- `test_aerollm_defaults` (4, kv-budget) — fail even in isolation; belong to the `kv-available-budget` base /
  parallel session; zero OCR coupling.
- `test_docs_routes*`, `test_dashboard_layout_v2`, `test_swarm_goal_surfaces`, `test_system_metrics`,
  `test_qa_airgap_*` — pre-existing baseline (env/ordering); none import or touch any OCR file (verified by grep).
This is the known ~16-failure baseline; OCR adds zero regressions.

## BLOCKERs / residual risks

- **No BLOCKERs.**
- **R1 (low) — filename/payload-text interpolated raw into note frontmatter.** `image_filename` (attacker-
  influenced, multipart) and the OCR `text` are interpolated verbatim into the `.md` frontmatter/body
  (`_land_raw_ocr_note`, app.py:9384). A payload containing `\n---\n` could inject cosmetic fake frontmatter.
  **Not a security boundary breach:** the note is inert markdown DATA, never re-parsed as instructions, never fed
  to a prompt (the real threat — prompt injection — is closed and tested). Worst case is KB note cosmetics.
  Proposed (post-ship) fix: sanitize/escape the `image:` value and detect a `---` line in the body. Low priority.
- **R2 (low) — helper-timeout falls to the 500 catch-all.** `_default_runner` re-raises
  `subprocess.TimeoutExpired`; the endpoint's bare `except Exception` returns a safe-message 500 (not a hang,
  not a leak — `finally:` still unlinks). Vision is sub-second and the 12 MB cap bounds input, so practically
  unreachable. Proposed: map `TimeoutExpired` to a 422/409 graceful message. Low priority.
