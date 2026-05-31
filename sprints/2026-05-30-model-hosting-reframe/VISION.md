# Vision: Model-Hosting Strategy Reframe

**Date:** 2026-05-30
**Product:** arail
**Wedge size:** one sprint

> Scope note: the three decisions below were made WITH the user. The visionary's
> job here was to pressure-test the win condition and wedge and to flag the
> honesty/positioning risks for the architect — not to re-open the choices. The
> exact 20–30B deep-mode model ID is a deliberate TODO placeholder; this doc does
> not pick one, and the architect must not either.

## User

Two concrete personas, both real today:

1. **The minimalist-tier cloner.** Someone who clones ARAIL on a 36 GB Apple
   Silicon machine, runs `./arailctl setup && ./arailctl start`, and wants the
   default assistant to "just work" without a 5 GB qwen2.5:7b fallback pull or a
   probe-then-fallback dance that sometimes lands them on the wrong base. They
   never read the Modelfile; they judge ARAIL by whether the first chat reply is
   fast and competent.

2. **The maximus-tier operator.** Same hardware class. They upgraded to maximus
   expecting "frontier-scale local inference," clicked deep mode, and got AirLLM
   layer-streaming Llama-3.1-70B that pages itself to a crawl (or OOMs) on a 36 GB
   box. The advertised promise and the lived experience diverge. They want a deep
   model they can quick-download and that actually runs at usable speed locally.

## Problem

The actual pain, not the requested feature:

- **Deep mode over-promises against the hardware reality.** A 70B (let alone 405B)
  via AirLLM on a 36 GB machine is not a frontier bench — it is a demo that
  technically completes and practically frustrates. The current default
  (`AIRLLM_MODEL=meta-llama/Llama-3.1-70B`, `backends.py:988-989`) sets an
  expectation the machine cannot honor until MoE / a more memory-efficient method
  lands. 70B is the wrong default weight class for the target hardware *today*.

- **The ai-eng install path is fragile and leaks its scaffolding.** Setup probes
  `qukaizen/ai-eng:3b`, and on miss pulls a 5 GB qwen2.5:7b and builds from
  `Modelfile.preview` (`setup.sh:768-799`). That fallback is a second auto-download
  on an OOM-sensitive machine, it ships a 7B wearing a "3B" label, and the qwen
  lineage is advertised in the catalog, README, and Modelfile system prompt
  (`models_catalog.yaml:26,37,42-52`; `Modelfile.preview`). The brand the user
  wants — "3B Opus-distilled AI engineering model" — is not what setup actually
  delivers or describes.

## Win condition

Pre-committed, measurable thresholds:

1. **One auto-install, one model.** After `./arailctl setup` on a clean 36 GB
   machine, exactly one model auto-installs: ai-eng, via a single `ollama pull`
   of the baked tag. No second fallback pull occurs. Verified by setup log: one
   pull line, zero `qwen2.5:7b` pulls.
2. **Deep mode is downloadable and runnable.** Maximus deep mode points at a
   20–30B open model (TODO placeholder ID) that a maximus operator can
   quick-download on demand and run to first token in under, say, 60s on the
   reference machine without OOM. (Architect sets the exact latency/footprint bar
   in ARCHITECTURE.md; this is the order of magnitude.)
3. **Zero user-facing qwen mentions.** `grep -ri "qwen2.5" README.md CHANGELOG.md
   CLAUDE.md docs/ models_catalog.yaml` returns nothing tied to ai-eng's identity.
   The only surviving qwen reference is the unavoidable `FROM` line in the internal
   Modelfile. (Catalog rows for *standalone* Qwen models the user can browse stay —
   the rule is about ai-eng's lineage, not delisting the Qwen family.)
4. **No regression to airgapped default.** `LAB_MODE=airgapped` still blocks every
   cloud provider; deep-mode swap touches only the local backend default.

## Wedge

The smallest change that proves the value, shippable in one sprint, runs entirely
on the developer's own machine with no cloud account:

- Flip the deep-mode default in `backends.py` / `airllm_worker.py` from the 70B
  env default to a `TODO`-placeholder 20–30B model id, surfaced as a maximus
  quick-download (NOT a setup auto-install — confirmed: only ai-eng auto-installs
  today, deep models are pull-on-demand, so this preserves the constraint).
- Bake the LoRA into the `qukaizen/ai-eng:3b` Ollama tag so setup is a single
  `ollama pull` with no Modelfile-create step and no probe/fallback ladder.
  Collapse `setup.sh:768-799` to one pull. Keep `Modelfile.production` only as the
  internal build recipe.
- Strip qwen lineage from all user-facing strings (catalog description/family for
  ai-eng, README, CHANGELOG, CLAUDE.md, docs, Modelfile system prompt). Rebrand to
  "3B Opus-distilled AI engineering model."

This is a config + copy reframe, not new infrastructure — correctly one sprint.

## Disconfirming evidence

Pre-committed failure signals:

- **ai-eng tag not actually published.** If `ollama pull qukaizen/ai-eng:3b` 404s
  at sprint time, the single-pull wedge is built on a tag that does not exist. If
  the tag is not live before BUILD, we DEFER the setup-collapse half of the sprint
  rather than ship a `pull` that strands clean-machine users with no assistant.
  (The architect must verify tag availability as a gate.)
- **The 20–30B deep model still OOMs.** If the placeholder weight class, once the
  user picks it, cannot reach first token without paging on the reference 36 GB
  machine, the deep-mode reframe has only moved the over-promise from 70B to 30B.
  Signal: a deep-mode smoke run that OOMs or exceeds the latency bar twice → the
  weight class is still wrong, escalate back to visionary.
- **The honesty cost is too high.** If hiding the qwen lineage draws a credible
  attribution/licensing objection (see notes), the branding line is not worth a
  license violation → revert the "hide" half, keep the single-pull half.

## Displacement

QuKaiZen has three products; saying yes here is time not spent elsewhere:

- **aerollm** loses a sprint of attention. Notably, retiring the 70B AirLLM default
  de-emphasizes the AirLLM-vs-AeroLLM bakeoff that `benchmark_models` and the
  AeroLLM CUDA-backend roadmap lean on. The deep-mode model becomes the new
  AeroLLM proving target — make sure that hand-off is intentional, not accidental.
- Within arail, this pulls ahead of **maximus.plan Phase 1** (HF download + license
  gate + full-load via AeroLLM) and the **Chat Studio M2 loader strip**. Both
  assume a deep-model story; settling the weight class first de-risks them, so the
  displacement is more reordering than loss — but it IS a reorder, state it openly.
- "Nothing gets displaced" is not true here: the AirLLM 70B path is load-bearing
  for the current frontier-bench narrative, and removing it as the default forces
  the maximus tier copy to be rewritten.

## Notes for the architect (do NOT resolve in this doc)

1. **Is hiding the qwen lineage honest/defensible?** Qwen2.5 ships under the Qwen
   license (and qwen2.5:3b/7b-class weights have attribution expectations). MIT on
   ARAIL's own code does not override the base model's license. "3B Opus-distilled"
   is a defensible *description of the distillation product* IF a qwen base is still
   FROM-referenced and attributed somewhere license-compliant (the Modelfile, a
   THIRD_PARTY/ATTRIBUTION file, or model card on the Ollama tag). Stripping qwen
   from *marketing copy* is normal; stripping it from *required attribution* is a
   license risk. Architect must locate the line between "not advertised" and "not
   attributed" and ensure the latter never happens. Confirm the exact Qwen2.5
   license terms for the chosen base before BUILD.

2. **Does a 20–30B "deep mode" still deliver the frontier-bench promise?** Maximus
   currently advertises "Frontier-scale local inference, full bench" (README:64).
   A 20–30B is decidedly not frontier-scale by 2026 standards. Either the tier copy
   must be honestly rewritten (e.g., "the heaviest model that runs *well* locally,
   with cloud frontier models one click away via Compute Source") or we are quietly
   downgrading the tier while keeping the old promise. Architect must decide the
   honest framing — the visionary flags that the current README promise and a 30B
   default are in tension and must not both stand.

## Recommended next step

**PROCEED to /architect**, with two hard gates.

Design seed for the architect: This sprint reframes ARAIL's local model story
around hardware honesty. Collapse ai-eng setup to a single `ollama pull
qukaizen/ai-eng:3b` (LoRA baked into the tag; no probe/fallback; `Modelfile.production`
becomes the internal build recipe only), retire the AirLLM 70B/405B deep-mode
default in favor of a TODO-placeholder 20–30B open model offered as a maximus
quick-download (not a setup auto-install), and strip the qwen2.5 lineage from all
user-facing surfaces while preserving any license-required attribution in
non-marketing locations. The two gates the architect owns: (a) verify the
`qukaizen/ai-eng:3b` tag is actually published before committing to the single-pull
path, and defer that half if not; (b) resolve the two flagged tensions — qwen
attribution vs. license, and whether a 30B deep mode requires rewriting the maximus
"frontier-scale" promise — before any code is written. airgapped default and the
single-auto-install constraint are invariants, not negotiable.
