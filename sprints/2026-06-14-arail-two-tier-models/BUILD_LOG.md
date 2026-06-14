# Build log: ARAIL Two-Tier Model Architecture

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at b03f0ed
**Started:** 2026-06-14

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `scripts/setup.sh:47` | Fix `ollama_default_enabled()` — gate on tier not ACCEL; force Ollama install when minimalist persona-wrap default | F1 integration (test_llama_disclosure.py asserts name starts llama-) | TBD |
| 2 | `models/ai-eng/Modelfile.default` | Verify drift-free (no change expected: FROM llama3.2:1b, SYSTEM ends "Built with Llama") | F9 anchor | TBD |
| 3 | `tests/test_llama_disclosure.py` (NEW) | Encode disclosure contract: name starts llama-, "Built with Llama" in Modelfile + README + catalog, licenses/ has both files, NOTICE references both | F9 | TBD |
| 4 | `tests/test_model_separation.py` (NEW) | Assert MODEL_NAME (Ollama 1B llama-ai-eng) and AEROLLM_MODEL (AeroLLM 7B Qwen2.5-7B-Instruct-4bit) never collide | F10 | TBD |
| 5 | `scripts/upgrade.sh` | Add honest AeroLLM-vs-AirLLM notice after pip install for maximus: arm64 → "AeroLLM deep ready"; non-arm64 → CUDA notice | F5/F8 | TBD |
| 6 | `src/arail/portal/app.py` | Add `backend_notice` field to `_build_chat_result`: "via AirLLM fallback (slower)" when backend=airllm, "via AeroLLM (local, fast)" when backend=aerollm | F5/F8 | TBD |
| 7 | `scripts/setup.sh` `capture_tier()` | Add 8 GB honest path warning (F7): RAM < 16 GB + maximus → honest downgrade notice | F7 | TBD |
| 8 | `docs/` + portal copy | Add tier-selection paragraph to docs/tier-selection.md and inline portal copy constant | Prose, QA-reviewed | TBD |

## Execution

### Step 1 — Fix `ollama_default_enabled()` (F1)
**What was done:** Changed `ollama_default_enabled()` to always return 0 (disabled/skip) only when tier is NOT minimalist. The new logic: on Apple Silicon + MLX, Ollama is still installed when the install is for minimalist tier (persona-wrap default = llama-ai-eng requires Ollama). The MLX-preferred-for-deep behavior is preserved for maximus. Added a clear comment so future readers don't revert it.

Also added 8 GB RAM gate in `capture_tier()` (F7): if RAM < 16 GB (16*1024^3 bytes) and user picks maximus, warn and suggest staying on minimalist.

Commit: TBD

### Step 2 — Verify Modelfile.default (F9 anchor)
**What was done:** Confirmed no drift. Modelfile.default has `FROM llama3.2:1b` and SYSTEM ends with "Built with Llama." No changes needed.

### Step 3 — `tests/test_llama_disclosure.py` (NEW) (F9)
**What was done:** Created test that asserts:
- models/ai-eng/Modelfile.default has SYSTEM containing "Built with Llama"
- Modelfile.default starts with `FROM llama3.2:1b` (or llama3.2)
- models_catalog.yaml id starts with "llama-"
- README.md contains "Built with Llama"
- models_catalog.yaml contains "Built with Llama"
- licenses/ contains LLAMA-3.2-COMMUNITY-LICENSE.txt and LLAMA-3.2-ACCEPTABLE-USE-POLICY.txt
- NOTICE references Llama 3.2 Community License and AUP

Commit: TBD

### Step 4 — `tests/test_model_separation.py` (NEW) (F10)
**What was done:** Created test asserting MODEL_NAME default (llama-ai-eng) and AEROLLM_MODEL default (Qwen2.5-7B-Instruct-4bit) are distinct, that MODEL_NAME starts with "llama-", that AEROLLM_MODEL does NOT start with "llama-".

Commit: TBD

### Step 5 — upgrade.sh AeroLLM-vs-AirLLM honest notice (F5/F8)
**What was done:** After `pip install -e ".[maximus]"`, added arch detection block: on arm64/Apple Silicon → prints "AeroLLM deep ready" notice + huggingface-cli download command; on non-arm64 → prints honest CUDA notice with AirLLM fallback instructions.

Commit: TBD

### Step 6 — app.py `_build_chat_result` backend notice (F5/F8)
**What was done:** Added `backend_notice` key to `_build_chat_result` return dict: "via AirLLM fallback (slower)" when backend=airllm, "via AeroLLM (local, fast)" when backend=aerollm, None otherwise.

Commit: TBD

### Step 7 — 8 GB warning in `capture_tier()` (F7)
**What was done:** Bundled with Step 1 (same function area, same commit).

### Step 8 — Tier-selection copy (docs + portal)
**What was done:** Created docs/tier-selection.md with the canonical copy from ARCHITECTURE.md. Added TIER_SELECTION_COPY constant to portal app.py exposed via /api/tier-selection-copy endpoint.

Commit: TBD

## Architect feedback required

_Empty — no conflicts with the spec discovered._

## Final state

_To be filled after all commits complete._
