# G2 — "Built with Gemma" disclosure checklist (gate for the default-floor swap)

Making `qkz-project-aware-2b` (Gemma 2B) the **minimalist default** requires the Gemma license
disclosure, exactly parallel to the existing **Llama 3.2 Community License** exception already in the
repo (see `CLAUDE.md` "Llama disclosure exception" + `licenses/`). The default swap (`setup.sh`
`ARAIL_DEFAULT_GEMMA=1` path + the catalog row) MUST NOT be enabled by default until every box is ticked.

## Checklist
- [ ] **Bundle the license texts in `licenses/`** (parallel to the two Llama files):
      - [ ] `licenses/gemma-terms-of-use.md` — the Gemma Terms of Use (verbatim from ai.google.dev/gemma/terms).
      - [ ] `licenses/gemma-prohibited-use-policy.md` — the Gemma Prohibited Use Policy.
- [ ] **"Built with Gemma" displayed** wherever the model is surfaced:
      - [ ] `README.md` (the model/tier section).
      - [ ] `src/arail/chat/models_catalog.yaml` — the `qkz-project-aware-2b` `description` (already staged with "Built with Gemma").
      - [ ] `models/ai-eng/Modelfile.gemma` — the SYSTEM prompt ends with "Built with Gemma." (already staged).
      - [ ] `NOTICE` — add the Gemma attribution + a pointer to `licenses/gemma-*`.
- [ ] **Model name / notice rule — CONFIRM FROM THE LIVE TERMS (the one open item).**
      Llama requires the name to begin with "Llama" + "Built with Llama". Gemma's Terms have their own
      requirement (include the Terms + the use restrictions + a Gemma notice on distribution). Pin the
      EXACT current requirement from ai.google.dev/gemma/terms before shipping:
      - [ ] Does Gemma require "Gemma" in the **distributed model name**? (If so, rename
            `qkz-project-aware-2b` accordingly, and update the catalog `id` + `setup.sh` + `Modelfile.gemma`
            + the DaC `model.json` `recommended.id` to match.)
      - [ ] Include the required "Gemma is provided under and subject to the Gemma Terms of Use" notice
            text wherever the Terms require it.
- [ ] **Derivative attribution:** if `qkz-project-aware-2b` is a fine-tune/distill of a Gemma base,
      state the base model + that it's a modified version, per the Terms.

## Then, to ARM the default swap (after G1 + this checklist are green)
1. Fill the real base into `models/ai-eng/Modelfile.gemma` (replace `__PLACEHOLDER_GEMMA_BASE__`) and
   confirm `ollama create qkz-project-aware-2b -f models/ai-eng/Modelfile.gemma` works.
2. Flip the catalog `qkz-project-aware-2b` `tier:` `optional` → `recommended` (and the install handle to
   the real one) in `models_catalog.yaml`.
3. Make it the setup default: either set `ARAIL_DEFAULT_GEMMA=1` as the default, or replace the
   `llama-ai-eng` default path — the gated block in `setup.sh` is already in place and is a **no-op
   until enabled**.

Until all of the above: the minimalist default remains **`llama-ai-eng`** (Llama-3.2-1B), unchanged.
