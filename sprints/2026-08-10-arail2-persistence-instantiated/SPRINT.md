# Sprint: arail2-persistence-instantiated

**ID:** 2026-08-10-arail2-persistence-instantiated
**Started:** 2026-08-10
**Product:** arail
**Branch:** `qukaizen/arail2-persistence-instantiated` (based on `d5c592a`, origin/main)

## Task

ARAIL 2.0's persistence layer shipped in #175 and has never been instantiated
on a real machine. Two defects, possibly one root cause:

**Defect A — the relational store is never created.** `src/arail/dbspec/` is
real architecture: `arail.db` per data dir, deliberately scoped to the same
directory boundary as a World's Lance tables and secrets. Its own docstring
frames this as a tenancy fix ("in 1.x the tenant boundary was the process's
frozen env, and nothing in the storage layer recorded which world a row
belonged to"). A `./arailctl db` verb exists (`plan|apply|doctor|optimize|
drift|migrate`) — but **nothing calls it**:

- `install` never runs `db apply`
- `start` never ensures the schema is applied before the portal boots
- `status` never reports DB presence, schema version, or drift
- `scripts/setup.sh` mentions `dbspec` only in comments about the embedder

Consequence, verified on the operator's machine: **`arail.db` does not exist
anywhere under `lab/`** — not for the root lab, not for any of the six
instances. `db migrate` is documented as a one-shot 1.x → 2.0 migration and
has never been invoked.

**Defect B — the semantic retrieval path silently returns zero.** After the
QA-6 gate fix (PR #176) and a full re-embed under #175's upgraded embedder,
retrieval is only half-working on a 422-row, 339-approved World:

| Query | Result |
|---|---|
| `"gradient descent"` | 5 hits |
| `"attention"` | 44 gated hits |
| `"transformer"` | 47 gated hits |
| `"how does attention work"` | **0 hits**, `empty_reason=no_match` |
| `"what is a transformer"` | **0 hits** |

Every hit returns `source='keyword'`. `pkb._semantic_search(...)` returns 0
**even ungated** — so single words match by regex substring and
natural-language questions match nothing. Buddy only ever sends
natural-language questions, so the QA-6 win condition is still not delivered
in practice even though the gate is provably open.

## Why these are one sprint

Both live in the ARAIL 2.0 persistence/retrieval layer, both shipped-but-
never-exercised, and `pkb.py` / `pkb_index.py` / `vector_index.py` all import
`dbspec`. **The architect must rule early on whether A and B are one bug or
two** and split the sprint if they are two. Do not assume the link — the
`dbspec` imports in `pkb_index.py` are largely `dbspec.embed` and the
generated models registry, not the DB itself.

## Open question for the architect

Should `start` **create/migrate** the DB on boot, or **refuse** and tell the
user to run `install`? This is the quiet-boot rule from the
2026-07-23 clean-experience sprint pulling against convenience.

**Precedent:** the immediately preceding sprint
(`2026-08-09-compiled-kb-bootstrap`) faced the identical question for the
Compiled-KB manifest and chose **refuse** — bootstrap runs from `install` and
an explicit verb, never from `start`, because booting must stay quiet and must
never silently re-approve a term the operator revoked.

**OPERATOR RULING (2026-08-10) — this sprint deviates from that precedent,
deliberately:** *"make this seamless and easy, but also want to give status
visibility and startup love as it's now a dependent service."*

So the answer is **seamless, not refuse** — but the reason the precedent went
the other way still holds and must be honored in a specific way. The
distinction the architect should design to:

- The Compiled-KB case refused because bootstrap makes a **policy** decision
  (what an agent is allowed to treat as truth) and could silently re-approve
  something the operator revoked. Auto-running it on boot would have made a
  consent decision on the operator's behalf.
- `arail.db` is **infrastructure**, not policy. Creating an empty schema
  decides nothing on the operator's behalf and revokes nothing. It is a
  dependent service, and a dependent service that isn't up is a startup
  failure to be handled, not a choice to defer to the user.

Therefore: `start` **ensures the DB is ready** (create + migrate to the
current schema version) as a readiness-gated startup step — and *reports* it
rather than doing it silently. Quiet boot means no chatter when everything is
already fine, not invisible writes. Treat it the way `start` already treats
readiness for other services (`--warm` reports boot-time model warm-up).

A **migration that would alter or destroy existing data** is not in the
"infrastructure, decides nothing" category and must NOT be seamless — that
still needs an explicit verb. The architect should draw this line precisely:
create-and-apply-forward is seamless; anything lossy is not.

### Required scope from the ruling

1. **Seamless** — a user who runs `install` then `start` never has to know
   `arail.db` exists, and never has to run `./arailctl db` by hand.
2. **Status visibility** — the DB becomes a first-class line in
   `./arailctl status`, alongside the other services: present/absent, schema
   version, drift, and per-World instance (not just the root lab). Must not
   break the documented `arail.status/v2` schema or the `0`/`3`/`4` exit-code
   contract; a DB that is down or drifted should map onto the existing
   degraded semantics rather than inventing new ones.
3. **Startup love** — the DB is a dependent service, so `start` should
   readiness-gate on it and fail *honestly and actionably* when it can't come
   up, naming the fix. Same caliber of surface as the 2026-07-29 elite-cli
   sprint's readiness-gated `start`.
4. **`doctor`** should catch the "shipped but never instantiated" class
   directly — see the meta-observation below.

## Meta-observation worth designing against

This is the **second consecutive release** where a mechanism shipped correct
and gated behind a step nothing performs (QA-6: the Compiled-KB gate shipped
on with nothing ever approved; this sprint: the relational store shipped with
nothing ever creating it). The sprint should ask whether `status` / `doctor`
can be made to catch this class structurally, rather than fixing the two
instances and waiting for a third.

## Phases

| Phase | Subagent | Artifact | Status | Verdict |
|---|---|---|---|---|
| think | visionary | VISION.md | skipped | — |
| plan | architect (design) | ARCHITECTURE.md | in progress | — |
| build | builder | BUILD_LOG.md | pending | — |
| review | architect (review) | REVIEW.md | pending | — |
| test | qa | TEST_REPORT.md | pending | — |
| ship | — | PR | pending | — |

## Skipped phases

| Phase | Reason |
|---|---|
| think | Win condition is not in question: the persistence layer must actually exist on a real lab, and Buddy must retrieve on natural-language queries. |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-08-10 | Skip visionary | Bug-fix sprint with an obvious win condition. |
| 2026-08-10 | Bundle defects A and B into one sprint, with an early architect ruling on whether to split | Both are shipped-but-never-instantiated ARAIL 2.0 persistence defects; the retrieval layer imports `dbspec`. The link is a hypothesis, not an established fact. |

## Constraints carried in

- **Per-instance boundary is load-bearing.** `arail.db` is scoped per data dir
  by design; do not introduce a shared or root-level DB that spans Worlds.
  Per-instance secrets are never shared or auto-copied (CLAUDE.md).
- **One PKB root per process** remains an invariant; `pkb_index`'s degraded
  state is process-global (see its module docstring).
- **Quiet boot.** `start` must not become chatty or perform silent writes
  without a ruling that supersedes the clean-experience sprint.
- **Egress honesty.** The embedder is local (`nomic-embed-text` via Ollama,
  ~74 rows/s measured); nothing here should introduce a network call on a
  search path. `pkb_index` already treats an on-demand embed inside a search
  request as a defect (C1/C2).
- `./arailctl status` has a documented `arail.status/v2` schema and a real
  exit-code contract (`0`/`3`/`4`) — extending it must not break either.

## Evidence appendix (measured 2026-08-10, operator's machine)

```
find lab -name 'arail.db'          -> (no results, anywhere)
gate_state(ai)                     -> state=populated, approved=339, live=339
pkb.search('attention', gated)     -> 44 hits, all source='keyword'
pkb._semantic_search(..., ungated) -> 0
```

Post-QA-6 Compiled-KB state, for reference: root 0 · ai 339 · qukaizen 32 ·
video-games 69 · debt-finance 0 (no bundle in catalog; needs one mount) ·
finance 0 (no World staged).
