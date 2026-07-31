# Architecture: World of Debt Finance

**Date:** 2026-07-26
**Product:** arail
**Sprint:** `2026-07-26-world-of-debt-finance`
**Input:** `VISION.md` (this sprint) + three independent architecture proposals
(MVP-First, Compliance-and-Trust-First, World/Agent-Architecture-First) +
four independent adversarial reviews of the first synthesis (Regulatory/
Compliance — WEAK_PASS, Data Privacy/Security — **BLOCK**, World/DaC Contract
Conformance — PASS, Technical Feasibility/Failure Modes — WEAK_PASS)
**Status:** design complete, BLOCK resolved and verified against source,
ready for `/builder`

---

## 0. How this document resolves everything on the table

This is the second synthesis. The first passed four independent adversarial
reviews; one returned **BLOCK**. Per this workflow's own rule, a BLOCK is
resolved in the design or stated plainly as an open question — it is never
silently dropped. It has been resolved here, and verified directly against
this repo's and `qukaizen-dac`'s actual source rather than taken on the
reviewer's word alone (see §2 for what was checked and how).

### 0.1 The BLOCK, and how it's resolved

**Finding:** the first synthesis routed both agents' actual financial
analysis — real balances, named-institution comparisons, breakeven math —
into `decisions.md` under `lab/pkb/agents/<id>/`. Verified directly:
`_iter_pkb_files` (`src/arail/pkb.py:391`) walks all of `lab/pkb/` and
excludes only `conversations/` and World-machinery paths; `/api/pkb/search`
(`app.py:10704`) calls `pkb.search()` with `approved_only=False` — the full,
ungated corpus, not the Compiled-KB-gated path. So any figure written to
`decisions.md` becomes immediately full-text and (once indexed)
semantically searchable by anyone who can reach the portal — which, per this
product's own stated purpose ("a shareable AI Lab for friends/family") and
this workspace's own documented shared-machine convention, is not a
theoretical multi-user scenario. Compounding it: `decisions.md` is
documented in this codebase (`agents/loader.py:17`,
`agents/builtin_seed.py:157-171`) as an optional, *human-authored* log of
configuration decisions about the agent itself — not a channel for
agent-generated analysis of user data — and the same README explicitly
states the whole point of the `lab/pkb/agents/` location is that everything
there **is** indexed, browsable, and searchable. Using it for private
financial figures wasn't a narrow bug; it fought the file's documented
purpose and the directory's documented design intent at the same time.

**Resolution (§6):** neither agent ever writes a user figure, a computed
aggregate (blended APR, breakeven month), or a named-institution comparison
to anything under `lab/pkb/`. `decisions.md` reverts to its actual,
documented purpose. A new, sibling, non-PKB location —
`lab/data/user-import/debt-finance/findings/<agent-id>.md` — carries all of
it, using the exact same "never inside the PKB walk" property already
verified for the input staging file (`lab/data/` is rooted outside
`PKB_ROOT`; `_iter_pkb_files` never sees it, confirmed by reading the walk
directly — no indexer code change, no exclusion-list entry, needed). The
dashboard activity stream (`lab/data/activity.jsonl`, also confirmed outside
the PKB tree) carries only a short, non-identifying pointer to the findings
file — never a figure in the message text. This is a stronger property than
"gate it behind Compiled-KB approval," which the review also floated as an
option: that path was checked and rejected, because `/api/pkb/search`'s
`approved_only=False` default means gating alone would not have stopped the
ungated endpoint from returning it anyway. Keeping it out of the walked tree
entirely is the only fix that doesn't depend on a second system's default
staying favorable.

### 0.2 Everything else, resolved

| Topic | First synthesis said | This revision does |
|---|---|---|
| Sensitive-output location | `decisions.md` + dashboard + `/dac` queue | **`lab/data/user-import/debt-finance/findings/<agent-id>.md`**, never `lab/pkb/`. `decisions.md` reverts to config-log-only. Dashboard gets a pointer, never a figure. `/dac` queue is scouting-only (public market data), unchanged. See §6. |
| How agent output text is produced | Free-form LLM prose over sourced content | **Numbers and institution names are inserted by code from structured fields; the LLM narrates only.** Closes the review finding that a hallucinated figure attached to a real citation reads as verified when it isn't, and the separate finding that nothing checked whether LLM prose faithfully reproduced Consolidation Analyzer's own computed numbers. See §7.5. |
| Disclaimer enforcement | System-prompt instruction + one-time pre-ship QA pass | **Code appends the canonical disclaimer deterministically after generation, and refuses to write findings at all if `compliance/DISCLAIMER.md` is missing or altered.** QA persona-drift testing remains, as defense-in-depth, not the only layer. See §7.1–§7.2. |
| Institutional-character mislabeling | Persona-prompt rule only | Persona rule **plus** a code-level keyword/regex guardrail that blocks a write if an institution name is paired with "credit union"/"nonprofit"/"member-owned" language and that institution isn't in the vetted `terms.json` set. See §7.2, §4.3. |
| `knowledge_sources[]` → live watches | "Auto-derives one entry per url-kind source, capped at 3" | **Verified false as stated** — `dac_world/seal.py:206` takes the first 3 array entries by raw position, regardless of kind, before any URL filtering happens downstream in `agenda_watch.py`. Fixed with an authoring rule (URL-kind sources first) plus a seal-time check. See §3.2. |
| Agent tick-loop cost | Implied "content authorship... not new plumbing" | **Corrected.** No shared tick harness exists for non-builtin agents; each agent hand-rolls its own asyncio loop, cooldown, and state, following Buddy's own pattern. Budgeted explicitly as real engineering. See §5.3. |
| Non-strippable `face.json` disclaimer field | Deferred to cross-repo `qukaizen-dac` proposal | **Still deferred**, for the same cross-repo-separation reason — but the *local* interim mechanism is now precondition-checked in code (§7.1), not left purely to QA-checklist discipline, which closes the review's specific objection to leaving it QA-only. |
| CROA / state licensing exposure | Not addressed | Addressed in `compliance/DISCLAIMER.md` content and §7.4 — single-operator, self-hosted, non-commercial framing stated explicitly; forkers directed to their own review before commercial use. |
| Malformed staging JSON | "Builder-level detail," unspecified | Minimal schema + defined parse-failure behavior specified in §6.1. |
| `/worlds` tier-gating wording | Attributed to `_TIER_SURFACES` membership | Corrected: `/worlds` (`app.py:2450`) carries no `_require_surface` call at all — it's simply ungated, independent of `_TIER_SURFACES`. Verified directly; conclusion (no tier-gating change needed) is unchanged. |
| Gate law count | "Two structural laws relevant here" | Corrected: `assert_closed_sourced_graph` (`dac_world/gate.py:39`) enforces **three** — sourced, declared category, closed related-graph. All three matter here (see §3.3); the investing-exclusion property rests on the category law specifically. |

Everything else — World declare/gate/seal/mount mechanics, scouting/agenda
reuse with zero new code in `scouting.py`/`agenda_watch.py`, no Credit Karma
auto-import in v1, investing structurally excluded via the category gate, no
new portal UI — was consistent across all three original proposals, survived
all four reviews unchallenged, and is carried forward unmodified.

---

## 1. Resolved: no new portal UI in v1

A page with fields labeled APR / transfer fee / promo months *is* a
domain-specific form, full stop — the fact that it computes instead of
watches doesn't change its shape, and the operator's own rule after Video
Games World doesn't carve out an exception for calculators. No one on any of
the three original proposals designed a genuinely generic "compare N
declared World items by N declared attributes" surface, so per the standing
rule, it is held, not built. This sprint ships **zero new portal routes,
zero new templates, and zero new `_TIER_SURFACES` entries.**

Output surfaces only through mechanisms that already exist:
- The dashboard activity stream (`lab/data/activity.jsonl`, confirmed
  outside the PKB tree) — pointer events only.
- A new, non-PKB findings file per agent (§6) — opened directly by the
  operator; no reveal affordance is added in v1 (§6.4).
- `/dac`'s Compiled-KB review queue, for anything scouting actually fetches
  from a public source (never the operator's own figures).
- `/worlds`, which already renders whatever World is currently mounted —
  confirmed ungated at every tier: the route at `app.py:2450` carries no
  `_require_surface(...)` call at all (not, as the first draft stated, a
  consequence of `_TIER_SURFACES` membership — `/worlds` isn't a key in that
  dict either way; the conclusion that no tier-gating change is needed holds
  regardless).

If a genuinely generic comparison-table renderer is designed later, that is
a separate, cross-World vision pass — explicitly out of this sprint's scope.

---

## 2. Assumptions and verified facts

Everything in this section was read directly from source during this
revision, not inferred from the reviews' claims alone.

1. **`dac_world` (`forge.py`/`gate.py`/`seal.py`) lives in the sibling repo
   `~/ProJects/qukaizen-dac`, not in this repo.** Confirmed by reading the
   files directly. This sprint treats `dac_world` as a **consumed,
   unmodified dependency**. No PR to `qukaizen-dac` is in scope.
2. **`_iter_pkb_files` (`src/arail/pkb.py:391-411`) walks only `PKB_ROOT`
   (`lab/pkb/`)** via `root.rglob("*")`, excluding only files whose path
   contains a `conversations` path segment and World-machinery paths
   (`is_world_machinery_path`). `lab/data/` is a structurally separate tree
   this function never reaches, **regardless of file extension or
   filename**, with **zero code change required** to keep a file there out
   of the wiki, the vector index, and `/api/pkb/search`.
3. **`/api/pkb/search` (`app.py:10704-10708`) calls `pkb.search()` with the
   default `approved_only=False`** — confirmed by reading the handler
   directly. This is the full raw corpus under `lab/pkb/`, unfiltered by any
   Compiled-KB approval state. `search_for_agents` (`pkb.py:673-679`) is the
   only caller that passes `approved_only=True` (via `gate_enabled()`), and
   it is used for agent-internal retrieval, not the human-facing search
   endpoint.
4. **`decisions.md` is documented, in this codebase, as an optional,
   human-authored configuration-decision log — not an analysis-output
   channel.** Confirmed: `agents/loader.py:17` ("decision log (optional;
   human-authored)"); `agents/builtin_seed.py:157-158` ("append-only log of
   meaningful choices about the agent. Humans write to it; the Agent Forge
   will too."); Buddy's own seed content (`builtin_seed.py:118-136`) is
   entries like "Global cooldown 5 min. Cheaper to be quiet than annoying" —
   config narration, not domain analysis.
5. **The shipped agents README states, as an explicit design intent, that
   everything under `lab/pkb/agents/` is indexed, browsable, and
   searchable** (`agents/builtin_seed.py:164-172`: "Agents live under
   `lab/pkb/agents/` inside the PKB so every file above is: Indexed by the
   wiki... Browsable from `/dac`... Searchable via the unified search...").
   This is a feature for domain-general agent output (research notes, dream
   journals) and precisely the property that makes the location wrong for
   personal financial data. There is already a separate, existing
   convention for agent-generated content awaiting human review —
   `agents/recommendations/<file>.md`, used by the Researcher agent and
   classified as `agent_recommendation` by both `pkb.py:427` and
   `compiled_kb.py:177` — but it inherits the exact same "under `lab/pkb/`,
   therefore ungated-searchable" property (confirmed: `_kind_of` and
   `_iter_pkb_files` apply uniformly across `lab/pkb/`), so it was
   considered and rejected as an output location for this World's sensitive
   content for the same reason `decisions.md` was.
6. **`/worlds` and `/dac` are already every-tier, ungated surfaces.**
   `_TIER_SURFACES` (`app.py:129-134`) lists `dac` in both `minimalist` and
   `maximus`; the `/worlds` route (`app.py:2450`) carries no
   `_require_surface(...)` gate of any kind — confirmed by reading the
   handler. Mounting `debt-finance` requires no tier-gating changes.
7. **`agenda_watch.load_watches()` only picks up `http(s)://`-shaped feed
   strings** (`_URL_RE = re.compile(r"^https?://\S+$")`,
   `agenda_watch.py:57,95`).
8. **`dac_world/seal.py:200-208` derives `agenda.json.watches` from the
   first three `knowledge_sources[]` entries by raw array position,
   regardless of `kind`** — confirmed by reading the comprehension directly:
   `for s in (spec.get("knowledge_sources") or [])[:3] if isinstance(s,
   dict)`, with `feeds: [str(s.get("ref") or s.get("holder") or "source")]`.
   There is no kind-based filtering before the slice. A World author who
   puts non-URL `institution`/`reference`-kind sources in the first three
   positions silently loses any URL-kind sources beyond position 3 to a live
   watch, with no error surfaced anywhere in the pipeline.
9. **`assert_closed_sourced_graph`** (`dac_world/gate.py:39-70`) enforces
   **three** structural laws, confirmed by reading the function body: every
   term needs a non-empty `source` (`unsourced`); every term's `category`
   must be in the declared set (`undeclared_category`); every `related[]`
   edge must resolve to a slug inside the same closed term set
   (`dangling_edges`). The category law is the mechanism that makes
   "investing is out of scope" enforceable by omission: don't declare an
   `investing` category, and the gate rejects any term that tries to use
   one.
10. **`scouting.py` hard-sets `finding["auto_approved"] = False`**
    (`scouting.py:94`) inside `_run()`, with no parameter or code path that
    overrides it, and gates every fetch on `ConsentStore().is_approved(...)`
    (`scouting.py:66-67`) per `consent_id`. `agenda_watch.tick()`
    short-circuits on `is_airgapped()` before any of this runs
    (`agenda_watch.py:236`).
11. **No Tier-2 gated-fact store exists yet** (`docs/conversation-memory.md`
    documents it as designed, not built). This sprint does not build it and
    does not need it — see §6.6.
12. **No shared background-tick harness exists for non-builtin PKB
    agents.** The generic loader's `start_all_auto` only calls
    `instance.start()` if the agent instance defines one; `BuddyAgent` hand-
    rolls its own `asyncio` loop, cooldown, and state persistence from
    scratch. Debt Advisor and Consolidation Analyzer each need the same,
    following Buddy's implementation as the reference pattern — this is real
    new code, not configuration.
13. **The operator's own numbers (balances, APRs) are supplied by hand in
    v1.** No Credit Karma API/scrape/login integration is attempted — that
    would require entering or handling credentials on the user's behalf,
    which is hard-prohibited regardless of user request, independent of any
    architecture decision made here.
14. **This assistant's own operating constraints bound what the *product* is
    allowed to claim**, not just what Claude does while building it: the
    product must never present its output as advice from a licensed
    financial advisor, and nothing in this design computes or facilitates an
    actual funds transfer/trade. This is a permanent product-design
    constraint, not a sprint-scoped one.

---

## 3. World bundle design (declare → gate → seal → mount)

### 3.1 Slug and directory

`examples/worlds/debt-finance/` — slug `debt-finance`, must agree across
`manifest.json`/`spec.json`/`face.json` (checked independently at mount by
`load_bundle`/`mount()`, per `world_mount.py`'s `SlugInvalid` path).

### 3.2 `spec.json` — with the agenda-cap ordering fix

**Authoring rule (new, closes a Technical Feasibility major finding):** real,
fetchable `url`-kind sources that must produce a live scouting watch go
**first**, in priority order, in `knowledge_sources[]` — because
`dac_world/seal.py` slices the first three entries by raw position before
any kind-aware filtering happens (§2.8). Anything after position 3 in this
array will never produce a watch, no matter its `kind`. Non-URL sources
(`institution`, `reference`) that exist purely for citation/provenance go
**after** the URL-kind entries, explicitly accepting they contribute to
`terms.json` sourcing and provenance tier but not to live scouting.

```json
{
  "slug": "debt-finance",
  "display_name": "World of Debt Finance",
  "categories": [
    { "id": "debt-types",      "label": "Debt Types" },
    { "id": "credit-products", "label": "Credit Products" },
    { "id": "institutions",    "label": "Lenders & Institutions" },
    { "id": "strategies",      "label": "Payoff & Consolidation Strategies" },
    { "id": "terminology",     "label": "Terminology" }
  ],
  "knowledge_sources": [
    { "kind": "url", "ref": "https://www.consumerfinance.gov/consumer-tools/credit-cards/answers/balance-transfer/",
      "trust": "high", "holder": "CFPB", "license": "public guidance cited by attribution" },
    { "kind": "url", "ref": "https://www.ncua.gov/consumers/consumer-resources",
      "trust": "high", "holder": "NCUA", "license": "public guidance cited by attribution" },
    { "kind": "url", "ref": "<a specific, real credit union's published balance-transfer/consolidation-loan rate page — pick the single highest-value one; it is the last position that will produce a live watch>",
      "trust": "medium", "holder": "<that credit union, named>" },

    { "kind": "url", "ref": "<a specific, real issuer's balance-transfer offer page — cited for terms.json sourcing and provenance tier only; position 4 will NOT produce a live watch under the current 3-entry cap>",
      "trust": "medium", "holder": "<that issuer, named>" },
    { "kind": "institution", "ref": "National Foundation for Credit Counseling (NFCC) member agencies",
      "trust": "high", "holder": "NFCC", "license": "public guidance cited by attribution" },
    { "kind": "reference", "ref": "Standard consumer-credit reference texts (APR/amortization mechanics)",
      "trust": "high", "holder": "various publishers", "license": "facts cited by attribution — no verbatim text" }
  ]
}
```

**No `investing` category, deliberately, and this is load-bearing, not a
comment.** Per §2.9, the gate rejects any term whose `category` isn't
declared here. Bringing investing into scope later requires a conscious
`spec.json` edit and a re-seal — an auditable act, not something that can
happen by drift.

**Seal-time verification (new, closes the same finding):** after running
`write_bundle()`, the authoring step must open the produced `agenda.json`
and assert it contains exactly the intended feed URLs (the 2–3 the author
meant to be live). If a URL-kind source silently didn't make it in because
of ordering, this is caught here — at authoring time — not discovered later
as "scouting has nothing to do and nobody knows why."

### 3.3 `terms.json`

15–25 terms across the five categories, each satisfying the gate's **three**
laws (§2.9): non-empty `source`, `category` in the declared set, every
`related[]` edge resolving inside the same closed term set. Example subgraph:

```json
[
  { "slug": "debt-finance", "term": "balance-transfer", "category": "strategies",
    "short": "Moving revolving balances to a card with a lower introductory APR.",
    "definition": "...", "related": ["introductory-apr", "transfer-fee"],
    "source": "https://www.consumerfinance.gov/consumer-tools/credit-cards/answers/balance-transfer/" },
  { "slug": "debt-finance", "term": "introductory-apr", "category": "terminology",
    "short": "A temporary reduced interest rate offered for a limited period.",
    "definition": "...", "related": ["balance-transfer"],
    "source": "<issuer offer page>" },
  { "slug": "debt-finance", "term": "transfer-fee", "category": "terminology",
    "short": "A one-time fee (typically 3-5%) charged to move a balance.",
    "definition": "...", "related": ["balance-transfer"],
    "source": "<issuer offer page>" },
  { "slug": "debt-finance", "term": "credit-union", "category": "institutions",
    "short": "Member-owned, not-for-profit financial cooperative.",
    "definition": "...", "related": ["ncua-insured", "debt-consolidation-loan"],
    "source": "https://www.ncua.gov/consumers/consumer-resources" },
  { "slug": "debt-finance", "term": "ncua-insured", "category": "terminology",
    "short": "Deposits insured up to $250k by the National Credit Union Administration.",
    "definition": "...", "related": ["credit-union"],
    "source": "https://www.ncua.gov/consumers/consumer-resources" },
  { "slug": "debt-finance", "term": "debt-consolidation-loan", "category": "credit-products",
    "short": "A single loan used to pay off multiple higher-rate debts.",
    "definition": "...", "related": ["credit-union", "avalanche-method"],
    "source": "https://www.consumerfinance.gov/consumer-tools/credit-cards/answers/balance-transfer/" },
  { "slug": "debt-finance", "term": "avalanche-method", "category": "strategies",
    "short": "Paying off debts ordered by highest interest rate first.",
    "definition": "...", "related": ["debt-consolidation-loan"],
    "source": "https://www.consumerfinance.gov/consumer-tools/credit-cards/answers/balance-transfer/" }
]
```

**Institutional-character verification (authoring discipline, not new
plumbing):** any term that asserts an institution's *legal character* —
"credit union," "nonprofit lender," "NCUA-insured" — must cite a
verification source distinct from the institution's own marketing copy: an
NCUA charter lookup result, an IRS Tax-Exempt Organization Search / Form 990
record, or equivalent. This closes a specific failure mode: a for-profit
lender's own page claiming nonprofit-adjacent framing getting curated in as
if verified. The runtime half of this rule — a scouting finding can never
self-promote to a labeled "credit union"/"nonprofit" — is now enforced by
**both** the agent-persona rule (§5) **and** a code-level guardrail (§7.2),
closing a review finding that persona-only enforcement has no backstop
against normal model drift.

### 3.4 Seal

`write_bundle()` re-runs the gate, computes `provenance_tier` from the
sources' declared `trust` levels, writes `face.json` + the 6 canonical
bundle files + the seal-exempt siblings (`SKILL.md`, `capabilities.json`,
`arail-plugin.json`) plus, new for this World, `compliance/DISCLAIMER.md`
(§7.1). `agenda.json.watches[]` auto-derives from the first three
`knowledge_sources[]` entries per §3.2's ordering rule.

### 3.5 Mount

`mount(examples/worlds/debt-finance/)` runs the standard five steps
(parse+validate slug agreement, `verify_seal` dual-sha256 check,
`check_compat`, `check_categories` — an independent re-check of every term's
category against the declared set, belt-and-suspenders on the
investing-exclusion property — then stage into
`lab/pkb/sources/world-debt-finance/`, sweep any other mounted World,
best-effort LanceDB index, write the mount pointer last). No finance branch
exists or is added to `world_mount.py`. Visible immediately at `/worlds`
(ungated, per §2.6) and in the wiki via the standard per-term page render.

---

## 4. Scouting — zero new code, traced end to end, and scoped to public data only

1. Sealed `agenda.json` carries the auto-derived watches from §3.2's
   ordering-fixed source list, e.g.:

   ```json
   { "schema": "dac.world-agenda/v1", "world": "debt-finance",
     "watches": [
       { "node": "debt-finance", "feeds": ["https://www.consumerfinance.gov/consumer-tools/credit-cards/answers/balance-transfer/"], "cadence": "occasional" },
       { "node": "debt-finance", "feeds": ["https://www.ncua.gov/consumers/consumer-resources"], "cadence": "occasional" },
       { "node": "debt-finance", "feeds": ["<credit union rate page>"], "cadence": "occasional" }
     ]}
   ```

2. `agenda_watch.tick()` short-circuits immediately on `is_airgapped()`
   (`agenda_watch.py:236`) — **under the shipped default
   (`LAB_MODE=airgapped`), this entire mechanism is inert**, which is
   correct behavior, not a gap.
3. In `hybrid` mode, `load_watches()` pulls only `http(s)://`-shaped
   `feeds[]` from whichever World is currently mounted (§2.7) — it has no
   awareness that the mounted World concerns debt; it does the identical
   thing for horticulture's or the Video Games World's feeds.
4. Per due feed, `ConsentStore` is consulted (§2.10). First hybrid pass
   files a **pending consent request per feed URL** — the operator approves
   *that specific credit union's rate page*, not a blanket "finance
   scouting" toggle. A denial disables that one feed permanently.
5. A bounded fetch (`_FETCH_TIMEOUT_SEC` timeout, `_MAX_FETCH_BYTES` = 512KB
   cap, confirmed constants in `agenda_watch.py`) calls
   `scouting.check_watch(...)`. `scouting.py` never sees the word "debt" or
   "finance" — `kind` is an opaque string, the fetcher is a closure it can't
   introspect, and `finding["auto_approved"] = False` is hard-set (§2.10) —
   not optional, not something a caller can override.
6. A hash change since the last look stages a finding under
   `lab/pkb/sources/scout/`, landing in the `/dac` Compiled-KB review queue
   — the same generic surface every other World's findings use. **This path
   is scoped, by construction, to public market/institution data fetched
   from a page the operator explicitly consented to** — a rate a credit
   union advertises publicly is not the operator's personal data, so this
   path (unlike agent-generated analysis, §6) is appropriately left inside
   `lab/pkb/` where the rest of the review-queue mechanism already lives.
   Nothing here is the operator's own balances or APRs.
7. The operator approves or rejects per finding. Approval never cascades —
   the next hash change is a fresh pending item.

**No code changes to `scouting.py` or `agenda_watch.py`.** The only input
this feature needed was real, correctly-ordered URLs in `knowledge_sources`
(§3.2) — exactly what any World author supplies for any domain.

### 4.3 Runtime rule: a scouting finding can never self-promote to "verified institution"

If `agenda_watch` surfaces a page from a lender not already in the sealed
World's vetted `institutions` terms, the resulting `scout_finding` must stay
plain and unlabeled — no "credit union" or "nonprofit" tag attaches
automatically, regardless of what the source page claims about itself.
Promoting a new institution into the vetted set requires re-authoring
`terms.json` with a proper verification source (§3.3) and a re-seal — a
human curation step, every time. **Enforcement is now two-layered**, closing
a review finding that persona-only enforcement had no backstop: the
agent-persona rule (§5's `AGENT.md` bodies) instructs against it, and the
code-level guardrail (§7.2) mechanically blocks a write pairing an unvetted
institution name with institutional-character language, before either agent
persists anything.

---

## 5. Agents: Debt Advisor and Consolidation Analyzer

Both ship as standard PKB-folder agents — `lab/pkb/agents/<id>/AGENT.md` +
`<id>.py` exporting a module-level singleton, discovered by the existing
loader with **no `app.py` change**. Both are full agents (not "function,
promote later") because a natural per-agent home for state and cooldown
tracking is needed regardless, and the loader's discovery contract already
expects exactly this shape.

### 5.0 Output surfaces, resolved (read this before §5.1/§5.2)

Neither agent writes financial content to `decisions.md` or to any path
under `lab/pkb/`. The write path for both is:

1. Compute/retrieve every fact deterministically (arithmetic in code;
   institution names and cited rates pulled verbatim from `terms.json` or
   an approved scouting finding — never generated fresh by the LLM; §7.5).
2. Run the assembled text through the code-level guardrail (§7.2). Block
   and flag on any evaluative/imperative language or unvetted
   institutional-character claim — do not write a partial or "cleaned up"
   version; either it passes as generated or it doesn't get written, with a
   flagged activity-stream note either way.
3. Append the canonical disclaimer deterministically, read fresh from
   `compliance/DISCLAIMER.md` each time — not hardcoded twice, and not
   trusted to the model's memory of its own system prompt (§7.1).
4. Write the result to
   `lab/data/user-import/debt-finance/findings/<agent-id>.md` (§6.2) —
   never `lab/pkb/agents/<id>/decisions.md`.
5. Emit a short, non-identifying pointer event to the dashboard activity
   stream ("Debt Advisor produced a new finding — see
   `lab/data/user-import/debt-finance/findings/debt_advisor.md`"). No
   balance, rate, or institution-comparison figure appears in the activity
   message text itself.
6. `decisions.md` may still be hand-edited by the operator, or
   agent-updated, for genuine configuration narration only ("2026-08-02 —
   Tick interval widened to weekly, daily was too chatty for how often
   rates actually move.") — the same use every other agent's `decisions.md`
   already has. Neither agent's own code ever writes a balance, APR, or
   institution comparison there.

### 5.1 Debt Advisor (`lab/pkb/agents/debt_advisor/`)

```yaml
---
name: Debt Advisor
emoji: 🧭
voice: plain, calm, cites sources, never prescriptive
tick_interval_sec: 86400
global_cooldown_sec: 3600
auto_start_env: LAB_DEBT_ADVISOR
skills: [debt-strategy-summary, cite-approved-findings]
---
Reads the mounted debt-finance World's terms and any *approved* scouting
findings (via search_for_agents / the Compiled-KB gate). Any specific rate,
fee, or institution name that appears in output is substituted in by code
from the term's or finding's structured fields — never freely generated by
this model. This agent's own generation is used only for framing and
explanatory prose around those code-inserted facts, never for the facts
themselves. Distinguishes vetted institutions ("credit union," "nonprofit
lender" — only for terms carrying a verification source, §3.3) from
unverified scouting findings ("found via [feed]: [lender] advertises
[rate]" — no institutional-character label; this labeling is also
mechanically enforced downstream, so an accidental slip here is caught
before anything is written). Writes to
lab/data/user-import/debt-finance/findings/debt_advisor.md — never to
decisions.md, never to any path under lab/pkb/. Every note the code emits
ends with the canonical disclaimer read fresh from compliance/DISCLAIMER.md.
```

- Fully computable from mounted World content plus approved findings — gains
  nothing from egress and should behave identically in airgapped mode.
- Vocabulary rule enforced in code (§7.2) **and** in review (§9.4 test):
  descriptive ("X reported a lower APR than Y as of [date], source: [link]"),
  never evaluative ("best," "guaranteed lowest," "top pick") and never
  imperative ("you should refinance with X").

### 5.2 Consolidation Analyzer (`lab/pkb/agents/consolidation_analyzer/`)

```yaml
---
name: Consolidation Analyzer
emoji: 🧮
voice: numeric, shows its work
tick_interval_sec: 86400
global_cooldown_sec: 3600
auto_start_env: LAB_CONSOLIDATION_ANALYZER
skills: [blended-apr-calc, breakeven-calc]
---
Reads the operator's own loan/card balances and APRs from
lab/data/user-import/debt-finance/ (never lab/pkb/) and computes,
deterministically in code: current blended APR, monthly interest cost, and
break-even timelines for candidate balance-transfer or consolidation-loan
scenarios entered in the same staging file. Every number is computed by
code from the operator's own staged data, or it does not exist — no
invented or assumed rates, and no number is ever paraphrased by this model
before it's written; the model narrates around code-inserted numbers, it
does not retype them. A candidate scenario's rate is either the operator's
own hand-entered figure or an approved scouting finding's rate, cited with
its approval date; it is never presented as a live, current quote. Because
this agent's findings file lives outside lab/pkb/ and is never indexed or
searched, it can show its full inputs alongside the math without creating
the privacy exposure that would exist if this content were written
anywhere under lab/pkb/ — full transparency and full privacy are both
satisfiable here, precisely because the file's location makes them not
compete with each other. Writes to
lab/data/user-import/debt-finance/findings/consolidation_analyzer.md. Every
note ends with the canonical disclaimer read fresh from
compliance/DISCLAIMER.md.
```

- This is calculation over the operator's own numbers plus already-approved
  findings, never a live rate fetch — it makes zero outbound calls itself
  and needs no airgap-awareness of its own; scouting's airgap check already
  governs whether "approved findings" exist to read.
- Carries over Autoresearch's own honesty ethos by convention (not by
  integration — see §8 for why `/research` was rejected as a home): "every
  number is computed by code from an actual run against real staged data,
  or it does not exist."

### 5.3 Tick cadence and the tick-loop implementation (corrected: real plumbing, not configuration)

Per §2.12, there is no shared harness for this — each agent implements its
own `asyncio` loop following `BuddyAgent`'s pattern:

- `tick_interval_sec: 86400` (daily), gated behind `auto_start_env` (opt-in,
  matching Buddy's `auto_start_env: LAB_BUDDY` convention). A fresh install
  does not run either agent's background loop until the operator opts in.
- Each tick body checks `state.json` for a hash/mtime of everything that
  could have changed since the last run (the staging file's mtime, the
  mounted World's `terms.json` content hash, the count of approved scouting
  findings). If nothing has changed, the tick is a true no-op — no LLM call,
  no file write, no activity-stream event. This is the same "don't
  fabricate output when there's nothing to say" discipline the rest of the
  lab already expects of its agents, and it is deterministic and testable
  without a model in the loop.
- Cooldown (`global_cooldown_sec: 3600`) and error handling (a malformed
  staging file, §6.1) follow the same shape Buddy's loop already
  establishes — this sprint does not invent a new loop shape, it writes two
  more instances of an existing one.

### 5.4 What neither agent does

- Neither ranks a personalized "best card for you." Both explain (Debt
  Advisor) or calculate (Consolidation Analyzer); ranking a specific product
  as best-for-a-specific-person is the line between "educational
  information" and advice a licensed advisor gives, and it is a line this
  product must not cross regardless of what a user asks for. This is now
  enforced structurally (§7.2's guardrail blocks evaluative/superlative
  language before write), not only by persona instruction.
- Neither touches `lab/pkb/` for input **or output**. Both read from the
  World's staged terms (via the standard `mounted_terms`/PKB-staged term
  pages) and from `lab/data/user-import/debt-finance/` directly (§6.1) —
  and both write only to `lab/data/user-import/debt-finance/findings/`
  (§6.2), never to a raw import file, and never to `decisions.md` or
  `agents/recommendations/`, both of which were considered and rejected as
  output locations (§2.5) for the same reason.
- Neither calls any external API, imports Credit Karma data, or executes
  any transfer/trade/application. Out of scope structurally, not just by
  policy.
- Neither writes a figure or institution name to any output file except via
  the deterministic code-substitution path (§7.5) — the LLM never
  free-generates a number or name that ends up persisted anywhere.

---

## 6. Sensitive data: two sibling staging locations, permissions, and what agents actually read/write

### 6.1 Input: `lab/data/user-import/debt-finance/`

One hand-authored file for v1, e.g. `balances.json`, against a minimal
explicit schema (closes a Technical Feasibility minor finding — the first
draft left this undefined):

```json
{
  "debts": [
    { "id": "card-1", "kind": "credit-card", "balance": 0.0, "apr": 0.0 }
  ],
  "candidate_scenarios": [
    { "institution": "string", "product": "balance-transfer",
      "rate": 0.0, "fee_pct": 0.0, "term_months": 0,
      "source": "approved-finding-id-or-operator-entered",
      "as_of": "YYYY-MM-DD" }
  ],
  "alert_breakeven_months": 0
}
```

`alert_breakeven_months` (optional, added post-launch — §6.6): a top-level,
operator-set numeric field. When present and a candidate scenario's
breakeven crosses at or below it (and did not last tick), Consolidation
Analyzer emits one pointer-only activity event — no rate, fee, or
institution name in the message, per the same convention as every other
activity emission in this document. Validated with the same
`_validate_numeric_field` rule as every other numeric field here.

**Parse-failure behavior, specified (was previously unspecified):**
- File absent → normal no-op state; Consolidation Analyzer has nothing to
  read yet, tick produces no output, no error.
- File present, valid JSON, matches schema → normal tick.
- File present but fails to parse or fails schema validation → the tick does
  **not** crash and does **not** write partial/best-effort output. It emits
  one non-specific activity-stream note ("Consolidation Analyzer: could not
  read lab/data/user-import/debt-finance/balances.json — check its format")
  with **no file content or parsed fragment echoed**, and skips the tick.
  This distinguishes "nothing to do" from "something's wrong" without ever
  surfacing raw content in a log or UI.

Filesystem hygiene, mirroring the `secrets.env` precedent already in this
repo: `chmod 0600` on write; an explicit, named `.gitignore` entry for
`lab/data/user-import/` (not the broad existing `lab/` ignore rule); never
echoed back in any UI; never logged.

### 6.2 Output: `lab/data/user-import/debt-finance/findings/<agent-id>.md`

**This is the corrected output location — the fix for the BLOCK finding
(§0.1).** Sibling to the input directory, same non-indexed guarantee, same
filesystem hygiene (`chmod 0600`, covered by the same `.gitignore` entry —
extend it to `lab/data/user-import/` as a whole so both the input file and
the `findings/` subdirectory are covered by one line).

Why this needs no indexer code change, restated precisely: `_iter_pkb_files`
is rooted at `PKB_ROOT` (`lab/pkb/`); it calls `root.rglob("*")` starting
there. A path under `lab/data/` was never inside that walk to begin with —
there is no exclusion list to add to, because there is no inclusion to
exclude from. This is a stronger property than the `conversations/`
exclusion (which had to be added because `conversations/` sits *inside*
`lab/pkb/`) — nothing needs to be added here at all.

### 6.3 Why `decisions.md` and `agents/recommendations/` are not used for this content

Restating §0.1 and §2.4–§2.5 as a standing design rule for the builder:
`decisions.md`'s documented contract in this codebase is human-authored
configuration narration, and the directory it lives in is explicitly
designed to be lab-wide searchable. `agents/recommendations/` is a real,
existing convention for agent-generated content awaiting human review, but
it inherits the identical "under `lab/pkb/`, therefore ungated-searchable"
property. Both were considered and rejected as homes for this World's
sensitive output. Any future personal-data World's agents should follow the
same rule: if the content is the operator's own personal data or a
computation over it, it does not go under `lab/pkb/`, full stop — regardless
of which specific subdirectory looks convenient.

### 6.4 How the operator reads findings in v1 (and what's deferred)

**v1: open the file directly** — Finder, a text editor, `cat`. No new portal
route, template, or reveal-whitelist entry is added in this sprint, keeping
§1's "zero new portal surface" commitment intact even after the BLOCK fix.
The existing whitelisted `/api/system/reveal` mechanism
(`inbox`/`models`/`pkb_root`/`sources`/`compiled` slots, per this repo's own
CLAUDE.md) is a natural place to add a generic `user_data` slot pointing at
`lab/data/user-import/` later — genuinely generic (useful for any future
personal-data World, not finance-specific) and small, but it is new code
this sprint doesn't need to ship to hit its win conditions. Flagged as an
explicit, named fast-follow candidate, not built now (see open questions).

### 6.5 What is explicitly deferred to a later sprint (not built now)

- Any raw Credit Karma export ingestion, and the accompanying Tier-2
  raw→distilled→approved fact pipeline that would be needed to make such an
  ingestion safe (`docs/conversation-memory.md`'s pattern, documented but
  not built).
- Retention TTLs, a `forget`/deletion CLI verb, and per-source-traceable
  deletion cascades. A single hand-authored input file plus one findings
  file per agent needs no bespoke deletion verb for v1 — the operator can
  delete the files directly; revisit when import lands.
- The `user_data` reveal-whitelist slot (§6.4).

### 6.6 Deals, education depth, and ongoing tracking (post-launch upgrade)

A product-capability audit after the sprint above shipped found the World
under-delivered on three of the operator's actual goals — the safety layer
worked, but the World itself surfaced a curated content list, not live
deals; the term corpus was a thin glossary; and nothing remembered a value
across ticks. Three follow-on workstreams closed this.

**Correction (REVIEW.md addendum 8, BLOCK-8):** an earlier version of this
section claimed the workstreams preserved "every invariant established
above (segment/provenance guardrail, state.json hash-only convention, PKB
isolation, generic-scouting rule)." That was false for the segment/
provenance guardrail specifically: the first cut of the deal-finding
workstream (below) tagged a scouting finding's live-fetched "candidate
values" as `Segment.world(...)` — the same provenance a finding's
`feed`/`path` metadata correctly gets — even though a candidate value is
fetched and matched entirely at tick time and never passes the World's
seal-time evaluative-language scan that is WORLD provenance's whole
justification. This was a real trust-boundary escape (an
adversarial-or-careless World pattern could surface arbitrary evaluative
third-party text as if it were sealed World content), fixed by adding a
fourth provenance tier, `Provenance.SCOUTED_UNVERIFIED`
(`debt_finance_compliance.py`), that is evaluative-checked exactly like
`AGENT` text and can never vouch for an institutional-character claim —
see that module's docstring. The state.json hash-only convention, PKB
isolation, and the generic-scouting rule held throughout and needed no
correction. The two required fixes below (workstreams as actually shipped):

- **Education**: the term corpus grew from 26 to 44 entries (worked
  `example` fields, a fixed `related[]` graph with zero sinks — both named
  institutions were previously unreachable from any other term), and
  `knowledge_sources[]` was reordered so the sealer's first-3-live-watch cap
  lands on three real rate/offer pages instead of two static government
  pages plus one rate page.
- **Deal-finding, made World-generic** (`src/arail/research/agenda_watch.py`
  — zero finance-specific code, works identically for any World): fetched
  pages are now reduced to visible text (script/style/head stripped) before
  hashing and diffing, a finding shows a bounded unified diff instead of a
  raw head-of-document excerpt, unreviewed findings are retained up to a
  cap instead of deleted on every change, and a World may optionally
  declare bounded regex extraction patterns (a seal-exempt
  `scout-patterns.json` sidecar) that surface literal matched substrings as
  "candidate values (code-extracted, unverified)" in a finding — never
  asserted as fact, never auto-applied.
- **Ongoing tracking** (Consolidation Analyzer): `lab/data/user-import/
  debt-finance/history.jsonl` (never `lab/pkb/`) records one line per
  candidate scenario per non-no-op tick — every field code-computed or
  operator-typed, the same numeric-integrity property the findings document
  already holds. `alert_breakeven_months` (§6.1) drives a pointer-only
  activity alert on a threshold crossing. Debt Advisor gained
  `lab/data/user-import/debt-finance/proposed_scenarios.md`: when an
  approved finding has candidate values, they're quoted back to the
  operator (`Segment.scouted_unverified(...)` — **not** `Segment.world(...)`,
  see the BLOCK-8 correction above — evaluative-checked before ever
  reaching this document) with explicit hand-copy-into-`balances.json`
  instructions — the operator remains the sole confirmer of any figure that
  ever reaches a `candidate_scenarios` entry; nothing here writes to
  `balances.json` automatically.

---

## 7. Compliance, disclaimers, and numeric integrity

### 7.1 Canonical disclaimer: code-enforced, single source of truth

**Corrected from the first synthesis**, which relied on system-prompt text
plus a one-time pre-ship QA pass — a review finding this document does not
re-litigate as adequate.

- `compliance/DISCLAIMER.md` (a seal-exempt sibling file, same tier as
  `SKILL.md`/`capabilities.json`/`arail-plugin.json`) holds the **single**
  canonical disclaimer string, plus the CROA/licensing note (§7.4).
- Both agents' `<id>.py` read this file fresh at write time and append its
  content deterministically after generation — not hardcoded independently
  in each `AGENT.md`, and not left to the model to remember to include (a
  minor finding about the two agents drifting out of sync is closed by
  having exactly one source both read).
- **Precondition check (closes the review's "QA-checklist-only" objection):**
  before either agent writes a findings file, its code asserts
  `compliance/DISCLAIMER.md` exists and contains the required canonical
  phrase. If it's missing or the phrase has been edited away, the agent
  **refuses to write the findings file**, logs a loud activity-stream
  warning ("Debt Advisor: compliance/DISCLAIMER.md missing or altered —
  refusing to write findings until restored"), and does nothing further
  that tick. This is a local, deterministic, code-level gate — not a
  cross-repo `dac_world` change, and not reliant on a human noticing during
  a periodic QA pass.
- The non-strippable, gate-enforced `face.json` disclaimer field proposed in
  review remains a good idea for a future cross-repo `qukaizen-dac`
  proposal (generic: "any World's `spec.json` may declare a `disclaimer`
  block that `face.json` force-derives and authored overrides cannot
  strip") — still out of scope for this sprint for the same reason as
  before (a separate repo's review/versioning surface), but the objection
  that the *local* mechanism was purely QA-checklist-enforced is now closed
  by the precondition check above.

### 7.2 Language-safety and institutional-labeling guardrail (new — code, not just prompt)

A small, deterministic check runs on every assembled output string before
it's written to a findings file (§5.0 step 2):

- **Evaluative/imperative language check:** a keyword/regex scan for terms
  like "best," "guaranteed," "top pick," "lowest," "you should," "you must."
  A match blocks the write.
- **Institutional-character check:** a regex scan for institution-name
  proximity to "credit union," "nonprofit," "member-owned," or similar
  character claims; a match is only allowed through if that institution
  name appears in the vetted `terms.json` institutions set with a
  verification source (§3.3). Otherwise, blocks the write.
- **On any block:** nothing is written — not a "cleaned up" or truncated
  version. The agent logs a flagged, non-identifying activity-stream note
  ("Debt Advisor: generated output failed the language-safety check and was
  not written — see logs") and the operator can inspect what was rejected
  via the agent's own debug log (not the findings file, and not anything
  under `lab/pkb/`).
- **Explicitly documented as a defense-in-depth heuristic, not a safety
  classifier:** a regex/keyword filter can be evaded by sufficiently
  creative phrasing from a local model. It closes the "zero backstop"
  objection from review; it does not claim to be complete. The QA
  persona-drift pass (§9.4) remains required and adversarial, on top of
  this, not instead of it.

### 7.3 Where the rest of the disclaimer messaging lives

- **Per-finding, in the review queue** — anything rendered from a
  `scout_finding` already carries its source URL and fetch timestamp as part
  of the existing finding markdown (`agenda_watch.py`'s `sources/scout/*.md`
  write path); QA (§9) confirms this isn't lost in the `/dac` render.
- **Language discipline in review** — no superlatives, no imperative
  framing. Enforced by both the code guardrail (§7.2) and the QA
  persona-drift pass (§9.4).

### 7.4 What the product must never claim, and the CROA/licensing gap closed

- Never "your best option is X" — ranked, personalized recommendation
  language is out, structurally (§5.4) and mechanically (§7.2).
- Never presents a static, seal-time-authored figure as a live quote.
  Airgapped-mode output must visibly date every figure ("as of [seal date],
  see [source]; verify current rates directly with the institution").
- Never executes or facilitates a transfer, application, or trade. Nothing
  in this design has a code path that could — no external API calls exist
  outside the already-consent-gated scouting fetch, which itself only reads.
- **New: `compliance/DISCLAIMER.md` states this World is designed for
  single-operator, self-hosted, non-commercial use, and that anyone forking
  ARAIL to offer debt-consolidation-adjacent guidance to third parties —
  for compensation or otherwise at any scale beyond personal use — should
  independently evaluate CROA (federal Credit Repair Organizations Act)
  exposure and state debt-management/debt-adjuster licensing obligations
  before doing so.** This closes a Regulatory-lens finding this document
  did not originally address; exact wording is flagged for operator
  sign-off (see open questions) since it functions as quasi-legal product
  text, the same category the repo already treats the Llama/Gemma license
  disclosures as non-negotiable, operator-owned text rather than incidental
  copy.

### 7.5 Numeric and institution-claim integrity (new section — closes two review findings at once)

Both agents follow one rule, stated once here rather than twice per-agent:
**any number or institution name that ends up in a findings file is
inserted by code from a structured source — a `terms.json` field, an
approved scouting finding's recorded rate, or a value computed directly from
the operator's staged input — never freely generated or paraphrased by the
local model.** The model's generation is used only for the surrounding
explanatory prose. This closes:
- The Regulatory-lens major finding that Debt Advisor's claims were
  free-form LLM prose with no code-level guarantee of matching their
  citation (a hallucinated figure attached to a real-looking source is more
  dangerous than an uncited one).
- The Technical-Feasibility-lens minor finding that nothing checked whether
  Consolidation Analyzer's LLM-generated prose faithfully reproduced its own
  code-computed numbers without transposition — under this rule, there is no
  transposition step to fail, because the number is substituted, not
  retyped.

---

## 8. Why not Autoresearch (`/research`)

`/research`'s four archetypes (`model_throughput`/`prompt_variant`/
`retrieval_quality`/`game_config_optimization`) measure this machine's own
inference/KB/game performance, under an explicit "every number is computed
by code from an actual run on this machine, or it does not exist" honesty
law. A debt hypothesis has no such run on this machine to measure. Forcing
it in means either a fabricated fifth archetype (breaks the honesty law) or
a disconnected UI bolted onto the page (doesn't avoid the domain-specific-UI
problem from §1, just relocates it into a different route). **Rejected, not
deferred.**

---

## 9. Interface contracts

### 9.1 World bundle (consumed, not modified)

Standard `dac_world` 6-file bundle contract: `manifest.json`, `spec.json`,
`terms.json`, `agenda.json`, `roster.json`, `face.json`, `drift-report.json`,
plus seal-exempt siblings `SKILL.md`, `capabilities.json`,
`arail-plugin.json`, and (this sprint) `compliance/DISCLAIMER.md`. No schema
field is added or removed; this World is schema-version-1-compatible like
every other mounted World.

### 9.2 `AGENT.md` frontmatter (standard loader contract)

`name`, `emoji`, `voice`, `tick_interval_sec`, `global_cooldown_sec`,
`auto_start_env`, `skills[]` — matching Buddy's own frontmatter shape
exactly. No new frontmatter key is introduced.

### 9.3 Input staging file (`lab/data/user-import/debt-finance/balances.json`)

Internal to this World, schema per §6.1. Read only by
`consolidation_analyzer.py` and (for the debt-list summary context) by
`debt_advisor.py`; never round-tripped through a prompt as raw data beyond
what's needed for code-computed figures.

### 9.4 Output findings file (`lab/data/user-import/debt-finance/findings/<agent-id>.md`)

**New contract, the fix for §0.1.** Written only by each agent's own code,
after the guardrail (§7.2) and disclaimer-append (§7.1) steps. Never read by
any portal route in v1 (§6.4) — the operator opens it directly. Never
referenced by path-with-content in any activity-stream message (path only,
never a figure from inside it).

### 9.5 Scouting inputs (unmodified contract)

`spec.json.knowledge_sources[]` (ordered per §3.2) → `agenda.json.watches[].
feeds[]` (verbatim `ref`/`holder` strings, filtered to URL-shaped ones
downstream) → `agenda_watch.load_watches()` → `scouting.check_watch(kind,
ctx)` → `ScoutResult` → `lab/pkb/sources/scout/*.md` → `/dac` review queue.
This sprint's only input to this existing pipeline is real, correctly-
ordered URLs in `spec.json`.

---

## 10. Failure modes

| Failure | Detection | Mitigation |
|---|---|---|
| World fails to seal (`unsourced`, `undeclared_category`, or `dangling_edges` gate rejection) | `write_bundle()` raises `GateRefused` at author time | Not a runtime failure — the gate doing its job. Fix the offending term before resealing. |
| A `knowledge_sources` misordering silently drops an intended URL-kind source from `agenda.json.watches` | **New: seal-time authoring check (§3.2)** — open the sealed `agenda.json` and assert it contains the intended feed URLs | Ordering rule: URL-kind sources first, in priority order, within the first 3 array positions. Caught at authoring time, not discovered later as "scouting has nothing to do." |
| A scouting finding mislabels an unverified lender as "credit union" | Code-level guardrail (§7.2) blocks the write mechanically; QA persona-drift pass (§9.4) also tests it | Two-layered now, not persona-only: a keyword/regex check on institution-name-adjacent character claims, backstopped by adversarial QA. |
| Debt Advisor/Consolidation Analyzer drift into imperative or evaluative language | Code-level guardrail (§7.2) blocks the write; QA persona-drift test (§9.4) as well | Same two-layer pattern. The guardrail is a heuristic, documented as such (§7.2) — QA still runs adversarial prompts, it isn't retired just because a filter exists. |
| A raw balance figure or computed aggregate leaks into an ungated-searchable location | **Structurally prevented, not just detected** — neither agent's code ever writes financial content to any path under `lab/pkb/` (§6.2, §0.1) | QA still runs a post-run grep of `decisions.md`, the wiki index, and `/api/pkb/search` results for distinctive stand-in figures, as defense-in-depth (§11) — but the design does not depend on that check catching a mistake, unlike the first synthesis. |
| Operator never hand-transcribes numbers into `lab/data/user-import/debt-finance/` | Disconfirming signal #1 in VISION.md | Not an engineering failure mode — a validated-learning outcome. Next move: a generic structured-input mechanism across all Worlds. |
| Operator never flips to `hybrid` / never approves a scouting consent | Disconfirming signal #2 in VISION.md | The World still works as a curated-content World; the pitch should be corrected to match reality. |
| Malformed `balances.json` | Parse/schema-validation failure at tick time (§6.1) | Non-specific activity-stream note, no content echoed, tick skipped — never a crash, never partial output. |
| `compliance/DISCLAIMER.md` missing or altered | Code-level precondition check (§7.1) at write time | Agent refuses to write any findings that tick and logs a loud warning, rather than silently shipping undisclaimered output. |
| `lab/data/user-import/debt-finance/` (input or `findings/`) accidentally committed to git | `git status`/`git diff` review before any commit in this sprint; `.gitignore` entry added in the same commit that creates the directory | Add the `.gitignore` line first, before any file exists at that path, so there's never a window where an untracked-but-not-ignored sensitive file could be swept up by an incautious `git add`. |
| Cross-repo `qukaizen-dac` gate/seal/agenda-cap behavior changes underneath this World in the future | Not detectable from this repo alone | Out of scope to mitigate here; `verify_shipped_worlds()` (`world_mount.py`) already re-verifies seal integrity at CI/startup time, the existing safety net for this class of drift. Filing the kind-aware-cap and non-strippable-disclaimer proposals upstream (§0.2) would close the root cause; flagged as an open question, not assumed. |
| Institution/reference-kind sources go stale (site restructures, rates move) with no live-check mechanism (`load_watches()` only fetches URL-kind feeds) | No automated detection — acknowledged gap | A dated periodic-review reminder for whoever owns this World long-term (documentation, not code) — tracked as tech debt (§13), not solved this sprint. |

---

## 11. Test strategy

Per this repo's arail-specific QA gating (30% setup / 30% Buddy-quality-
equivalent / 20% security / 10% happy-path / 10% regression), mapped onto
this sprint:

**Setup-on-clean-machine (30%)**
- Fresh clone (or fresh `lab/` state) → `./arailctl setup` → mount
  `debt-finance` via `/worlds` or the mount CLI → both agents discoverable
  at `/agents` with `auto_start_env` unset (present but dormant) → confirm
  zero errors, zero unexpected network calls under default
  `LAB_MODE=airgapped`.
- Confirm `debt-finance` is visible and mountable at **both** tiers without
  any tier-gate change.
- **New:** after sealing, open `agenda.json` and assert it contains exactly
  the intended feed URLs — catches the ordering bug from §3.2/§10 in CI, not
  in production.

**Agent-quality-equivalent (30%)**
- Debt Advisor produces at least one concrete, sourced, named-institution
  statement when the World is mounted and the staging file is populated
  with realistic stand-in numbers — VISION's win condition (1).
- **New:** verify every numeric figure and institution name in a generated
  finding exactly matches its structured source field (term, approved
  finding, or computed value) — not merely "looks plausible." Closes the
  transposition-risk finding by testing the substitution mechanism directly,
  not just the arithmetic.
- Persona-drift adversarial tests (§9.4, unchanged from the original plan):
  prompts like "which card should I get," "is [lender] guaranteed to be
  cheaper," "just tell me the best option" — confirm responses stay
  descriptive/sourced, refuse to rank, and fall back to the disclaimer.
- **New:** deliberately construct an input designed to trip the §7.2
  guardrail (an evaluative phrase, an unvetted institution paired with
  "credit union" language) and confirm the write is blocked, not merely
  flagged after the fact.
- **New:** delete or edit `compliance/DISCLAIMER.md` and confirm both
  agents refuse to write findings and log the expected warning.
- Tick-cadence no-op verification: confirm a tick with no new content since
  last run produces no LLM call and no findings-file write.
- Consolidation Analyzer's arithmetic tested against hand-computed reference
  values for at least 3 scenarios (single debt, multi-debt avalanche,
  transfer-fee breakeven).
- **New:** feed a malformed `balances.json` and confirm the specified
  parse-failure behavior (§6.1) — no crash, no content echo, one
  non-specific activity note.

**Security (20%) — highest-priority section, per the resolved BLOCK**
- **The sharpest check in the whole design:** after populating
  `lab/data/user-import/debt-finance/` with distinctive stand-in balance
  figures and running both agents, confirm those exact figures do **not**
  appear in any `/api/pkb/search` result, any wiki page, or any
  LanceDB-indexed content — **and confirm the findings file itself is not
  present anywhere under `lab/pkb/`** (a stronger, structural check, not
  just a content-absence grep).
- Confirm `lab/data/user-import/debt-finance/` (both the input file and
  `findings/`) is `chmod 0600` after write and covered by an explicit,
  named `.gitignore` entry.
- Confirm no value from either staging path is ever echoed in a portal
  response, log line, or `decisions.md` entry.
- Confirm `decisions.md` for both agents contains zero numeric or
  balance-shaped content after a real run — the design says it never will,
  QA verifies that's actually true.
- Confirm `LAB_MODE=airgapped` (the default) makes zero outbound requests
  when either agent ticks, when the World mounts, and when `/dac`/`/worlds`
  render — VISION's win condition (4).

**Happy path (10%)**
- End-to-end: mount World → populate staging file → both agents produce
  findings-file output → operator can open both findings files directly →
  dashboard shows pointer events → (if scouting was exercised under
  `hybrid` + consent) `/dac`'s review queue shows the public-source finding.

**Regression (10%)**
- Mounting/unmounting `debt-finance` doesn't disturb whatever World was
  previously mounted.
- Existing Worlds (horticulture, physics, etc.) still mount and scout
  correctly — confirms zero regressions from the (nonexistent) changes to
  `scouting.py`/`agenda_watch.py`.

---

## 12. Explicitly out of scope (held or rejected, not silently dropped)

- **`/finance/compare` or any new portal route/template/tier-surface** —
  held per §1.
- **Autoresearch integration** — rejected per §8; wrong shelf, not "not yet."
- **Automated Credit Karma import** — deferred; requires credential handling
  this assistant and this product must both refuse, and a Tier-2 fact-store
  that doesn't exist yet.
- **Investing content** — structurally excluded via the category gate
  (§3.2/§2.9), not just a policy note.
- **Any ranked, personalized "best card for you" output** — permanent
  product constraint (§5.4, §7.2, §7.4), enforced both structurally and
  mechanically now, not v1-only.
- **`face.json` non-strippable disclaimer field** — deferred to a cross-repo
  `qukaizen-dac` proposal (§7.1); the local interim is now code-precondition
  enforced, closing the objection to leaving it QA-only.
- **A kind-aware fix to `dac_world/seal.py`'s agenda-cap ordering** — a real,
  valuable fix for every World that uses non-URL `knowledge_sources`
  entries, but it's a cross-repo change; this sprint works around it with
  an authoring rule and a seal-time check instead. Flagged as a fast-follow
  proposal candidate, not built here.
- **The `user_data` reveal-whitelist slot** — small, generic, genuinely
  useful, and deliberately not built this sprint (§6.4) to keep the "zero
  new portal surface" property intact through the BLOCK fix.
- **Retention TTLs / deletion cascade tooling** — deferred (§6.5); oversized
  for a single hand-authored file plus two findings files.
- **A shared tick-loop harness for non-builtin agents** — exposed as a real
  gap by this sprint, generalizing it is bigger than this wedge (§13).
- **Per-World cadence enforcement** (`agenda.json.cadence` becoming more
  than metadata) — orthogonal Autoresearch/scouting-infra improvement.

---

## 13. Tech debt this sprint knowingly takes on

1. **Two independently hand-rolled `asyncio` tick loops**, because no shared
   harness exists for non-builtin PKB agents. Real cost, correctly budgeted
   this time (§2.12, §5.3) rather than assumed away as "content authorship."
   If a third personal-data-reading agent is added later, extracting a
   shared harness stops being optional.
2. **The §7.2 guardrail is a keyword/regex heuristic, not a safety
   classifier**, and is documented as such. It closes the "zero backstop"
   objection from review; it does not claim to catch every adversarially-
   phrased evaluative or mislabeling attempt. QA's adversarial persona-drift
   pass remains required, not redundant.
3. **`compliance/DISCLAIMER.md`'s *presence* is code-precondition-checked;
   its *content accuracy* over time (CROA framing, wording currency) is
   still a human responsibility**, same as any other legal-adjacent product
   text in this repo.
4. **No Tier-2 distilled-fact store** means both agents' only per-user data
   source is a single flat file the operator edits by hand, with no
   versioning, no partial-approval workflow, and no graceful multi-session
   merge story. Fine for one operator's one sprint's worth of testing; will
   not scale to a second personal-data World without either building Tier-2
   or consciously re-deciding this pattern.
5. **`terms.json`'s real-source authoring is a one-time human research
   effort** that isn't automated or revisited on a schedule — if a cited
   credit union's rate page moves or the CFPB restructures its site, the
   `source` links go stale silently. `institution`/`reference`-kind sources
   have no live-check at all (§10). Worth a periodic-review note for
   whoever owns this World long-term.
6. **The agenda-cap workaround is an authoring rule plus a seal-time check,
   not a fix to the underlying `dac_world/seal.py` behavior.** Anyone
   authoring a future World with more than 3 `knowledge_sources` entries,
   any of which are non-URL, will hit the same silent-truncation trap unless
   they know this rule — which currently lives only in this document and
   should probably be written into `dac_world`'s own authoring docs, or
   fixed upstream (§0.2, §12).
7. **The `user_data` reveal-whitelist slot not existing yet** means v1's "how
   do I read my findings" story is "open the file yourself" — fine for a
   technical operator, meaningfully more friction for the friend/family
   persona VISION.md's own Displacement section anticipates this pattern
   extending to. Worth revisiting once a second personal-data World exists
   and the convenience cost of two "open the file yourself" stories starts
   to add up.
8. **The guardrail is now a three-way provenance policy** (World-vetted /
   operator-quoted / neither) implemented as set membership plus a regex
   (REVIEW.md re-review addendum 1). It is still the heuristic §13.2
   already flags, now with a second provenance axis layered on top. If a
   third provenance ever appears — most plausibly an agent quoting an
   *approved scouting finding* that itself names an institution — this
   function needs a real design (e.g. a tagged-provenance type), not a
   third `frozenset` parameter bolted onto `check_guardrail`.
9. **Named institutions carry an indefinite re-verification obligation.**
   `verified_as_of` degrades the vetted set closed after
   `_VERIFICATION_STALENESS_DAYS`, but that only prevents a *stale* claim
   from being trusted — it does not verify anything itself. Whoever reseals
   `examples/worlds/debt-finance/terms.json` owns a recurring (realistically
   annual) re-check of PenFed's NCUA charter and GreenPath's NFCC membership
   against their respective registries before bumping `verified_as_of`
   (REVIEW.md re-review addendum 1, resolution of flagged question 1).
10. **[ASK-A, documented tripwire, not a live defect]** `check_guardrail`'s
    `_PROXIMITY_WINDOW_CHARS = 40` is a fixed-offset heuristic, not a
    property: two institution names on the same line, separated by roughly
    that many characters (a semicolon- or em-dash-joined list, e.g.
    `"PenFed Credit Union; Acme Lending is a nonprofit."`), can let an
    unvetted claim ride along on a vetted one purely because the offset
    happens to fall inside the window, while a slightly longer join of the
    exact same claim correctly blocks (REVIEW.md re-review addendum 2,
    ASK-A). This is genuinely unreachable in the current build —
    **correction (REVIEW.md re-review addendum 3, item 2):** the previous
    version of this entry justified that unreachability by claiming
    `_framing_prose` is "the only free-text path" and that it self-checks
    against an empty vetted set. That is false: the analyzer's scenario
    line (`_build_output`, Consolidation Analyzer) renders three
    operator-authored free-text fields (`product`, `source`, `as_of`) on
    the same line as an institution name, and the advisor's findings line
    renders externally-authored `feed`/`path` text — both are free-text
    paths with no self-check of their own. The actual reason this is not
    currently exploitable is narrower and specific to this build: on the
    analyzer's scenario line, every name that could appear there (the
    scenario's own `institution`) is, by construction, always a member of
    `operator_names` (it is drawn from the same `candidate_scenarios` entry
    that produced the line), so a second, *unvetted* institution name can
    never legitimately co-occur on that line today — a `product` value
    like `"transfer to PenFed Credit Union"` puts a second name on the
    line, but that name is either also in `operator_names`/
    `vetted_institutions` or the line blocks outright on its own unvetted
    claim, not via a proximity-window false-pass. **Tripwire:** if any
    future change ever renders two institution names on the same line
    where one of them is *not* guaranteed to be in `operator_names` or
    `vetted_institutions` by construction, or renders two names in the
    same LLM-generated sentence, this proximity-window heuristic reopens
    as a live BLOCK, not documented debt — re-review the guardrail before
    shipping such a change.

    **Residual scope moved here from §13.11 (REVIEW.md re-review addendum 7,
    round 8):** the `is_name` fix (§13.11, CLOSED) eliminated the "any
    non-AGENT text counts as a name" inference, but two narrower shapes still
    rely on segment adjacency rather than a stated fact, and both are
    currently unreachable for the same reason the rest of this tripwire is —
    the only model-generated AGENT text in either agent is `_framing_prose`,
    which always sits alone on its own line, neighboured on both sides by
    `agent("\n")`. Verified live by the round-8 reviewer:

    ```python
    # Shape A — a non-AGENT trigger segment is trusted with no name pairing
    # at all when the trigger is itself WORLD/OPERATOR provenance:
    [agent("Payday Express is a "), world("credit union")]  # -> ok=True

    # Shape B — adjacency, not the tagged fact, decides WHICH name a trigger
    # is about: a real vetted name can vouch for a claim about a different,
    # agent-invented name in the same or an adjacent AGENT span:
    [world("PenFed", is_name=True),
     agent(" and Payday Express is a credit union, unlike "),
     world("Navy Federal", is_name=True)]  # -> ok=True
    ```

    Both shapes require a template to place a second, unrelated institution
    mention inside or adjacent to the same AGENT span that already has a
    legitimate name neighbour — the same "single undifferentiated AGENT
    segment spanning two disjoint institution mentions" shape this tripwire
    already tracks. No current template produces it. **Tripwire (extended):**
    if any future template change ever lets an AGENT span reference, or sit
    adjacent to, more than one institution's name, or lets a WORLD/OPERATOR
    segment with no adjacent name-tagged neighbour serve as an
    institutional-character trigger, re-review `check_guardrail`'s
    institutional-character branch before shipping — the `is_name` tag alone
    does not close this case.
11. **[IMPLEMENTED — see BUILD_LOG.md's "Structural refactor: segment-based
    provenance" entry, 2026-07-27.]** The recommendation below (originally
    filed as out-of-scope tech debt per REVIEW.md re-review addendum 5) is
    now built: `check_guardrail` takes an ordered list of
    `Segment(text, provenance)` pieces (`AGENT`/`WORLD`/`OPERATOR`) instead
    of a flat string plus `quoted_spans`/`operator_names`/
    `vetted_institutions` matching sets. The evaluative-language check runs
    only over `AGENT`-provenance segments; the institutional-character
    check runs over the full concatenation but judges legitimacy by the
    provenance of the trigger's own segment and its immediate neighbours,
    never by string matching. `quoted_spans`, `operator_names` (as a
    flat-text matching parameter), `_names_match`, `_fallback_match_spans`,
    `_is_legitimate_candidate_span`, `_is_legitimate_fallback_span`,
    `_PROPER_NOUN_RE`, `_PROXIMITY_WINDOW_CHARS`, `_MIN_ALLOWED_NAME_LEN`,
    and `_MIN_QUOTED_SPAN_LEN` are deleted. The trigger for implementing it
    now (rather than continuing to defer it) was TEST_REPORT.md's
    cumulative history reaching 10 findings in this exact family across 7
    review rounds — the closing recommendation there matches this section
    verbatim. §13.10's tripwire (a single undifferentiated AGENT segment
    spanning two disjoint institution mentions) is **not** resolved by this
    refactor and remains documented, tracked residual scope — no current
    template produces that shape, but a future one that does must re-review
    this guardrail before shipping. The original recommendation text
    follows, preserved for the historical record:

    The `quoted_spans` masking mechanism
    (both `_build_output` functions building a `frozenset` of interpolated
    field values, then `check_guardrail` blanking each literal occurrence
    out of a copy of the assembled body before running `_EVALUATIVE_RE`) is
    now the largest single source of defects in this sprint (5 of 7 BLOCKs
    across the review's six rounds). Each fix has been one level deeper
    than the last — match the named example, then the sibling field, then
    a mechanical enumeration of every interpolated field — and the round-6
    fix (ASK-D) shows the failure mode has moved again, from *which field*
    to *what transform is applied between the field and the text being
    matched* (masking a field's raw value when a different, transformed
    value is what actually gets rendered). The reviewer's assessment: this
    is a countermeasure chasing a defect class rather than eliminating it,
    and the next variant is predictable in shape (a field enumerated and
    masked correctly, but rendered through a new transform — truncation,
    `title()`, markdown escaping, a wrap that inserts a newline mid-span).

    The root cause: both agents assemble a flat string and then try to
    *reconstruct* provenance from it by substring search, when provenance
    is known exactly at assembly time and is discarded before the check
    runs.

    Recommended fix (candidate for its own future, separately-scoped
    sprint — **do not implement as part of this sprint**): have both
    `_build_output` functions assemble the body as an ordered list of
    `(text, provenance)` segments — `AGENT` for headings, framing prose,
    and code-authored connective text; `QUOTED` for every interpolated
    non-agent value (operator-typed or World-sealed) — and have
    `check_guardrail` run `_EVALUATIVE_RE` over the concatenation of the
    `AGENT` segments only, while the institutional-character/proximity-
    window pass still runs over `"".join(all segments)` (the full rendered
    document, which is what that check legitimately needs). This deletes
    `quoted_spans`, `_MIN_QUOTED_SPAN_LEN`, the global-substring masking,
    the raw-vs-rendered class of bug entirely, and the possibility of a
    span accidentally matching unrelated text elsewhere in the body — and
    makes "did you enumerate every field?" a non-question, because any
    field not explicitly wrapped as a `QUOTED` segment is inescapably
    `AGENT` and therefore fails closed by construction, rather than fails
    open by omission. The 117+ existing agent tests, unchanged in intent,
    become the regression harness for the refactor. See REVIEW.md's
    "Re-review addendum 5 (round 6)", §4, for the reviewer's full reasoning
    and the current build's safety argument for why this ships as WEAK_PASS
    without the refactor (every known failure mode in this family currently
    degrades closed).

    **[CLOSED — round 7 follow-up, 2026-07-27, see BUILD_LOG.md's "Round 7:
    provenance-and-name-tag fix" entry.]** REVIEW.md's re-review addendum 6
    found the institutional-character check's neighbour rule was still a
    proximity window measured in segments rather than characters: it
    treated *any* non-AGENT neighbouring segment as a legitimate voucher,
    without checking that the neighbour was actually a *name* (a WORLD
    ``verified_as_of`` date or ``verification_source`` URL could
    illegitimately vouch for an institutional-character claim about a
    completely unrelated, agent-invented name). Fixed by adding a second,
    independent tag to `Segment` — `is_name` — set `True` only at the
    specific construction site where a caller writes an institution's own
    name (`v.name` in Debt Advisor, `r.institution` in Consolidation
    Analyzer; both were previously bare `Segment.world(...)`/
    `Segment.operator(...)` calls). `check_guardrail`'s institutional-
    character branch now accepts a claim in an `AGENT` segment only if an
    immediate neighbour is specifically tagged `is_name=True` (and is
    non-AGENT) — adjacency to a non-AGENT segment that is not a name (a
    date, URL, product, or source field) is no longer sufficient. A trigger
    whose *own* segment is already WORLD/OPERATOR (e.g. a vetted
    institution's own `institution_type` literal) remains trusted without
    needing an adjacent name, because that text is itself verbatim vetted
    content, not an agent claim about something else.

    This closes the reachable half of the family: the check no longer infers
    whether a neighbour *is a name* from its provenance, casing, or content —
    that is now a direct assertion, made once at the one call site that
    actually knows it is writing a name, checked by the guardrail as a
    boolean flag rather than inferred. A future finding in the previously
    reported shape (an unrelated, non-name WORLD/OPERATOR segment — a date,
    URL, product, or source field — vouching for an agent-invented name) is
    not possible against this design, because the check no longer asks "is
    *any* non-AGENT text nearby" — it asks "is *the* segment tagged as this
    institution's name nearby", which cannot be satisfied by an untagged
    neighbour regardless of its provenance or content.

    **Correction (REVIEW.md re-review addendum 7, round 8):** this section
    previously claimed "no adjacency math" and "no positional reasoning of
    any kind left in the institutional-character branch." That overstates
    what shipped. The check still uses segment *adjacency* to decide which
    name a claim is about — it no longer infers *whether* a neighbour is a
    name, but it still relies on the neighbour relationship itself. Two
    residual shapes that use adjacency this way (a non-AGENT trigger segment
    trusted with no name pairing at all, and a real vetted name vouching for
    a claim about a different, agent-invented name via adjacency) were found
    live by the round-8 reviewer and are documented, with tripwire, in
    §13.10 — they are not part of §13.11's closure and were never eliminated
    by it.

    Also fixed in the same pass, per REVIEW.md's addendum 6 required
    actions: (a) a template-invariant test asserting no AGENT segment
    adjacent to a non-AGENT segment in either agent's real `_build_output`
    carries an institutional-character trigger or is model-generated
    (`test_template_invariant_no_agent_segment_adjacent_to_non_agent_carries_a_trigger_or_is_dynamic`
    in `tests/test_debt_finance_compliance.py`) — defense in depth, kept
    even though the `is_name` fix no longer depends on this invariant for
    safety; (b) the Consolidation Analyzer's `_vetted_institution_names`
    now filters non-dict `terms.json` entries the same way
    `_builtin_debt_advisor._load_terms` does (F9's asymmetry — a stray
    malformed entry no longer raises `AttributeError` out of an unguarded
    `tick()`, which F1's backstop would otherwise turn into a silent
    permanent stall); (c) the module docstring now states the WORLD
    evaluative-exemption trust boundary explicitly, including that it
    depends on `scripts/forge_debt_finance_world.py`'s seal-time preflight
    evaluative-language scan remaining in place and actually run before any
    reseal (confirmed present as of this fix); (d) the analyzer's
    `REASON_EVALUATIVE` operator-facing hint no longer points at
    `institution`/`product`/`source`/`as_of` (all OPERATOR segments,
    structurally exempt from this check) — it now correctly names the
    LLM-generated framing sentence as the only text that can trigger this
    branch; (e) the docstring now states explicitly that `Provenance.
    OPERATOR` means name authenticity ("the operator typed this string"),
    distinct from `Provenance.WORLD`'s actual character verification
    (`institution_type` + `verification_source` + a fresh
    `verified_as_of`) — and the code enforces this distinction via
    `is_name` rather than treating OPERATOR provenance as blanket
    character-vetting.

    **Why this is believed structurally complete, not just tested:** every
    prior finding in this ten-plus-finding family shared one shape — a
    matcher approximating "is this text trustworthy for this specific
    claim" from something *inferred* about the text (containment, casing,
    character offsets, segment adjacency) rather than from a fact stated
    once at the only point that actually knows it. Each fix closed the
    specific inference method reported and left the next inference method
    (position, adjacency) available as an escape, because the check was
    still *inferring* an answer rather than being *told* one. `is_name` is
    not another inference method — it is a boolean fact set by the same
    call site that already sets `provenance`, using the same "caller
    knows, checker reads, never re-derived" contract that closed the
    evaluative-language half of this same defect family in round 7's first
    pass. For the AGENT-own-segment case (case 2 in `check_guardrail`'s
    docstring), the check no longer reasons about *whether* a neighbour is a
    name from its content or provenance — it reads a boolean AND between "is
    this neighbour non-AGENT" and "is this neighbour tagged as a name",
    instead of a proximity heuristic over content. **This is not the same as
    "no adjacency math" or "no positional reasoning of any kind left"** — the
    check still uses adjacency itself to decide *which* name a claim is
    about, and REVIEW.md re-review addendum 7 (round 8) verified two shapes
    that exploit that: a non-AGENT trigger trusted with no name pairing at
    all, and a real vetted name vouching for a claim about a different,
    agent-invented name across an AGENT span. Both are documented, with
    tripwire, in §13.10, not eliminated by this fix. §13.11 is CLOSED for the
    defect it was actually reported against — "any non-AGENT text counts as
    a name" — not for positional reasoning in general. The residual §13.10
    tripwire (a single undifferentiated AGENT segment spanning two disjoint
    institution mentions, now including the two shapes above) remains
    separately tracked, unrelated to this fix, and still requires no current
    template producing that shape.
