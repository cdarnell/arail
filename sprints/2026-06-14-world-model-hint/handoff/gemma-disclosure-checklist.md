# G2 — "Built with Gemma" disclosure checklist (gate for the default-floor swap)

Making `qkz-project-aware-2b` (Gemma 2B) the **minimalist default** requires the Gemma license
disclosure, exactly parallel to the existing **Llama 3.2 Community License** exception already in the
repo (see `CLAUDE.md` "Llama disclosure exception" + `licenses/`). The default swap (`setup.sh`
`ARAIL_DEFAULT_GEMMA=1` path + the catalog row) MUST NOT be enabled by default until every box is ticked.

## Checklist — DONE in PR "Gemma disclosure" (this branch), except where noted
- [x] **Bundle the license texts in `licenses/`** (parallel to the two Llama files):
      - [x] `licenses/GEMMA-TERMS-OF-USE.txt` — required §3.1(4) notice + obligations + canonical URL.
            ⚠ Paste the VERBATIM full Terms from ai.google.dev/gemma/terms before PUBLIC distribution.
      - [x] `licenses/GEMMA-PROHIBITED-USE-POLICY.txt` — pointer + incorporation-by-reference note.
            ⚠ Paste verbatim before public distribution.
- [x] **"Built with Gemma" displayed** wherever the model is surfaced:
      - [x] `README.md` — staged "Built with Gemma" note in the model-strategy block.
      - [x] `src/arail/chat/models_catalog.yaml` — the `qkz-project-aware-2b` `description` (staged).
      - [x] `models/ai-eng/Modelfile.gemma` — SYSTEM prompt ends "Built with Gemma." (staged).
      - [x] `NOTICE` — §4 Gemma attribution + the verbatim §3.1(4) notice + `licenses/GEMMA-*` pointers.
      - [x] `CLAUDE.md` — "Gemma disclosure exception" section added.
- [x] **Model name / notice rule — RESOLVED (confirmed from the live Terms, 2026-06-16).**
      Gemma's Terms do **NOT** require "Gemma" in the distributed model name (unlike Llama). So
      `qkz-project-aware-2b` needs **no rename**. The required §3.1(4) notice text is bundled (NOTICE +
      the license file). Distribution obligations (Gemma Terms §3.1): provide recipients the Terms,
      include the notice, mark the modification, pass through the Prohibited Use Policy — all recorded.
- [ ] **Derivative attribution (NEEDS G1):** state the exact Gemma base `qkz-project-aware-2b` is built
      on (fine-tune/distill) in NOTICE §4 + `Modelfile.gemma` once the base is confirmed.
- [ ] **Verbatim full text (pre-public-release):** paste the full Gemma Terms + Prohibited Use Policy
      into the two `licenses/GEMMA-*.txt` files (currently faithful summaries + the canonical URLs).

## Then, to ARM the default swap (after G1 + this checklist are green)
1. Fill the real base into `models/ai-eng/Modelfile.gemma` (replace `__PLACEHOLDER_GEMMA_BASE__`) and
   confirm `ollama create qkz-project-aware-2b -f models/ai-eng/Modelfile.gemma` works.
2. Flip the catalog `qkz-project-aware-2b` `tier:` `optional` → `recommended` (and the install handle to
   the real one) in `models_catalog.yaml`.
3. Make it the setup default: either set `ARAIL_DEFAULT_GEMMA=1` as the default, or replace the
   `llama-ai-eng` default path — the gated block in `setup.sh` is already in place and is a **no-op
   until enabled**.

Until all of the above: the minimalist default remains **`llama-ai-eng`** (Llama-3.2-1B), unchanged.
