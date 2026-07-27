# Vision: World of Debt Finance — the first wedge of a Personal Finance World

**Date:** 2026-07-26
**Product:** arail
**Wedge size:** one sprint
**Status:** revised post-architect-review — see companion ARCHITECTURE.md for the
technical resolution of every open item below; this revision corrects two
claims the original draft got wrong about ARAIL's own code (flagged in
review, verified directly against source — see ARCHITECTURE.md §2 and §6).

## User

The lab owner — or the friend/family member they hand a cloned ARAIL lab to,
per ARAIL's own fork-and-rename model — who already has a Credit Karma account
and checks it the way most people do: passively, to watch a score move, not to
act on it. Concretely: three open balances (a credit card at a punishing APR,
a personal loan, maybe a car loan), income that clears expenses most months
but not by much, and a real, specific question sitting unanswered — *"is there
a cheaper way to be carrying this debt than the way I'm carrying it right
now?"* She has never called a credit union. She has never opened a
balance-transfer offer past the teaser rate. She does not know what "closed
sourced graph" or "provenance tier" means and never should have to — she just
wants the lab to have opinions about her actual numbers.

This is not "someone who wants to invest better" and not "someone in a debt
crisis needing a hotline." It is the much larger, much less served middle: a
person maintaining finances competently enough to not be in trouble, who has
never had a free, private, always-on advisor whose only job is to look at
*her* debt and ask "could this be cheaper."

## Problem

Not the feature request ("build a World with two agents"). The actual pain:
**most people don't know how to act as their own financial advisor**, and the
gap is not information — CFPB rate tables and credit union sites are public —
it's *synthesis effort*. Comparing her card's real APR against ten
balance-transfer offers' actual terms (not the teaser), checking whether a
local credit union underwrites better than her bank, and doing the
breakeven math on a transfer fee versus the interest saved, is a research
project most people correctly judge isn't worth a Saturday for what might be a
0.5-point difference — so they don't do it, and they keep paying the
expensive rate by default, indefinitely, out of research fatigue rather than
lack of intelligence.

Compounding this: she already has the one artifact that would make this
research free — her Credit Karma data, sitting unused. Nothing today turns
"I have my numbers" into "here's a decision." Getting that synthesis to
happen automatically, continuously, and privately is the actual problem this
World would solve. Investing is explicitly not this problem yet — it doesn't
exist as a live option until cash flow turns positive, which is the operator's
own stated ordering and matches the persona: you don't optimize returns on
money you're simultaneously bleeding to a 24% card.

**A second, load-bearing problem surfaced during design review and belongs in
this document, not just the architecture:** ARAIL's own agent folders are
*designed* to be transparent — the shipped agent README states plainly that
everything under `lab/pkb/agents/` is "indexed by the wiki, browsable from
`/dac`, searchable via the unified search." That's the right default for
horticulture notes and research dreams. It is exactly the wrong default for a
household's actual debt figures, and this World is the first one where that
tension is load-bearing rather than theoretical (see Displacement, below, and
ARCHITECTURE.md §6 for how it's resolved). Getting this right here is part of
the problem this wedge exists to solve — not just for this World, but as the
precedent for every personal-data World that follows it.

## Win condition

Falsifiable, witnessable, pre-committed:

1. **One real, named, sourced comparison.** Within the sprint, on the
   operator's own machine, with his own real (or realistically-shaped
   stand-in) balances staged locally, the Debt Advisor or Consolidation
   Analyzer surfaces at least one concrete recommendation of the shape *"your
   current card is at X% APR; [named credit union / named issuer]'s
   balance-transfer product is at Y%, transfer fee Z% — breakeven in N
   months"* — with Y and Z sourced to an actual rate page (fetched via the
   generic scouting path, or hand-curated into the World's terms if fetch
   hasn't run yet), never a fabricated number, and with every stated number
   inserted by code from a structured field — not paraphrased by a local
   LLM — so a name or figure can never silently drift from what it's cited
   to (see ARCHITECTURE.md §7.5). If the agents can only produce generic
   advice ("consider a lower-interest card") with no named institution or
   real rate, the wedge has not proven anything and has not shipped.
2. **The lab treats it as a finding, not a fact, on a surface built for that
   sensitivity — not repurposed from a different one.** The recommendation's
   actual figures and named-institution comparisons land in a
   structurally-private file the PKB never walks and `/api/pkb/search` never
   returns (see ARCHITECTURE.md §6); a short, non-identifying pointer to it
   appears in the dashboard activity stream (which already lives outside the
   PKB tree, verified); and anything scouting actually fetches from a public
   rate page lands, as it does for every other World, in the `/dac`
   Compiled-KB review queue. This is a structural requirement, not a
   nice-to-have: it is how the product stays inside "helps you act as your
   own advisor" and out of "acts as a licensed advisor," which is a
   constraint on the product itself, independent of what ARAIL as software is
   permitted to do. It is *not* satisfied by writing analysis into
   `decisions.md` — design review found that file is (a) documented in this
   codebase as a human-authored, agent-*configuration* log, not an analysis
   channel, and (b) fully indexed and returned by the ungated
   `/api/pkb/search` endpoint regardless of any approval state. The original
   draft of this vision assumed `decisions.md` was a safe generic surface for
   this; it verifiably is not, and the architecture no longer uses it that
   way.
3. **Nothing sensitive lands anywhere the PKB walks, verified by
   construction, not just checked after the fact.** The operator can search
   the Knowledge Base / wiki for his own balance figures after this sprint
   and find nothing — not because a human remembered to grep for it once,
   but because the file the figures live in is never under `lab/pkb/` in the
   first place, the same structural property this design already relies on
   for the input staging file. A post-run grep of `decisions.md` and the
   wiki index is still run in QA as defense-in-depth, but the design does not
   depend on that check catching a mistake.
4. **It survives airgapped-by-default honestly.** Under the shipped default
   (`LAB_MODE=airgapped`), the World mounts, the agents run on locally-staged
   data, and the recommendation in (1) can still be produced from
   hand-curated/mounted World content alone — scouting-driven *live* rate
   updates are correctly inert until the operator opts into `hybrid` and
   approves consent per feed, and the UI/agent output must not imply
   otherwise. Whether scouting can do anything at all in `hybrid` mode
   depends on getting real URL sources into the *first three* positions of
   `spec.json`'s `knowledge_sources[]` array — a real upstream constraint of
   the sealing pipeline discovered in review (ARCHITECTURE.md §3.2) — so this
   condition is now an explicit authoring checklist item, not an assumption.

Pre-committed: if (1) cannot be demonstrated end-to-end with a real named
institution and a real number, the wedge has not shipped regardless of how
polished the World bundle or the agent prose is.

## Wedge

**v1 = seal a Personal-Finance World's first slice (World of Debt Finance) +
two thin PKB agents reading locally-staged data + zero new portal surface.**
Nothing in the World declare→gate→seal→mount pipeline or the
scouting/agenda-watch pipeline is domain-aware, and that part of the wedge
really is just content authorship — no code changes to `scouting.py` or
`agenda_watch.py`, verified directly against source. **Correcting the
original framing:** the two agents themselves are *not* pure content/config
authorship. ARAIL has no shared background-tick harness for non-builtin PKB
agents today — Buddy hand-rolls its own asyncio loop from scratch, and the
generic loader only calls `instance.start()` if the agent defines one. Debt
Advisor and Consolidation Analyzer each need their own modest, real tick-loop
implementation (state persistence, cooldown, a "nothing changed since last
run" no-op check) written the same way Buddy's was. Budget this as real
engineering, not configuration.

In scope:
- Author and seal a `debt-finance` World bundle: `spec.json` with categories
  (`debt-types`, `credit-products`, `institutions`, `strategies`,
  `terminology`), a closed and sourced `terms.json` (every term categorized,
  every `related[]` edge resolvable, every term's `source` a real citation —
  the gate's three laws reject anything else), and `knowledge_sources[]`
  naming real, concrete, fetchable pages, **with real URL-kind sources placed
  in the first three array positions** — the sealing pipeline's agenda
  derivation takes the first three `knowledge_sources` entries by raw array
  position regardless of kind, not "the first three fetchable ones," so
  ordering is load-bearing, not stylistic (verified against
  `dac_world/seal.py`; see ARCHITECTURE.md §3.2 for the authoring rule and
  the seal-time check that catches a misordering).
- Derive `agenda.json`'s `watches[]` from those same `knowledge_sources` — the
  existing generic Librarian tick, `ConsentStore` gate, and airgap check pick
  this up with **zero new code**, exactly as they do for every other World.
  This is the load-bearing answer to the operator's hard constraint: scouting
  for this World is not a new feature, it is the existing feature fed new
  content.
- Two agents, `debt_advisor` and `consolidation_analyzer`, under
  `lab/pkb/agents/`, following the standard `AGENT.md` + `<id>.py` singleton
  contract, each with its own hand-rolled tick loop (see above). Their job is
  arithmetic and synthesis over locally-staged numbers plus the mounted
  World's sourced terms — not a chat personality gimmick — and every number
  or institution name that reaches an output file is inserted by code from a
  structured field, never freely generated by the local model (closes a
  major review finding: an LLM-paraphrased figure attached to a real-looking
  citation is more dangerous than an uncited one, because it reads as
  verified when it isn't).
- A **new, git-ignored, non-PKB staging location** for the operator's own
  numbers — `lab/data/user-import/debt-finance/` — following the exact
  `secrets.env` precedent already in this repo: `chmod 0600`, an explicit
  named `.gitignore` entry, never echoed or logged, and structurally outside
  the PKB indexer's walk (confirmed by reading `_iter_pkb_files` directly:
  it's rooted at `lab/pkb/`, so `lab/data/` was never inside it — this needs
  zero indexer code, not an exclusion-list entry). **v1 staging is
  manual** — the operator (or the friend running the fork) transcribes his
  own numbers into a small structured file by hand, against a minimal
  documented schema (ARCHITECTURE.md §6.1). This sidesteps two things that do
  not belong in this sprint: (a) a generic-vs-domain-specific portal *input*
  form question the operator's hard constraint would force us to resolve
  before building any UI, and (b) live Credit Karma ingestion, which is a
  credential/API integration problem an order of magnitude bigger than this
  wedge and is called out separately below.
- **A second, sibling non-PKB location for the agents' actual output**:
  `lab/data/user-import/debt-finance/findings/<agent-id>.md`. This is the
  single most important correction from the original draft. Every real
  figure, every named-institution comparison, every breakeven calculation
  lives here — never in `decisions.md`, never in any path under `lab/pkb/`.
  `decisions.md` reverts to its actual, documented purpose in this codebase
  (an optional, human-authored log of configuration decisions about the
  agent itself) and carries zero financial content. The dashboard activity
  stream — confirmed to live at `lab/data/activity.jsonl`, itself outside the
  PKB tree — carries only a short, non-identifying pointer event ("Debt
  Advisor produced a new finding — see
  `lab/data/user-import/debt-finance/findings/debt_advisor.md`"), never a
  raw figure in the message text itself.
- A **code-level, not merely prompt-level**, disclaimer and language-safety
  layer: the canonical "not a licensed financial advisor" text is appended
  deterministically by code after generation (not left to the local model to
  remember to include), and a lightweight keyword/regex guardrail scans
  generated text for evaluative ("best," "guaranteed") or imperative ("you
  should") language and for unverified institutional-character claims before
  any write — blocking and flagging, never silently publishing, when it
  trips. See ARCHITECTURE.md §7. This closes a major review finding: relying
  solely on system-prompt instruction to a small local model, backed only by
  a one-time pre-ship QA pass, was judged an insufficient safeguard for a
  feature surfacing debt-consolidation and lender comparisons to a real
  person.

Explicitly OUT of scope for this sprint (held, not silently dropped):
- **Any new portal page or "loan/consolidation comparison tool" UI.** This
  was floated by the operator as a possible MVP surface, and it is
  structurally the same shape as the domain-specific research-input form the
  operator already ruled out after Video Games World: a comparison table with
  APR/fee/term columns is a finance-specific form, not a generic
  AutoResearch/World feature, unless someone designs a genuinely generic
  "compare N declared World items by N declared attributes" surface that
  would also make sense for, say, comparing GPU driver branches in the Video
  Games World. Nobody has designed that generic surface. Per the standing
  rule: **hold it.** This sprint ships the recommendation as data (a private
  findings file plus a dashboard pointer and, for public-source scouting
  findings, the `/dac` queue), not as a bespoke comparison widget. Reading
  the private findings file for v1 means opening it directly (text editor /
  Finder) — no new "reveal" affordance is added in this sprint; see
  ARCHITECTURE.md §6.4 for why, and the open questions for whether that's
  worth a small fast-follow.
- **Autoresearch integration.** `/research`'s four archetypes
  (`model_throughput`, `prompt_variant`, `retrieval_quality`,
  `game_config_optimization`) measure this machine's own inference/KB/game
  performance, and its explicit honesty law is "every number is computed by
  code from an actual run on this machine, or it does not exist." A debt
  hypothesis has no such run to measure; forcing it in either fabricates a
  fifth archetype that violates that law, or bolts a disconnected UI onto the
  page. Not the right shelf. Rejected, not deferred — this isn't "not yet,"
  it's "not this."
- **Automated Credit Karma import.** Credit Karma has no sanctioned way for
  an agent to pull a user's account data other than logging in or entering
  credentials on the user's behalf — both are hard-prohibited regardless of
  user request. Building this would also mean designing, from scratch, the
  Tier-2 distilled/gated-fact pattern described in
  `docs/conversation-memory.md`, which the codebase itself documents as
  design-only, not built. That's real, valuable, and much bigger than one
  sprint. v1 tests the hypothesis with manual staging instead.
- **Investing content of any kind**, per the operator's own explicit
  ordering — enforced structurally by never declaring an `investing`
  category in `spec.json` (the gate rejects any term that tries to use an
  undeclared category), not merely by convention.
- **A shared tick-loop harness for non-builtin agents.** Real, valuable, and
  exposed as a gap by this sprint (two agents each need their own loop
  because none exists) — but generalizing it is bigger than this wedge.
  Flagged as tech debt (ARCHITECTURE.md §13), not solved here.
- **A cross-repo fix to `qukaizen-dac`'s agenda-cap ordering behavior or a
  non-strippable `face.json` disclaimer field.** Both are good ideas
  surfaced by review; both live in a sibling repository with its own
  review/versioning surface. This sprint works around the cap with an
  authoring rule and a seal-time check, and enforces the local disclaimer
  with a code-level precondition rather than the gate. See open questions for
  whether to file either proposal now.

## Disconfirming evidence

Pre-committed kill/shelve signals:

1. **Manual staging is where it dies.** If the operator (or the friend
   persona) won't bother hand-transcribing numbers into
   `lab/data/user-import/debt-finance/` even once, the whole "turns her
   existing data into a decision" value proposition never gets tested — this
   tells us the input-friction problem is the real blocker, not the
   recommendation quality, and the next move is a generic structured-input
   mechanism (across all Worlds), not more finance-specific work.
2. **Airgapped-by-default makes the "surfaces cheaper lenders" promise
   inert.** If the operator never flips to `hybrid` and never approves a
   single scouting consent request, the agents can only ever reason over
   whatever was hand-curated into `terms.json` at seal time — static,
   stale, not the "agents research and find things" pitch. If that's the
   steady state after two weeks, the honest conclusion is: this ships as a
   curated-content World, not a live-research one, and the pitch should be
   corrected rather than left implying otherwise.
3. **The recommendation is generic, not named.** If after real use the
   agents only ever produce boilerplate ("consider paying more than the
   minimum") with no real named institution or sourced rate, win condition
   (1) fails and the value the operator asked for — "surface credit unions
   and non-profit lenders that offer cheaper loans" — has not materialized.
   Shelve and revisit whether the term corpus needs to be authored by a human
   with real domain research rather than assumed available.
4. **The operator doesn't act on or trust a single finding within two
   weeks.** If the findings file fills up with recommendations he doesn't
   recognize as useful or doesn't verify, the synthesis isn't landing —
   pull back to a narrower single-agent, single-recommendation-type wedge
   before adding the second agent's scope.
5. **The disclaimer/guardrail layer trips constantly on legitimate output, or
   never trips at all under adversarial testing.** Either extreme is a
   signal: constant false-positive blocking means the guardrail is too blunt
   and needs tuning before this can be trusted hands-off; zero trips under
   deliberately adversarial QA prompts ("just tell me the best option")
   means the guardrail isn't actually doing anything and the compliance
   posture is weaker than it looks on paper.

## Displacement

- **Attention on ARAIL's own open threads.** This is a full sprint's worth of
  World-authoring plus two new agents' worth of testing, now with a
  materially larger engineering component (per-agent tick loops, a
  code-level disclaimer/guardrail layer) than the original draft accounted
  for; it is not free relative to the Video Games World follow-ups already
  on record as pending operator decision (the capability-registry adapter
  question) or the `qkz-project-aware-2b` / model-floor line of work.
- **Cross-product:** a week on arail content-authoring and agent-plumbing is
  a week not spent on aerollm's frontier-lane work or nucleus's distillation
  pipeline. Named explicitly, not waved away.
- **Precedent-setting cost, not just feature cost.** This is the first World
  whose subject matter is the user's own sensitive personal data rather than
  general domain knowledge (Horticulture, Physics, Video Games), and design
  review surfaced a real, previously-latent conflict: ARAIL's agent folders
  are *designed* to be lab-wide-searchable ("every file [under
  `lab/pkb/agents/`] is indexed by the wiki, browsable from `/dac`,
  searchable via the unified search" — the shipped agents README's own
  words), which is exactly wrong for personal financial data. This sprint's
  resolution — keep all substantive personal-data output entirely outside
  `lab/pkb/`, in a sibling location to the input staging directory — sets the
  pattern every future personal-data World (health, career, relationships)
  will follow. Getting it right here, including catching the leak this
  sprint's own first draft would have shipped, is worth the extra design
  care this document and its architecture spent — but it means this sprint
  is slower than a same-sized non-sensitive World would be, and that
  slowness is deliberate, not scope creep.

## Risks & coordination

- **Tier-2 fact-store gap (design question for the architect, not a
  blocker to reject on):** `docs/conversation-memory.md` documents the
  gated, quote-sourced "approved facts" pattern as designed but not built.
  This sprint does not require it — agents read the locally-staged file
  directly, outside the PKB, which is a narrower and already-safe pattern —
  but the architect should explicitly decide and document whether that
  direct-read pattern is the *permanent* shape for personal-data Worlds, or
  a stopgap until Tier-2 exists. The architecture (§6.6) treats it as the
  permanent v1 shape and defers Tier-2 explicitly; left undecided beyond
  that, the next personal-data World will re-litigate this from scratch.
- **License/compliance framing, not just data-handling:** whatever text the
  agents generate must read as informational synthesis with named sources,
  not as advice from a licensed advisor — "not a licensed financial advisor"
  language belongs in the agents' own persona prompts *and* is now
  code-enforced at write time (not solely relying on the model to remember),
  mirroring how the repo already treats the Llama/Gemma disclosure
  requirements as non-negotiable product text, not optional legal
  boilerplate. Review additionally surfaced a CROA / state debt-management
  and credit-counseling licensing question this document did not originally
  consider — addressed in ARCHITECTURE.md §7.4, flagged for operator
  sign-off in open questions.
- **Real-source authoring is a real cost:** the gate's "closed, sourced
  graph" requirement means someone has to actually go find and cite real
  credit union / NCUA / CFPB pages for `terms.json` and `knowledge_sources`
  before this can seal — this is genuine domain research effort, not
  boilerplate — *and*, per a review finding verified directly against
  `dac_world/seal.py`, the order those sources appear in the array
  determines which ones ever produce a live scouting watch (a hard 3-entry,
  position-based cap, not kind-aware). Both should be budgeted as real cost
  in the architect's plan, not assumed away.
- **The PKB-transparency-vs-privacy tension is now documented, but only for
  this World.** Whether "keep sensitive output structurally outside
  `lab/pkb/`" should become a written, cross-World policy (e.g., in this
  repo's CLAUDE.md) rather than something each future personal-data World
  has to independently rediscover is a real open question, flagged for the
  operator rather than decided unilaterally here.

## Recommended next step

**PROCEED to `/builder`** — the architecture is resolved. Scope: (1) seal and
mount the `debt-finance` World bundle with real, sourced institutions, URL
sources ordered correctly for the agenda cap; (2) ship `debt_advisor` and
`consolidation_analyzer` as standard PKB agents, each with its own tick loop,
reading a new git-ignored, non-indexed `lab/data/user-import/debt-finance/`
staging file and writing to a sibling, equally non-indexed
`lab/data/user-import/debt-finance/findings/` directory — never to
`decisions.md` and never to anything under `lab/pkb/`; (3) let scouting work
exactly as it already does for every other World via `agenda.json`, with zero
new code in `scouting.py` or `agenda_watch.py`; (4) ship the code-level
disclaimer-append and language/institution-claim guardrail described in
ARCHITECTURE.md §7 as part of both agents' write path, not as a follow-up.

**REJECT** — not defer — folding this into `/research`/Autoresearch; it is
the wrong shelf per the engine's own honesty contract.

**HOLD** the loan/consolidation comparison-tool UI, any Credit Karma
auto-import, the reveal-whitelist convenience for the findings file, and the
two cross-repo `qukaizen-dac` proposals (kind-aware agenda cap, non-strippable
disclaimer field) until, respectively: a genuinely World-generic comparison
surface is designed; the Tier-2 gated-fact pattern exists; the operator
decides the convenience is worth the small added code; and the operator
decides whether to open those proposals now or later. None block this
sprint; all would silently violate a standing constraint or overstate this
sprint's scope if built now.

If the builder finds that even the private findings-file path can't be kept
cleanly outside the PKB walk without more plumbing than a "one sprint" wedge
should carry, the fallback shippable is the World bundle plus agents
producing recommendations over the sealed World content alone (no user
numbers at all, generic "how balance transfers work" synthesis) — a smaller
but still real test that the two agents and the World mechanism work, with
personal-data ingestion pushed to a fast-follow sprint. Given the direct
source-code verification behind this revision, that fallback is not expected
to be needed — the non-indexed property of `lab/data/` was confirmed by
reading `_iter_pkb_files` itself, not assumed.
