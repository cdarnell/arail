# TEST_REPORT — 2026-07-08-world-forge

**Verdict: PASS.**

## Automated
500 passed / 2 failed (unrelated, pre-existing opencode tests — confirmed
identical failures on pristine `main`, tracked separately). Full run:
`tests/portal/`, `tests/test_world_forge_{gate,pipeline,seal,api}.py`,
`tests/test_world_{recolor,recolor_qa,identity_flip,switcher,buddy,face,
mount,loader}.py`, `tests/test_brand.py`.

New this sprint: 50 (gate/provenance/loose-json parity + pipeline w/
FakeRouter incl. 1B-garbage survival + sealer round-trip through ARAIL's
own verify_seal/check_compat/check_categories + adversarial SKILL.md
containment) + 15 (forge/terms/review API integration, CSRF, 409s,
edit→reseal→swap, auto-close on delete, hostile-field containment).

## Manual — real model, real portal
- Direct pipeline run against Ollama `llama-ai-eng`: 25-term "Indoor
  plants and their care" world forged in ~44s, gate ok, tier
  model-asserted, sealed + `verify_seal` true + mounted +
  `load_world_skill()` returned a working glossary. Snake Plant correctly
  categorized with dense, sensible related edges. Cleaned up before commit.
- Browser-driven `/worlds` page: forge flow UI verified live (form → real
  202 → progress panel with live stage/counter/elapsed polling → clean
  error state on a genuine model-convergence failure — no hang, no crash).
- Browser-driven Knowledge → World Terms: real mounted world (Horticulture,
  47 terms) rendered correctly by category; edit drawer opened with real
  field values; a live save persisted to disk and re-verified its seal.
  Reverted before commit (shipped world).
- Confirmed a genuine finding along the way (not a code defect): a
  "thinking"-mode local model configured in this dev environment cannot
  converge to structured JSON at any practical token budget — the exact
  risk the design doc names. Root-caused with a direct backend probe,
  not guessed at.

## Scope check against the plan
All six plan phases (WF-1 through WF-6) shipped. Non-goals honored: no
leveled-worlds axis, no promotion pipeline (Curator flags only), no
`tags[]` schema bump, no curriculum/reader assembly.
