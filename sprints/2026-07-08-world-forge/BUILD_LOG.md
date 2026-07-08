# BUILD_LOG — 2026-07-08-world-forge

## WF-1 — the port (commit 1bb0a8b)
`src/arail/world_forge.py`: Python port of DaC's `forge-world.mts` (7-stage
pipeline, verbatim prompts/temps), `gate.ts` (3 laws), `provenance.ts` (model:
regex, honest rollup), `export-bundle.mts` sealer (6 sealed siblings +
manifest), `skill.ts` renderer (F1/F2 injection containment), and
`reconcile-world.mts`'s judge prompt. Framework-free, injectable router,
tolerant loose-JSON repair, cancellation, atomic reseal. 50 tests
(`test_world_forge_gate.py`, `_pipeline.py`, `_seal.py`).

## WF-2/3/5 — API layer (commit 5fcaaa3)
`src/arail/portal/world_routes.py` (new router, wiki_routes pattern):
Forge (202 + one-at-a-time lock + inference_slot + cancel), Terms editor
(gate→reseal→swap on every write), Curator review (seal-exempt `review.json`
sidecar). CSRF envelope on every write. 15 integration tests
(`test_world_forge_api.py`).

## WF-2/3/4 — UI layer (commit 8d53597)
Three-agent parallel build: `/worlds` page (catalog + forge hero + progress
+ preview), the Knowledge → World Terms editor (drawer, slug-picker,
provenance chips, Curator flags), and the world-first flow (welcome step 2,
dashboard mission framing + goal suggestions, Buddy goal-within-world
gearing). `docs/world-forge.md` corrected to the user's tier philosophy.

## Manual verification (real model, real portal, real mount)
- **Finding, not a defect**: the portal's default-configured model in this
  dev environment (MLX Qwen3-8B, "thinking" mode) never converges to JSON
  within any practical budget — confirmed at 400 AND 2000 max_tokens, the
  model reasons indefinitely and even confabulates the task. This is exactly
  the risk `docs/world-forge.md` already names ("reasoning models... stall
  the draft loop"). Not a pipeline bug: the forge correctly used whatever
  the router resolved to.
- **Real success**: pointed `forge_world` at Ollama's `llama-ai-eng` (the
  1B instruct model that's ARAIL's own documented default) via
  `OpenAICompatBackend` — forged "Indoor plants and their care" / 25 terms
  in ~44s. Gate passed, tier `model-asserted`, avg 2.12 edges/term.
  `snake-plant` categorized correctly with dense related edges to `pothos`,
  `peace-lily`, `dracaena`, `zz-plant`; a `cacti-and-succulents` category
  emerged naturally — the exact Snake-Plant-as-succulent case from the
  brief. Sealed, `verify_seal` true, mounted, `load_world_skill()` returned
  a working glossary.
- **Live browser verification**: `/worlds` renders and drives a real forge
  (progress panel, stage rows, live polling) against the portal's default
  router — confirmed the UI state machine is correct even when the model
  itself fails to converge (clean error state, no hang, no crash).
  Knowledge → World Terms rendered the real Horticulture world (47 terms,
  correct categories), opened the edit drawer, and a live save through the
  actual UI persisted to disk and re-verified its seal. Reverted the test
  edit before commit (Horticulture is a shipped world).

## Follow-up (tracked, not blocking)
- Consider a "prefer an instruct-tuned local model for the Forge" default
  or an explicit backend picker on the Forge form, since a router configured
  for a large reasoning model will silently fail to draft. Out of scope for
  this sprint (the approved plan specifies "uses the default local router");
  flagging for a follow-up decision.
- Minor cosmetic: the World Terms tier badge briefly flashes "mixed · 0
  edited / 0 dreamed" for one frame before `S.data.tier` populates on load.
  Harmless (self-corrects immediately); not worth blocking on.
