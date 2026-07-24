---
title: Conversation memory
description: "How the lab remembers chat — the append-only transcript, the gated user-understanding tier, and the schema contract both obey."
category: Reference
order: 6
tags:
  - memory
  - chat
  - pkb
  - schema
  - privacy
audience: architect
related:
  - agents
  - the-lab
---

# Conversation memory

> **⚠ STATUS (2026-07-23):** Tier 1 (the append-only `transcript.jsonl` log) is
> **shipped**. The **Tier-2 "user understanding" fact store** described below —
> `lab/pkb/understanding/<fact_id>.md`, fact distillation from user quotes,
> `recall_user_facts`, gated fact injection — is **ROADMAP / not yet built**
> (no such code or directory exists). Read the Tier-2 sections as the intended
> design, not current behavior. Do not assume fact-recall runs today.

The lab remembers chat in **two tiers**, and the difference between them is the whole design.

| Tier | What it is | Authoritative about the user? | Who reads it |
|---|---|---|---|
| **1 — Transcript** | Every turn, verbatim, append-only | **No** | The Chat tab (rehydration), the server (history for the next turn) |
| **2 — Understanding** | Distilled facts about you, each sourced to a quote | **Only once approved** | Agents, via `search_for_agents` |

Tier 1 is a log. Tier 2 is knowledge. Conflating them is how a lab ends up confidently wrong
about the person using it — see [ADR-0002](adr/0002-chat-memory-and-the-dac-boundary.md).

## Where it lives

```
lab/pkb/conversations/<conversation_id>/transcript.jsonl   # Tier 1
lab/pkb/conversations/<conversation_id>/meta.json          # title, timestamps, schema_version
lab/pkb/understanding/<fact_id>.md                         # Tier 2 — markdown + frontmatter
```

**Under the PKB root, deliberately.** `docs/agents.md` states the contract plainly: *"Wiping
memory is always one command: delete the file/dir, or run `./arailctl reset pkb`."* Conversation
data is the most sensitive thing the lab holds, so it lives inside that contract. Anything
written to `lab/data/` instead would survive a PKB wipe — a silent privacy break.

> **`.jsonl`, never `.json`.** `pkb.py:376` `_PKB_TEXT_SUFFIXES` includes `.json` but not
> `.jsonl`. Naming the transcript `.json` would vector-index every chat turn into the wiki.
> This is a pinned, tested invariant, not a stylistic preference.

## Tier 1 — the transcript

JSONL is append-only, so a record can never be updated in place. The transcript is therefore
an **event log**, and turn state is derived by folding events by `turn_id`:

```jsonc
{"v":1,"type":"turn.started",   "turn_id":"t_…","conversation_id":"c_…","branch":"A","seq":0,
 "role":"user","content":"…","ts":"2026-07-16T…Z","model":"…","backend":"…"}
{"v":1,"type":"turn.progress",  "turn_id":"t_…","seq":1,"delta":"…"}
{"v":1,"type":"turn.completed", "turn_id":"t_…","seq":9,"reply":"…","tokens_used":128,
 "latency_ms":812,"ts":"…"}
{"v":1,"type":"turn.failed",    "turn_id":"t_…","reason":"…","partial_text":"…","ts":"…"}
{"v":1,"type":"turn.interrupted","turn_id":"t_…","reason":"server_restart","partial_text":"…","ts":"…"}
{"v":1,"type":"turn.abandoned", "turn_id":"t_…","reason":"…","ts":"…"}
```

**`turn.progress` carries the incremental slice, never the cumulative text.** Cumulative
progress records would make a 500-token reply write O(n²) bytes.

### Invariants

- **A turn with no terminal event is an orphan.** `completed`, `failed`, `interrupted`, and
  `abandoned` are the terminal events. This *is* the crash-recovery mechanism: the startup
  sweep folds the log, finds turns with no terminal event, and appends `turn.interrupted`.
  Because appending a terminal event is what resolves an orphan, the sweep is idempotent.
- **At most one in-flight turn per `(conversation_id, branch)`** — not per conversation.
  Compare mode legitimately runs two branches at once (`branch ∈ {A,B}`).
- **`seq` is monotonic per turn and counts events, not tokens.** This is what lets a
  token-streaming backend and a single-delta backend share one protocol.
- **A `turn.completed` record is immutable.** History is superseded, never rewritten.
- **Every record carries `v`** (schema version). Readers must tolerate unknown fields.
- **One bad line never eats the log.** JSON parse failures are skipped per-line, counted, and
  logged — never allowed to abort the replay. Append + flush-per-record means only the last
  line can ever be torn.

### Versioning

`v` on every event; `schema_version` in `meta.json`. Additive fields do not bump `v`. A change
that would make an old reader wrong bumps `v`, and the fold must handle both.

## Tier 2 — understanding

One fact per file, markdown with frontmatter — the same shape as the rest of the PKB, which is
why it inherits the LanceDB index, `search_for_agents`, the approval gate, and the wipe
contract for free.

```markdown
---
fact_id: f_01J…
schema_version: 1
kind: preference          # preference | goal | context | skill
claim: "Prefers Rust for systems work"
confidence: 0.8
gate_status: raw          # raw | approved | rejected
created_at: 2026-07-16T12:00:00Z
superseded_by: null
provenance:
  conversation_id: c_01J…
  turn_id: t_01J…
  quote: "honestly I'd rather write it in Rust than Go these days"
---

Prefers Rust for systems work.
```

### The gate is the reality anchor

Two rules, both non-negotiable:

1. **Facts are distilled only from *user* turns — never from assistant output.** An agent that
   learns from its own generated text hallucinates a user and then believes itself.
2. **A fact with no locatable verbatim span in a user turn is rejected.** `provenance.quote`
   must actually appear in the cited turn.

Facts start `raw` and are invisible to agents. Only `approved` facts pass
`search_for_agents`, which honors the Compiled-KB gate (`ARAIL_APPROVED_ONLY`, `pkb.py:666-672`)
— the same gate the rest of the lab's knowledge already goes through.

**Facts are superseded, never rewritten.** When you start using Rust, the Go fact gets
`superseded_by` set; it is not edited and not deleted. That is how the lab can tell "changed
their mind" from "was always true".

## How agents consume it

Agents never read the transcript. They read approved facts:

```python
# BuddyHost
def recall_user_facts(self, kinds: list[str] | None = None, limit: int = 8) -> list[dict]: ...
```

Backed by `search_for_agents`, so the gate applies for free. Buddy folds the result into
`_compose_prompt` alongside its dream block. Chat-side injection happens in
`lab_brain.build_chat_messages` — **token-bounded top-K approved facts, never the raw
transcript.** Growth in the transcript must never grow the prompt; that is the point of having
two tiers.

## Relationship to DaC — explicitly none at runtime

This store is **ARAIL-native**. It borrows DaC's discipline (declare → gate → version → no
drift) and has **no runtime dependency on DaC**. DaC is a build-time pipeline with no write
API; it explicitly defines itself against paging conversation history in and out of a mutable
store. DaC is the control plane; ARAIL is the data plane.

The full argument, the alternatives, and the one seam left open as ROADMAP are recorded in
[ADR-0002](adr/0002-chat-memory-and-the-dac-boundary.md). Read it before wiring anything here
to DaC.

## One lab, one person

**ARAIL will never have multi-user hosted memory** ([ADR-0003](adr/0003-why-not-letta-memgpt.md)).
That is a product boundary, not a roadmap position, and it simplifies this design:

- **There is no `user_id`, and there never will be.** `conversation_id` is the only identity here.
  (`identity.py` is *lab* identity — branding — not user identity.)
- One PKB = one person's memory, which is exactly what makes `reset pkb` a complete forget.
- Single-user is a permanent assumption. Concurrent *tabs* are still real; concurrent *users* are
  not.

If you find yourself adding a user column, tenancy, or a hosted memory dependency, stop — that is
a signal something upstream has gone wrong.

## Privacy

- Everything is under the PKB root: `./arailctl reset pkb` wipes it, and so does deleting the
  directory. In-memory stream buffers are dropped on purge too — otherwise plaintext would
  outlive the wipe.
- Nothing here is git-tracked (`lab/pkb/` is git-ignored).
- The transcript never leaves the box; the egress guard applies as it does everywhere else.
- Ephemeral chat still works: a request with no `conversation_id` persists **nothing**. That is
  how the model warm-up ping avoids writing junk into your knowledge base.
