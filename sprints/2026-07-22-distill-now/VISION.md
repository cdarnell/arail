# Vision: "Distill now" — one manual, end-to-end bake→seal→compact, run once, for real

**Date:** 2026-07-22
**Product:** arail
**Wedge size:** one sprint
**Program:** ARAIL Lab automation (Fable roadmap §5, endorsed by Charlie). The **manual one-shot**
precedes any scheduler. This VISION scopes the one-shot ONLY. Source roadmap:
`/Users/netsushi/ProJects/qukaizen-nucleus/docs/PAPERAGENTS_ARAIL_NUCLEUS_GEOAI_ROADMAP.md`.
Precedent it builds on: `qukaizen-nucleus/sprints/2026-07-22-paperagents-dac-okf-real/` (first real, not
illustrative, PaperAgents↔DaC gate).

**Hard scope fence (per Charlie, verbatim "1000% this is a manual sequence first"):** if this sprint
grows a cron job, a `trigger = { kind = "schedule" }`, a weekly wrapper, org-admin self-serve, the docent
rail, or the Agent-Forge card UX, it has **overshot**. Those are named, later, separate sprints. This
sprint proves the *chain* runs once, on Charlie's box, and that compaction is safe. Nothing else.

---

## User

**Charlie, on his own workstation, running ARAIL locally.** Not a generalized non-technical user — the
roadmap's "non-technical user + docent rail" is explicitly a *later* concern that this run must earn the
right to build. Charlie has ARAIL running (`./arailctl start`, `127.0.0.1:8080`), at least one DaC World
already mounted and gate-approved on the `/dac` tab (e.g. one of the five knowledge Worlds, or the
photography World the `/build` tab already defaults to), and — critically — he has **never once** watched
his own lab's approved knowledge travel the full tail of the refresh loop: `COMPILE → bake(sealed) →
compact`. He can compile (that stage has a curl-able receipt). He cannot yet point at a single sealed
model his lab produced, nor a single compaction receipt proving the "knowledge becomes memory" step ran
without gutting his KB.

He is the right and only user for the first run because the risky, trust-burning step (compaction) is
destructive-feeling and unattended-by-design in the end state; the person who eats the first blast radius
should be the founder, on his own data, before any friend, family member, or HOT mapper is exposed.

## Problem

**The refresh-loop diagram claims a `RETAIN(bake+compact)` stage that has never run end-to-end on a real
lab.** The pieces exist in isolation and have never been connected and fired once:

- **The bake spine already exists.** `/api/build/world/start` (`src/arail/portal/build_api.py:211`)
  already takes an ARAIL-approved DaC World → pulls approved terms → synthesizes → calls the Nucleus
  trainer (`world_corpus.build_world_corpus` → `nucleus_client.train_direct`). This is ~70% of "Distill
  now" *already built*. But this path **deliberately bypasses the orchestrator/certifier**, so it emits
  **no seal** — `build_detail` returns `"seal": None` for `world_corpus` mode (`build_api.py:381`).
- **The seal machinery exists — separately.** The Nucleus certifier mints Ed25519-sealed "Knowledge
  Isotopes" verifiable via `qkz isotope verify` and `GET /seal/by-run/{run_id}`. But it only sits on the
  *orchestrator* path (`/api/build/start`), which the World path skips.
- **Compaction does not exist at all.** `grep -ri compact src/` in ARAIL finds unrelated hits. There is
  no pointer-swap, no `archive/<bake-id>/`, no `corpus_sha256` addressing, no receipt, no rollback.

So the honest state: ARAIL can *train a model from a World's approved knowledge*, but has never (a)
sealed that specific model, (b) sanity-checked that the sealed artifact actually loads and answers, or
(c) turned the now-distilled working KB into archived memory reversibly. Until those three connect and
run once, the `RETAIN` stage is paper, cannot earn a "live badge," and the whole "your lab's research
becomes a small expert model, then becomes memory" claim is unproven on real data.

## Win condition

Falsifiable, witnessed once, on Charlie's own machine, in local mode, **with no cloud account**. PASS
requires ALL of:

- **WC-A (one genuine sealed model).** A "Distill now" tap on an approved World produces a trained
  student model AND a seal artifact that `qkz isotope verify <id>` (or the offline `--from-file` path)
  returns **exit 0** on. The seal is curl-able / on-disk, not simulated, not badged SIMULATED.
  *Conditional-descope trigger below (see Recommended next step) if the certifier proves un-runnable
  on Charlie's box inside the sprint.*
- **WC-B (it actually loads and answers).** The sealed model loads into ARAIL's chat/compute-source path
  and answers **≥5 held-out prompts** drawn from the World's own terms without erroring or emitting empty
  output. This is a **load-and-answer smoke check, NOT a comparative eval** — see the descope note; on a
  first-ever run there is *no previous model to compare against*.
- **WC-C (one genuine compaction receipt, reversible, human-gated).** After WC-A+B pass, ARAIL shows one
  plain-language confirmation ("Your new model passed — tidy up the old notes?"). Only on an explicit tap
  does the working KB move to `archive/<bake-id>/` addressed by `corpus_sha256`; live KB resets. A
  **receipt file** is written recording `{bake_id, corpus_sha256, archive_path, model/seal id, timestamp,
  n generations retained}`. Compaction is **never** a delete.
- **WC-D (rollback proven once).** Restoring the archive returns the lab to its pre-compaction state —
  demonstrated live, once, in this sprint. If rollback isn't demonstrated, WC-C is not met.
- **WC-E (fail-safe).** A failure at any earlier step (train, seal, or smoke) leaves the lab **fully
  intact on the old state** — no compaction is offered, no KB is touched. Tested by forcing a failure.

**Witness, not vibe:** the sprint is PASS when Charlie can, in one sitting, point at (1) a `qkz isotope
verify` exit-0, (2) the model answering a held-out prompt in chat, (3) the receipt JSON, and (4) the
lab restored from archive.

## Wedge

The smallest change that proves the chain end-to-end. Most of the spine already exists; the net-new work
is three joints, not a new pipeline.

**IN (build):**
- A **"Distill now" button** on the *existing* `/build` or `/dac` tab (no new page) that fires the
  *existing* `/api/build/world/start` chain against a selected approved World, in **local mode**.
- **Seal joint:** make the World-corpus bake produce a real seal — either route its trained output
  through the certifier's seal step, or invoke the seal directly on the trained artifact so
  `qkz isotope verify` passes. (Reuse existing certifier/Ed25519 machinery; do not reinvent it.)
- **Load-and-answer smoke check:** load the sealed model, run ≥5 held-out World prompts, assert
  non-empty sane output. Gate compaction behind this passing.
- **Compaction joint (the genuinely new, higher-risk piece):** human-confirmed, reversible pointer-swap
  to `archive/<bake-id>/` by `corpus_sha256`, a written receipt, and a one-command rollback. This is the
  heart of what's worth proving and where the architect's paranoia should concentrate.

**OUT (explicitly deferred — building any of these = overshoot):**
- **Any scheduler / weekly / cron / `trigger` automation.** The named next sprint. Not here.
- **A formal PaperAgents `Pipeline` CRD.** *Confirmed absent* — the shipped CRD kinds are Team, Agent,
  Knowledge, Organization, Integration, RiskPolicy, Dashboard, Workflow, Secret (`src/crd/types.ts:18`).
  Adding a kind is a full typed sprint (types + KIND_ORDER + schema + registry + applier + snapshot
  migration), per the config-framework precedent. **v1 runs the chain as a script / committed run-spec,
  not a `pactl apply` manifest.**
- **A formal comparative AeroLLM smoke-eval vs the previous model.** *Confirmed absent as turnkey* —
  AeroLLM has research/correctness scripts (`wikitext_perplexity.py`, `perplexity_baseline_diff.py`) but
  nothing that says "new bake vs previous, held-out, PASS/FAIL." And on the **first-ever** run there is no
  previous model. Descoped to WC-B's load-and-answer check; the comparative gate is a later sprint that
  needs a second generation to exist first.
- The docent rail, the Agent-Forge "Super Skill" card, org-admin knobs, GeoAI guardrails, site messaging.
- Multi-World, multi-user, unattended compaction, N>1 generation policy tuning.

## Disconfirming evidence

Pre-committed. If we hit these, we descope or defer — we do not rationalize.

1. **The certifier won't run on Charlie's box in-sprint.** The seal path is a docker-compose stack
   (NATS + orchestrator + certifier + trainer). If it can't be stood up and made to seal the World bake
   inside the sprint's first days, **descope WC-A**: ship "trained loadable model + JSON run receipt
   (corpus_sha256, config, artifact path)" and **defer the Ed25519 seal** to a follow-up. This is the
   single pivotal unknown — the architect must spike it on **day one**, not discover it mid-build.
2. **`train_direct` doesn't yield a loadable artifact.** It "just launches a background task and returns
   immediately." If polling never converges to a model file ARAIL chat can actually load (adapter /
   gguf / Modelfile), WC-B fails and the "sealed *model*" claim collapses to "sealed *corpus*." Then
   descope to proving the corpus+training receipt is real and defer the loadable-model claim — but say so
   loudly; it means the bake tail is less real than the roadmap assumes.
3. **Compaction can't be made credibly reversible in one sprint.** If rollback (WC-D) can't be
   demonstrated cleanly, **do not ship compaction at all** this sprint — ship bake+seal+smoke and leave
   the KB untouched. An irreversible-feeling compaction is worse than none; it burns exactly the trust
   the roadmap's top named risk warns about.
4. **Charlie won't tap "tidy up."** Behavioral signal: if, after WC-A+B pass on his own real data,
   Charlie doesn't trust it enough to actually tap the compaction confirmation (leaves the old KB in
   place), the reversibility story isn't credible yet. That is a kill signal for *automating* compaction
   later — the scheduler sprint does not start until the founder taps yes on his own lab.

## Displacement

Saying yes is not free.

- **Within ARAIL:** this consumes the slot after `2026-07-20-model-ux-unification`. The core lab surfaces
  (chat memory, model UX, autoresearch/curriculum feed) get no advance this cycle. Specifically, further
  polish on the model-UX unification and any Knowledge-Canvas work waits.
- **Across QuKaiZen:** time here is time not on **aerollm** GA gates / CUDA backend, on **aerollm-distill**,
  or on **qukaizen-geoai** guardrails. Fable's §5 explicitly parks GeoAI guardrails behind this run
  ("paper guarding paper" otherwise) — so the displacement is *intended*, but real: GeoAI's higher-stakes
  users wait on this lower-stakes proof.
- **What it forecloses:** the tempting shortcut of demoing bake and compaction *separately* and *claiming*
  the loop is real. This sprint exists to make that claim illegal until the chain has run once, sealed and
  reversible, on real data. It also foreclosures the reverse temptation — jumping straight to the weekly
  scheduler on top of a chain no human has ever watched succeed once.

## Recommended next step

**PROCEED to `/architect` with this as the spec — conditioned on a day-one certifier spike.**

Justification: the chain is ~70% already built (the `/api/build/world/start` World-corpus path is the
spine); the net-new work is three well-bounded joints — seal-wiring, a load-and-answer smoke check, and a
human-gated reversible compaction + receipt — which is one sprint *if* the certifier cooperates.

The architect must resolve **before the builder starts**, because it gates whether WC-A exists:
1. **Day-one spike:** stand up the Nucleus certifier on Charlie's box and prove it can seal the
   World-corpus bake (disconfirmer 1). If it can't, pre-commit the descope to "trained model + JSON run
   receipt, seal deferred" rather than blocking the whole wedge.
2. **Pre-commit the compaction rollback design** (disconfirmer 3) — reversible pointer-swap with a
   demonstrated restore, or compaction doesn't ship this sprint.
3. **Do not** add a PaperAgents `Pipeline` CRD or a comparative AeroLLM eval — both confirmed absent and
   both explicitly out of scope; the chain runs as a script/run-spec with a load-and-answer smoke check.

Do not let "we'll wire the seal during the sprint" or "we'll make compaction reversible later" stand.
Both are decided before the sprint, not during it.
