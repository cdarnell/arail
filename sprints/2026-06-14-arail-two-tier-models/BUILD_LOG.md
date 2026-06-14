# Build log: ARAIL Two-Tier Model Architecture

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at b03f0ed
**Started:** 2026-06-14

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `scripts/setup.sh:47` | Fix `ollama_default_enabled()` — gate on tier not ACCEL; force Ollama install when minimalist persona-wrap default | F1 integration (test_llama_disclosure.py asserts name starts llama-) | 2756ff8 |
| 2 | `models/ai-eng/Modelfile.default` | Verify drift-free (no change expected: FROM llama3.2:1b, SYSTEM ends "Built with Llama") | F9 anchor | n/a |
| 3 | `tests/test_llama_disclosure.py` (NEW) | Encode disclosure contract: name starts llama-, "Built with Llama" in Modelfile + README + catalog, licenses/ has both files, NOTICE references both | F9 | c2d017e |
| 4 | `tests/test_model_separation.py` (NEW) | Assert MODEL_NAME (Ollama 1B llama-ai-eng) and AEROLLM_MODEL (AeroLLM 7B Qwen2.5-7B-Instruct-4bit) never collide | F10 | c2d017e |
| 5 | `scripts/upgrade.sh` | Add honest AeroLLM-vs-AirLLM notice after pip install for maximus: arm64 → "AeroLLM deep ready"; non-arm64 → CUDA notice | F5/F8 | 1a1a427 |
| 6 | `src/arail/portal/app.py` | Add `backend_notice` field to `_build_chat_result`: "via AirLLM fallback (slower)" when backend=airllm, "via AeroLLM (local, fast)" when backend=aerollm | F5/F8 | ffb7ae6 |
| 7 | `scripts/setup.sh` `capture_tier()` | Add 8 GB honest path warning (F7): RAM < 16 GB + maximus → honest downgrade notice | F7 | 2756ff8 |
| 8 | `docs/tier-selection.md` (NEW) | Tier-selection copy from ARCHITECTURE.md in canonical doc | Prose, QA-reviewed | 0e31896 |

## Execution

### Step 1 — Fix `ollama_default_enabled()` (F1)
Changed `ollama_default_enabled()` (setup.sh:47) to return true whenever
LAB_TIER=minimalist, regardless of ACCEL. On Apple Silicon the minimalist
default model (llama-ai-eng) is an Ollama persona-wrap; skipping Ollama on
M-series left it uninstalled (the F1 blocker). The "Apple Silicon prefers
MLX" behavior is preserved for the maximus tier only. Added a comment
warning future readers not to revert to ACCEL-gating.

Commit: 2756ff8

### Step 2 — Verify Modelfile.default (F9 anchor)
Confirmed no drift. `models/ai-eng/Modelfile.default` has `FROM llama3.2:1b`
and SYSTEM ends with "Built with Llama." No file changes needed.

### Step 3 — `tests/test_llama_disclosure.py` (NEW) (F9 stop-ship gate)
10-test file. Asserts: Modelfile.default FROM=llama3.2, SYSTEM contains
"Built with Llama", models_catalog.yaml default id starts "llama-" and
contains "Built with Llama", README.md contains "Built with Llama", NOTICE
references Llama 3.2 Community License and AUP, and licenses/ contains both
bundled files with non-trivial content. All 10 pass.

Commit: c2d017e

### Step 4 — `tests/test_model_separation.py` (NEW) (F10 regression)
7-test file. Asserts MODEL_NAME default (llama-ai-eng) and AEROLLM_MODEL
default (Qwen2.5-7B-Instruct-4bit) are distinct, that MODEL_NAME starts
"llama-", that AEROLLM_MODEL does not contain "llama", and that neither
model id is set to the other's value. All 7 pass.

Commit: c2d017e (same commit as Step 3)

### Step 5 — upgrade.sh honest AeroLLM-vs-AirLLM notice (F5/F8)
After pip install for maximus tier, added arch detection block at end of
upgrade.sh. arm64 → prints "AeroLLM (local, fast)" notice with step-by-step
build and weight-download instructions (huggingface-cli download command).
non-arm64 → honest "AeroLLM is Apple-Silicon-only today" notice with AirLLM
fallback instructions (ARAIL_INSTALL_AIRLLM=1, AIRLLM_MODEL) and cloud
Compute Source as alternative. Both notice paths mention the "via AirLLM
fallback (slower)" label users will see.

Commit: 1a1a427

### Step 6 — portal `_build_chat_result` backend notice (F5/F8)
Added `backend_notice` field to `_build_chat_result` return dict in
`src/arail/portal/app.py`. Mapping: backend=airllm → "via AirLLM fallback
(slower)"; backend=aerollm → "via AeroLLM (local, fast)"; other → None.
Field is included in every /api/chat SSE final event. Frontend can render
it as a badge or subtext under the chat reply. Verified app.py imports
cleanly after the change.

Commit: ffb7ae6

### Step 7 — 8 GB RAM warning in `capture_tier()` (F7)
Bundled with Step 1. Added 16 GB floor check (17179869184 bytes) in the
maximus RAM block of capture_tier(). RAM < 16 GB → warn with explicit message:
"maximus (7B-4bit ~4 GB resident) may cause swapping" + "the minimalist tier
(~1 GB) runs fine on 8 GB" + link to `./arailctl upgrade minimalist`.
The existing 48 GB informational notice is preserved for frontier-model users.

Commit: 2756ff8

### Step 8 — Tier-selection copy (docs)
Created `docs/tier-selection.md` with the canonical which-tier paragraph from
ARCHITECTURE.md, a quick-reference table (model, runtime, RAM floor, use-when),
switching commands, and model disclosure for both tiers (Llama 3.2 Community
License for minimalist, Apache 2.0 for maximus).

Commit: 0e31896

## Architect feedback required

_Empty — no conflicts with the spec discovered during build._

## Final state

**Commits made:** 5 (excluding BUILD_LOG skeleton)
- c66eaa2 — BUILD_LOG.md skeleton
- 2756ff8 — fix(setup): gate Ollama install on tier, not ACCEL — F1/F7
- c2d017e — test: F9 Llama disclosure gate + F10 model separation regression
- 1a1a427 — feat(upgrade): honest AeroLLM-vs-AirLLM notice on maximus upgrade — F5/F8
- ffb7ae6 — feat(portal): add backend_notice to chat result — F5/F8
- 0e31896 — docs: add tier-selection.md with canonical which-tier copy (Step 8)

**Tests added:** 17 new tests (10 disclosure + 7 model-separation), all passing.

**Test suite baseline (pre-sprint):** 41 failing, 2355 passing.
**Test suite with sprint changes:** 40 failing (-1 net), 2373 passing (+18 net).
The one pre-existing failure that disappeared is unrelated; no regressions introduced.

**Files changed:**
- `scripts/setup.sh` — ollama_default_enabled() gate (F1) + 16 GB RAM warning (F7)
- `scripts/upgrade.sh` — honest AeroLLM-vs-AirLLM notice block (F5/F8)
- `src/arail/portal/app.py` — backend_notice in _build_chat_result (F5/F8)
- `tests/test_llama_disclosure.py` (NEW) — 10 tests, F9 stop-ship gate
- `tests/test_model_separation.py` (NEW) — 7 tests, F10 regression
- `docs/tier-selection.md` (NEW) — canonical tier-selection copy

**Files verified, not changed:**
- `models/ai-eng/Modelfile.default` — FROM llama3.2:1b, SYSTEM ends "Built with Llama" (no drift)
- `src/arail/router/backends.py` — MODEL_NAME/AEROLLM_MODEL already separate (no changes needed beyond test coverage)
