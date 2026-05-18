# Vision: Provider-aware chat dropdown

**Date:** 2026-05-18
**Product:** arail
**Wedge size:** one sprint

## User

A returning ARAIL operator mid-session, already past setup, who has just saved an OpenRouter or Anthropic key in the ⚙ Manage providers modal and clicked the Compute Source pivot from "My Machine" to "Claude" (or OpenRouter). They want to send the next prompt to opus-4-7 or a frontier model — not to whatever `qwen2.5:7b` happens to still be selected in the dropdown. The moment of contact is the second after the radio flips: their eyes go to the model selector to confirm what they're about to talk to.

## Problem

The dropdown lies. `/api/chat/models` ignores the active provider and reads the local Ollama catalog (`app.py:5775-6089`); the radio has no change listener (`chat.legacy.html:957-959`). The experienced failure is silent-wrong: the user sends a prompt believing they hit Claude, but the selected model id (`qwen2.5:7b`) doesn't exist on Anthropic — they get a confused 404 or, worse, the request quietly routes somewhere unexpected. This directly violates `project_pluggable_provider_thesis`: pluggability that only works at the routing layer but not the UI layer is not pluggability, it's a leak.

## Win condition

1. Flipping Compute Source to any of the 6 providers repopulates the dropdown with that provider's models in under 800ms (p95, local network to provider list cache).
2. Sending a prompt under any active provider hits a model that exists on that provider — zero "model not found" errors caused by stale dropdown state in a 10-flip manual test.
3. Empty-key state shows "Save a key in ⚙ Manage providers" CTA (not silent empty) — verified for all 5 cloud providers.
4. Local-only behavior (no `?provider=`) is byte-identical to today in regression tests.

## Wedge

Add `?provider=` to `/api/chat/models`, wire the radio change listener, hardcode HF's curated list, ship empty-state CTA. Legacy template only. One sprint. Parallel to `ai-eng-v2.1` (local models) — together they complete the "local + external both honest in the dropdown" story the user framed today.

## Disconfirming evidence

Shelve or revisit if any of: (a) telemetry/self-report shows <10% of sessions ever change Compute Source over 2 weeks post-ship — the bug is real but nobody hits it; (b) OpenRouter's 200+ model list makes the dropdown a usability disaster requiring a search UI we didn't budget; (c) the HF curated list collects >2 maintenance issues in 30 days (staleness debt outweighs benefit) — pivot to a search-only HF flow.

## Displacement

Pushes out: finishing `chat.html` (already parked, not blocked); per-provider cost ceilings; auto-selecting a sensible default model on provider switch; adding Cohere/Mistral/Google/Together. None of these are blocked by this sprint — each is an additive layer on top of an honest dropdown.

## ARAIL gating flags for the architect

- **Security:** `/api/chat/models?provider=` MUST refuse cloud providers when `LAB_MODE=airgapped` — same posture as save/test/models endpoints. Test this.
- **Onboarding clarity:** the empty-key state is a teaching moment per `project_arail_educational_disclosure` — CTA should link directly into the Manage Providers modal, not just describe it.
- **Failure-mode grace:** provider list fetch failure (network, 401, rate limit) must degrade to a labeled error row in the dropdown, not silent empty — per `project_warmup_overlay_invisible`, also show a loading state during refresh.

## Recommended next step

**Proceed** to `/architect` with this as the spec.

Risks for the architect:
1. The HF curated list is a maintenance surface — design it so updates are a single YAML edit, not code changes.
2. Provider list caching: cache TTL must balance staleness (user just saved a key, needs fresh list) against hammering provider APIs on every radio flip.
3. Race condition: rapid radio flips during in-flight `loadModels()` must not leave the dropdown showing provider A's models while the radio reads provider B.
