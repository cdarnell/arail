# Vision: Platform Foundation — health/metrics/OpenAPI/Skills-into-Agents

**Date:** 2026-05-15
**Product:** arail
**Wedge size:** one sprint (tight)

## User

Two concrete personas, in priority order:

1. **The blueprint forker** — a developer (e.g. the PeanutLab example in
   `examples/peanut_farmer/`) who has cloned ARAIL, renamed it, and is
   now wiring monitoring or a thin status page for their lab. They
   `curl http://127.0.0.1:8080/api/system/health` expecting a stable,
   tier-correct shape they can script against. Today they get
   `services.opencode`/`marimo`/`neo4j` keys even on `min`, which means
   their min-tier dashboards either render bogus rows or have to filter
   client-side from undocumented knowledge.

2. **The lab operator (the user themselves, on their own machine)** —
   running `min` tier locally, occasionally hitting OOM (per workspace
   memory), and wanting to answer "is the lab healthy? how hot is it
   running?" without opening Admin (which is `max`-only). Today: health
   exists but is noisy with optional services; metrics doesn't exist.

The Skills→Agents fold targets the same operator while they're using
the min-tier portal — one Agents tab is the mental model already
(`docs/agents.md`), the separate Skills link is a vestige.

## Problem

The `/api/*` surface is the *platform contract* that survives every
rename. Right now four specific inconsistencies bite:

1. **`/api/system/health` leaks max-tier service rows to min-tier
   callers** (QA INFO #1 from opencode sprint). A min forker scripting
   against health sees `opencode: {alive: false}` and is misled into
   thinking opencode is supposed to be there. Happens on every health
   call, every tier-min install.
2. **No `/api/system/metrics` endpoint at all.** The operator who wants
   to graph RAM/disk/active-model over time has no scrape target. They
   shell out to `psutil` themselves or open Admin (max-only).
3. **OpenAPI drift across `/api/*`.** Some endpoints return
   `{ok: false, reason: ...}`, some return `{"error": "..."}`, some
   bare 500. Status codes are inconsistent (`/api/opencode/start` uses
   409 for not-ready; other readiness checks use 503 or 200+ok:false).
   Naming is mostly snake_case but `url_internal` vs `urlInternal`
   drift exists. Forkers have to read source to write a client.
4. **Skills is a separate nav entry that loads a panel the user
   already thinks of as "what my agents know."** Approved plan
   (Sprint 3 of the opencode roadmap) collapses it; pending.

These four are coupled because (a) Skills-fold reshapes `/api/agents`
and `/api/skills`, and if the OpenAPI conventions aren't fixed *first*
the new surface ships inconsistent and we re-cut it later, and
(b) `/api/system/health` and `/api/system/metrics` are the canonical
test cases for the conventions.

## Win condition

Three concrete, `curl`-observable outcomes, pre-committed:

1. `LAB_TIER=min curl -s :8080/api/system/health | jq '.services | keys'`
   returns **only** the services actually available on `min` — no
   `marimo`, `open-notebook`, `neo4j`, `opencode`. Same call on `max`
   returns the full set. Verified in CI.
2. `curl -s :8080/api/system/metrics` returns 200 with a documented
   shape (see Wedge for the shape choice), works offline, requires no
   external scraper, contains at minimum: `ram_used_bytes`,
   `disk_free_bytes`, `chat_model_loaded` (0/1),
   `process_uptime_seconds`, `active_provider` (label).
3. New `/api/*` endpoints added in this sprint conform to a documented
   convention sheet (`docs/api-conventions.md`, one page) covering:
   error envelope, status codes for not-ready / not-installed /
   tier-gated, snake_case keys. Plus a redirect `GET /skills → /agents?view=skills`
   returning 302, and `/agents?view=skills` rendering the Skills panel
   in-line.

Falsifiable signal of failure: if the forker (PeanutLab-style fork)
still has to read `app.py` source to know what `/api/system/health`
returns on their tier, we failed.

## Wedge

Single sprint, four scoped subsections, each independently
revertable. The wedge is **convention-first, audit-last**:

1. **Health tier-gating** — add a `tier` field to each service entry
   in the registry and filter response by `_visible_surfaces()`. ~20
   lines + tests.
2. **`/api/system/metrics` (JSON, not Prometheus — see Tension #2).**
   Single new handler returning a flat JSON object of gauges +
   counters with documented keys. ~60 lines. Prometheus text format
   is a *future option* gated behind `?format=prometheus` only if a
   user asks; default JSON keeps us airgapped-pure and dependency-free.
3. **OpenAPI consistency — convention-set only, applied to (a) the
   two endpoints touched above and (b) the new/touched `/api/agents`
   endpoints from item 4.** No whole-codebase audit. We write
   `docs/api-conventions.md` and lint *new* surface only. Existing
   drift is captured as a follow-up backlog file; not fixed here.
4. **Skills folded into Agents** — execute the approved plan
   (Sprint 3 of opencode roadmap). Redirect `/skills`, segment
   control inside `/agents`, partial extraction. The plan is
   already designed; this is execution.

## Disconfirming evidence

Pre-committed: shelve or roll back if any of these hit during build/QA:

- The architect cannot define the JSON metrics shape in
  ARCHITECTURE.md without a follow-on dependency (psutil already
  optional; if we end up needing `prometheus_client`, we have picked
  the wrong format and should pause).
- `/api/system/health` tier-gating breaks any existing portal page
  that consumes the endpoint (Admin, Dashboard). Indicates the
  service registry was load-bearing in undocumented ways and we
  should split the sprint.
- Skills-fold execution requires more than the ~10 file changes
  documented in the approved plan. Indicates plan staleness — defer
  Skills-fold to its own sprint and ship items 1–3 only.
- After ship: forker (or the user simulating one) still asks
  "what's in `/api/system/health` on min?" — meaning the convention
  doc didn't actually land as a contract.

## Displacement

This sprint **replaces** ad-hoc handler-by-handler error shaping.
After it ships, every new `/api/*` endpoint must conform to
`docs/api-conventions.md` or get pushed back in review. That is the
"foundation" — not new functionality but a *constraint* that future
work inherits.

What gets less attention while this runs:
- **aeroLLM HTTP bindings progress** (still aerollm-repo work; no
  arail-side capacity here). Acceptable — Compute Source pivot
  already absorbs aeroLLM when it lands.
- **qukaizen distillation work.** Same — not arail.
- Within arail: paperagents landing surface (frozen per memory) and
  any new agent UX beyond Skills-fold. Explicitly deferred.

If we said no to this sprint, accretion continues: every new `/api/*`
endpoint invents its own envelope, and the eventual cleanup is
proportionally larger. Saying yes now is cheaper than saying yes in
six sprints.

## Tensions resolved

1. **Blueprint vs product.** `/api/system/health` is part of the
   *stable platform contract* — it does NOT rebrand. The display
   name (LAB_NAME) is for HTML; the API surface is identifier-stable
   so forker-written clients survive renames. (`arail/CLAUDE.md`:
   "internal package name stays `arail`.")
2. **Prometheus vs JSON.** **JSON-first.** Airgapped default means
   no remote scraper anyway; adding `prometheus_client` is a new
   dep for a feature nobody locally asked for. JSON is greppable,
   `jq`-able, zero-dep. Prometheus text via `?format=prometheus`
   is reserved as a future no-dep addition (hand-rolled formatter,
   ~30 lines) only if a real forker asks.
3. **OpenAPI consistency scope.** **Convention-set + new endpoints
   only.** A whole-codebase audit is a quarter, not a sprint, and
   not the foundation — the foundation is the *rule*, not the
   exhaustive application. Backlog file captures known drift.
4. **Skills as Agents.** **Distinct concepts collapsed in UI, kept
   distinct in code.** The approved plan keeps `/api/skills/*`
   endpoints and `lab/pkb/skills/` layout intact; only nav + page
   structure changes. Skills remain a concept (a body of knowledge
   attached to an agent); the *Skills tab* disappears as a separate
   nav entry. This matches the user's mental model ("what my agents
   know") without breaking the loader contract.

## Recommended next step

**Proceed to /architect with this as the spec.**

Justification: scope is bounded (one sprint, four subsections, each
revertable), conventions are decidable in design phase, Skills-fold
has a pre-approved plan ready to lift. Architect should partition
ARCHITECTURE.md into four subsections per SPRINT.md note, define
`docs/api-conventions.md` once, and confirm the JSON metrics shape
before builder starts. If architect surfaces that any of the four
items cannot be revertable-independently, split: items 1–3 form
"platform-foundation-api"; item 4 splits to "skills-into-agents"
sprint.
