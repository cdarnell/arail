# Vision: Local-inference knowledge tools — per-term regeneration as the wedge

**Date:** 2026-07-09
**Product:** arail
**Wedge size:** one sprint

## User
A minimalist-tier arail operator — call her the "hobby world-keeper": someone
who forged or fetched a World glossary (say a 50-term "Home Espresso" or "Norse
Mythology" world) on a 16 GB Mac running the default `llama-ai-eng` (1B) model.
She is browsing Knowledge → World Terms, lands on a term whose example is thin,
generic, or was flagged by the Curator ("the model was terse"), and wants a
better one **right now** — not a whole-world overnight growth pass, not a manual
rewrite from a blank box. She has no cloud key and expects the lab to work
airgapped.

## Problem
The glossary has three existing local-inference surfaces, but there is a hole
between them for the single most common micro-interaction:

- `POST /api/worlds/terms/draft` drafts a **brand-new** term from a name. It
  cannot improve an existing term — it ignores the current definition/example.
- `POST /api/worlds/grow` and the overnight `world_growth_loop` do
  reconcile-and-propose across the **whole world**, batched (GROW_* limits),
  reversibly. Too heavy and too indirect when the user wants to fix one field.
- `POST /api/worlds/review` (Curator) **flags** a stale/thin term but offers no
  one-click way to act on the flag — the user is dumped back to a manual edit
  box.

So today, fixing one weak example on one term means either retyping it by hand
or triggering a world-wide pass and hoping the right term gets touched. The
forge preview UI already promises the escape hatch — line 360 literally tells
users to "edit them in the Knowledge tab or **Regenerate**" — but the
Regenerate verb has no implementation behind it. That is the pain: a named,
advertised affordance that doesn't exist, sitting on top of the exact
local-inference substrate that is arail's whole differentiator.

## Win condition
Pre-committed, measurable thresholds:

1. From a term row in World Terms, the user clicks "Regenerate example" (or
   definition/short) and gets a **candidate shown inline, unpersisted**, in
   under 8 s on `llama-ai-eng` (1B) for a mid-size world, mirroring the existing
   draft-then-review UX. Accept persists via the existing PUT reseal path;
   dismiss changes nothing.
2. The regenerated field respects existing `MAX_SHORT/DEFINITION/EXAMPLE` caps
   and carries honest provenance: accepting a model regen tags
   `source = _source_tag_from_model(...)` (model-asserted), and the world's
   provenance tier rolls up correctly — never silently laundering a hand-tier
   world into a dreamed one or vice versa.
3. Dogfood signal: on one real forged world, Charles regenerates ≥5 examples in
   one sitting and keeps ≥3 of them (accept, not dismiss). If he dismisses
   nearly everything, the 1B output isn't worth the click.

## Wedge
One new endpoint, `POST /api/worlds/terms/{slug}/regen`, that takes a `field`
(`example` | `definition` | `short`) and returns an **unpersisted** candidate —
structurally a sibling of `api_term_draft`, but the prompt is conditioned on the
term's *existing* fields plus the World subject ("here is the current example;
write a better, more concrete one"). It reuses, verbatim, the machinery already
in this file: `ModelRouter(billing_source="agent")`, `scheduler.inference_slot`,
`wf.loose_json`, the `MAX_*` caps, `wf._source_tag_from_model`, and the existing
PUT `/api/worlds/terms/{slug}` accept-and-reseal path. Client side: one
"Regenerate" button per editable field in `world-terms.js`, modeled on the
existing "Draft with model" button (lines 512–539), showing the candidate for
accept/dismiss. No new persistence format, no new provenance system, no
scheduler changes. Runs fully airgapped on the default 1B model.

## Disconfirming evidence
Pre-committed kill signals:

- **Quality floor:** if the dogfood pass yields <3/5 kept regens (win condition
  3 fails), the 1B can't do targeted field improvement well enough — shelve the
  per-field regen and fold the effort back into the batched `grow` path, which
  can afford the deep/7B or a cloud brain.
- **Latency floor:** if p50 > 8 s on a mid world blocks the single inference
  slot and makes the glossary feel frozen during chat, reject the synchronous
  design.
- **Redundancy:** if in practice users reach for whole-world `grow` anyway
  (regen click-through stays near zero after two weeks of it being present),
  the micro-interaction wasn't the real need — stop, don't build the adjacent
  ideas below.

## Displacement
arail is one of three QuKaiZen products; aerollm (the frontier MoE/GLM-5.2 work)
and aerollm-distill are the other draws on the same week. Saying yes here means
a sprint of arail portal/knowledge time that is **not** spent on aerollm's E1.b
qwen3_moe port or GA blockers. Within arail itself, it displaces polish on the
Curator `review`→action loop and the `grow` engine — though the wedge is
deliberately chosen to be the cheapest possible down payment on exactly that
Curator-flag→fix gap, so the displacement is partly an investment in it. It does
**not** displace the default-model/licensing work (Gemma floor), which is on a
separate track.

## Adjacent local-inference-in-docs ideas (explore only if the wedge earns it)
Ranked; each reuses the same substrate, none should be built before the wedge
proves the micro-interaction has pull:

1. **Curator-flag → one-click Regenerate.** Wire the existing `review.json`
   flags directly to the regen endpoint so a flagged term shows a "Fix this"
   button. Highest-leverage follow-on: it closes the review loop that currently
   dead-ends at a flag. Cheap once the wedge exists.
2. **Auto-link on add.** When a term is added/regenerated, run the *related*
   half of `api_term_draft` (already implemented — the roster-slug prompt) to
   suggest edges into the existing graph, tightening the closed-sourced-graph
   gate the reseal already enforces. Mostly a re-wiring of existing code.
3. **Local QA/search over the glossary.** A "ask this world" box that retrieves
   relevant terms (LanceDB is already in-stack) and answers locally with
   citations back to term slugs. Bigger — its own vision, not a rider on this
   one.

Drift detection (stale definition vs. related terms) is intentionally *not*
recommended: it overlaps the Curator `reconcile_terms` pass that already exists,
and would be a parallel system rather than an extension.

## Recommended next step
**Proceed to `/architect`** with the wedge as the spec: the single
`POST /api/worlds/terms/{slug}/regen` unpersisted-candidate endpoint plus a
per-field Regenerate button, reusing the draft/PUT/provenance machinery already
in `world_routes.py`. Scope the architect's attention to two risks: (1) prompt
conditioning that reliably beats the current field on a 1B without hallucinating
new claims, and (2) provenance-tier correctness when a model regen is accepted
onto a hand-edited term. Defer all adjacent ideas until the dogfood accept-rate
gate (≥3/5) is met.
