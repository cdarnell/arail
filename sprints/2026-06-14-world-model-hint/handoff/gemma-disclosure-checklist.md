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

## G1 status — HELD (2026-06-18)

Investigated arming G1 with a Gemma 4 base. Findings:
- **There is no true Gemma-4 2B.** Ollama's Gemma 4 family is `gemma4:e2b`/`e4b`
  (edge), `12b`, `26b`, `31b`. `gemma4:2b` does not exist (`pull model manifest:
  file does not exist`). The smallest, `gemma4:e2b`, is **7.2 GB on disk** (2.3B
  *effective*) — ~4.5× the catalog's 1.6 GB "light floor / runs on 16 GB" framing.
- Decision (owner, 2026-06-18): **HOLD G1.** Do not wrap `gemma4:e2b` (footprint
  breaks the floor positioning) and do not fall back to Gemma 2/3 (owner wants
  Gemma 4 specifically). Keep `llama-ai-eng` as the minimalist default.
- Scaffolding stays dormant and untouched: `Modelfile.gemma` keeps
  `__PLACEHOLDER_GEMMA_BASE__`, the `ARAIL_DEFAULT_GEMMA=1` gate stays a no-op.
- **Revisit when** a true small (~1.5–2 GB) dense Gemma 4 ships, or if the owner
  accepts the heavier `gemma4:e2b` floor (then: catalog `size_gb` 1.6 → 7.2).
