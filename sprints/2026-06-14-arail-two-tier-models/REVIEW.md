# Review: ARAIL Two-Tier Model Architecture (v1.1 models)

**Date:** 2026-06-14
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 9d6875f
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at b03f0ed
**Reviewer:** architect (review mode)

## Verdict: WEAK_PASS

No BLOCKs. All 8 implementation steps landed, all 10 findings are addressed in
code or test, the 17 new tests pass, and no regressions were introduced. The
single gap is F8's *visual* rendering: `backend_notice` is correctly produced
and emitted in the SSE `final` event, but no template/JS consumes it yet, so the
"via AirLLM fallback (slower)" label is data-honest but not yet user-visible.
That is a documented follow-up, not a stop-ship — hence WEAK_PASS.

## Spec adherence

Verified against ARCHITECTURE.md, not paraphrased from the build log.

**8 implementation steps — all hit:**

1. `scripts/setup.sh` `ollama_default_enabled()` (line 47) — reconciled F1.
   Now gates on `LAB_TIER` (minimalist → always install Ollama), preserves
   "Apple Silicon prefers MLX" for maximus deep only. Comment explicitly warns
   future readers not to revert to ACCEL-gating. **Matches spec exactly.**
2. `models/ai-eng/Modelfile.default` — verified drift-free: `FROM llama3.2:1b`,
   SYSTEM ends `Built with Llama.` No change needed. **Confirmed.**
3. `tests/test_llama_disclosure.py` (NEW, 10 tests) — encodes the full
   disclosure contract. **Confirmed, runs green.**
4. `tests/test_model_separation.py` (NEW, 7 tests) — asserts MODEL_NAME ≠
   AEROLLM_MODEL and namespace separation. **Confirmed, runs green.**
5. `scripts/upgrade.sh` — honest arm64-vs-CUDA notice (lines 112–140). arm64 →
   "AeroLLM (local, fast)" + build/download steps; non-arm64 → "Apple-Silicon-
   only today" + AirLLM opt-in + cloud alternative. Does NOT auto-download the
   4 GB weights (prints `huggingface-cli download`). **Matches spec.**
6. `src/arail/portal/app.py` — `backend_notice` added to `_build_chat_result`
   (line 5247) and emitted in all `final` SSE events (lines 5602/5633/5674/5814).
   **Data path matches spec; rendering gap noted below.**
7. `capture_tier()` 16 GB floor (lines 1195–1209) — F7 honest path, 48 GB
   informational notice preserved. **Matches spec.**
8. `docs/tier-selection.md` (NEW) — canonical which-tier copy + table + per-tier
   disclosure. **Confirmed present.**

**Drift:** none material. The interleaved unrelated commit `27d43e8`
(equation-ocr artifacts) landed between sprint commits but touches no sprint
files — cosmetic history noise, not scope drift.

## Code quality findings

- [INFO] `ollama_default_enabled()` rewrite is clear, well-commented, low
  complexity. The "do NOT revert" comment is exactly the tech-debt mitigation
  the architecture asked for.
- [INFO] `_build_chat_result` `_backend_notices` dict is a clean lookup; no
  duplication, no magic.
- [INFO] Both new test files are well-documented with stop-ship rationale inline
  and test *behavior/contract*, not implementation internals.
- [INFO] `MODEL_MLX_ID="mlx-community/Qwen3-8B-4bit"` (setup.sh:70) is a
  *separate legacy starter-model* variable, NOT `AEROLLM_MODEL`. It does not
  conflict with the Qwen2.5-7B deep default — verified `AEROLLM_MODEL` defaults
  to `Qwen2.5-7B-Instruct-4bit` in backends.py:1473/1513. No bug, but the two
  Qwen IDs in one file are a future-reader footgun (see tech debt).

## Security findings

- [INFO] No new user-input, auth, crypto, or deserialization surface. The
  upgrade notice and backend label are output-only strings.
- [INFO] `huggingface-cli download` is printed for the user to run manually, not
  auto-executed — no silent network egress added; airgapped posture preserved
  (the only network call remains the setup-time `ollama pull`).
- [INFO] `backend_notice` strings are static literals, no interpolation of
  untrusted data — no injection vector into the SSE payload.

## Test coverage assessment

- 17 new tests, all passing (verified locally via `.venv`: `17 passed in 0.02s`).
- Suite delta per BUILD_LOG: baseline 41 failing / 2355 passing → 40 failing
  (-1) / 2373 passing (+18). No new failures; net regression negative. **Not
  independently re-run in full here — see QA recommendation #5.**

**Failure-mode → test mapping (11-row table):**

| # | Mapped? | Where |
|---|---|---|
| F1 | YES | `ollama_default_enabled()` tier-gate + (integration, QA) |
| F2 | PARTIAL | non-fatal path in setup.sh; **integration smoke is QA-only** |
| F3 | DEFERRED | doctor/headroom — QA runtime check, no unit test |
| F4 | EXISTING | `_resolve_kv_budget` unit tests (pre-sprint) |
| F5 | YES | upgrade.sh notice + backend_notice; QA verifies CUDA print |
| F6 | EXISTING | deep_policy fast-fallback (pre-sprint) + QA smoke |
| F7 | YES | capture_tier 16 GB floor |
| F8 | PARTIAL | backend_notice emitted; **render not wired (gap)** |
| F9 | YES | test_llama_disclosure.py (10 assertions) |
| F10 | YES | test_model_separation.py (7 assertions) |
| F11 | QA | reasoning 5-prompt set — QA executes, not unit-testable |

F2, F3, F6, F11 are intentionally integration/QA-bound per the test strategy —
acceptable. F8 is the only mapping that is *weaker than the architecture
promised*.

## Performance assessment

Not benchmarked in this sprint (correctly — this is a wiring/copy/hardening
sprint). The win-condition latency gates (minimalist TTFT <2 s, setup-to-first-
token <10 min, maximus no-OOM) are explicitly delegated to QA on a 16 GB
M-series. No hot-path code was added; `_backend_notices` lookup is O(1).

## Tech debt delta

Matches the architecture's prediction (net slightly negative) with one addition:

- **As predicted (added):** the `ollama_default_enabled` tier-branch (mitigated
  by the explicit comment); AirLLM-CUDA fallback documented-not-built.
- **As predicted (repaid):** Llama disclosure now machine-verified; 1B/7B
  conflation now regression-tested.
- **NEW debt (file follow-up):** `backend_notice` is produced but no
  template/JS renders it — F8's user-visible label is latent. Also two distinct
  Qwen IDs live in setup.sh (`MODEL_MLX_ID` Qwen3-8B vs `AEROLLM_MODEL`
  Qwen2.5-7B) with no comment distinguishing them; a future reader could
  "unify" them and reintroduce conflation. Both should be ticketed.

## Finding-by-finding checklist

- [x] **F1** (Ollama gate) — `setup.sh:47` gated on `LAB_TIER`, not ACCEL.
      Minimalist always installs Ollama. **RESOLVED.**
- [x] **F2** (offline pull) — non-fatal, prints manual command. Integration
      smoke is QA-bound. **RESOLVED (code), QA-verify.**
- [~] **F3** (16 GB minimalist crowding) — honest-notice path exists; no unit
      test, doctor/runtime check is QA. **ACCEPTABLE.**
- [x] **F4** (KV budget OOM) — existing `_resolve_kv_budget` clamp + tests.
      **COVERED.**
- [x] **F5** (CUDA AeroLLM-not-ready) — upgrade.sh honest notice + backend
      label data. **RESOLVED.**
- [x] **F6** (deep weights missing) — existing deep_policy fast-fallback.
      **COVERED.**
- [x] **F7** (16 GB floor) — `capture_tier()` floor check at 17179869184 bytes
      with honest downgrade message. **RESOLVED.**
- [~] **F8** (AirLLM honest label) — `backend_notice` produced + emitted in SSE,
      but **no frontend renders it.** Data-honest, not yet visible. **PARTIAL.**
- [x] **F9** (Llama disclosure drift) — `test_llama_disclosure.py`, 10
      assertions, all green; covers Modelfile/catalog/README/NOTICE/licenses.
      **RESOLVED. Stop-ship gate is live.**
- [x] **F10** (1B/7B conflation) — `test_model_separation.py`, 7 assertions,
      confirms MODEL_NAME (`llama-ai-eng`) ≠ AEROLLM_MODEL
      (`Qwen2.5-7B-Instruct-4bit`). **RESOLVED.**
- [ ] **F11** (deep reasoning regression) — QA-only; deep must beat minimalist
      ≥4/5. **NOT YET EXERCISED — QA must run.**

## Required actions before merge

1. **File the F8 follow-up ticket:** wire `backend_notice` into the chat
   template/JS so the "via AirLLM fallback (slower)" / "via AeroLLM (local,
   fast)" label is actually shown. The data is honest but invisible today.
2. **File the Qwen-ID-disambiguation ticket:** add a comment in setup.sh
   distinguishing `MODEL_MLX_ID` (Qwen3-8B legacy starter) from the
   `AEROLLM_MODEL` deep default (Qwen2.5-7B), so the conflation footgun stays
   closed in the script too, not only in the test.

Neither blocks ship. Both must have a home (ticket) before PASS is granted by a
follow-up review.

## Recommendations for QA (beyond the unit tests)

The paranoid arail checklist (30% setup / 30% Buddy / 20% security / 10% happy
/ 10% regression) plus:

1. **Clean-machine setup on Apple Silicon (F1, highest priority).** This is the
   exact bug the sprint fixed. Run `ARAIL_NONINTERACTIVE=1` minimalist setup on
   an M-series box and confirm `ollama show llama-ai-eng` succeeds and a
   one-token chat completes via `OllamaNativeBackend`. The whole F1 fix is
   unit-untestable; this is the only proof it works.
2. **Offline `ollama pull` (F2).** Kill network mid-setup, confirm setup is
   non-fatal, prints the exact manual recovery command, and the chat tab shows
   "model not installed yet" rather than crashing.
3. **CUDA / non-arm64 upgrade notice (F5).** Run `./arailctl upgrade maximus`
   on a non-arm64 host (or stub `uname -m`) and confirm the honest "Apple-
   Silicon-only today" + AirLLM opt-in notice prints — and that AeroLLM weights
   are NOT auto-downloaded.
4. **F8 manual verification.** Since the label isn't rendered, QA must confirm
   the `backend_notice` field is present in the `/api/chat` SSE `final` payload
   (curl the stream) so the follow-up frontend work has correct data to bind to.
5. **Full-suite regression re-run.** The "-1 failing / +18 passing" delta is
   from the build log, not re-verified here. Run the complete suite and confirm
   no NEW failures and that the 17 new tests are included in the count.
6. **F11 reasoning gate (trust-critical, blocks ship per VISION).** Run the
   5-prompt reasoning set: maximus (Qwen2.5-7B deep) must beat minimalist
   (Llama-1B) ≥4/5. If it doesn't, the deep persona/quant is wrong and ship is
   blocked regardless of everything above.
7. **8 GB honest-path UX (F7).** On a <16 GB box, confirm the maximus warning
   actually fires and reads gracefully (no traceback, no jargon) — this is the
   arail "failure-mode grace" gate.
8. **Airgapped guard.** Confirm zero egress on the minimalist path under
   `LAB_MODE=airgapped` (Ollama localhost only; the `huggingface-cli` line in
   the upgrade notice is printed, never auto-run).
