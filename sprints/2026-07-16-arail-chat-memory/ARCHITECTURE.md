# ARCHITECTURE — Persistent chat memory

**Sprint:** 2026-07-16-arail-chat-memory
**Status:** design complete; no product code written
**Reads:** SPRINT.md · **Emits:** the contract the builder implements
**Companion docs:** `docs/adr/0002-chat-memory-and-the-dac-boundary.md`, `docs/conversation-memory.md`

---

## 1. Problem

The Chat tab loses its conversation on every tab switch or reload, and the lab keeps no record
of past conversations at all.

The portal is a true MPA — `_nav.html` uses plain `<a href>` links, so every tab switch is a
full page load. All chat state lives in an in-memory JS `State = {}` (`chat.html:1874`) with
`history: []` (`:1890`), destroyed on navigation. `streamChat()` (`:2826-2945`) reads the
response via `fetch()` + `getReader()` — a page-local connection. No `conversation_id` exists
anywhere; the server is stateless per turn and trusts the client to supply history
(`app.py:6776`).

Two requirements:

1. **Live continuity** — the conversation survives navigation; an in-flight response keeps
   generating and is recoverable.
2. **Durable understanding** — a retained record agents use to understand the user over time.

## 2. What the investigation changed

Verified against the working tree on 2026-07-16. Three premises in the brief were wrong, and
one live bug surfaced. These are load-bearing — read before implementing.

### 2.1 The inference slot leaks on client disconnect (live bug)

Generation is **already** background, and already broken:

- `_stream_sync_iterator` (`app.py:6218-6227`) starts `threading.Thread(target=_worker,
  daemon=True)` that drains the iterator to completion **regardless of the consumer**.
- Deep (`:6278`) and runtime (`:6322`) paths use `asyncio.to_thread`; a `ThreadPoolExecutor`
  future **cannot be cancelled once running** — cancelling the await abandons the thread, it
  does not stop it.
- `scheduler.inference_slot` releases the semaphore in a `finally` around a `yield`
  (`scheduler.py:184-194`). On client disconnect, the unwind runs `sem.release()` **while the
  GPU thread is still executing**.
- `ARAIL_INFERENCE_CONCURRENCY` defaults to **1** and exists as an OOM guard
  (`scheduler.py:26-30`).

**Consequence:** navigate away mid-generation → slot freed → next chat dispatches → two
concurrent MLX/AirLLM generations → exactly the OOM the semaphore prevents.

**This reframes the feature.** We are not adding background generation. We are capturing
generation that already runs in the background, is discarded, and corrupts the slot on the way
out. The design **fixes** this bug.

### 2.2 `chat.html:3418` is a warm-up ping, not a chat parser

`loadModel()` (`:3418-3477`) POSTs to `/api/chat/stream` with `message:'ok'`, `max_tokens:1`
and parses NDJSON only to detect `{type:'error'}`. Its `history: []` at `:3424` is a request-body
literal, not a state array.

**Consequence:** if persistence were unconditional, **every LOAD click would write junk into the
user's PKB.** This forces persistence to be opt-in (§6.3).

### 2.3 There is a third reader

`POST /api/teacher/stream` (`app.py:11257-11289`) calls the same `_run_chat_completion_stream`,
with its own reader at `teacher.html:281`. Any signature change to that generator breaks Teacher.

### 2.4 Other verified facts

- `start-portal.sh:6` runs `--reload`. **Restart-mid-stream is the default dev loop.**
- Both launchers are single-worker (no `--workers`), so a module-level registry is valid — and
  would shard silently if anyone adds workers. Document it.
- `pkb.py:376` `_PKB_TEXT_SUFFIXES = (".md",".txt",".rst",".csv",".json",".html")` — includes
  `.json`, **excludes `.jsonl`**. Transcript must be `.jsonl`. Pin by test.
- `max_tokens` is unclamped (`int(body.get("max_tokens") or 512)`, `app.py:6781`).
- Starlette branches on ASGI `spec_version`: `<2.4` → disconnect-cancel via a task group;
  `>=2.4` → the generator dies only when the next `send()` raises. uvicorn advertises `2.3`
  for HTTP but `2.4` for websockets — a migration in progress. **A uvicorn bump could silently
  flip cancellation semantics.** A detached task is immune to both branches.
- No code in `app.py` holds a strong reference to any `asyncio.create_task` result
  (`:798-806`, `:10958`, `:10995`) — the documented "task disappears mid-execution" footgun.
- `write_teacher_qa` (`pkb.py:807`) mkdirs on **every** write, surviving `rm -rf lab/pkb`;
  `activity.py` mkdirs once in `_init` and does not.

## 3. The DaC boundary (summary; full argument in ADR-0002)

**Adopt DaC's discipline; do not route conversation data through DaC's pipeline.**
DaC is the control plane, ARAIL is the data plane. No runtime dependency on DaC.

DaC defines itself *against* this use case (`CONTEXT_VM.md:208-210`), has no runtime
(`README.md:55`), and its one ARAIL seam runs the other way (ADR-0004 D4: "ARAIL only reads").
Claiming otherwise breaches DaC's own honesty rail (`README.md:65`).

The discipline transfers because the risk is identical: `DAC_ENGINE.md:153-155` — an agent that
updates its world from its own output "hallucinates a world and then believes itself. The gate
is what keeps the loop tethered." **And ARAIL already runs this loop**: `search_for_agents`
applies the Compiled-KB gate so "agents build ONLY on approved knowledge" (`pkb.py:666-672`).

## 4. Two tiers

| Tier | Store | Authoritative about the user? |
|---|---|---|
| 1 — Transcript | `lab/pkb/conversations/<cid>/transcript.jsonl` | **No** — it's a log |
| 2 — Understanding | `lab/pkb/understanding/<fact_id>.md` | Only once `gate_status: approved` |

Tier 2 as PKB markdown inherits the LanceDB index (`pkb_pages`), `search_for_agents`, the
approval gate, and "wipe the PKB = forget me" — no new machinery. It follows the existing
**dreams** precedent (`docs/agents.md:136-140`): distill raw log → durable markdown → inject on
next wake, which Buddy already consumes (`_builtin_buddy.py:1057-1090`). Difference: dreams are
agent self-reflection; user facts are claims *about a person*, so they need the sourcing gate.

**Under the PKB root, not `DATA_DIR`** — `docs/agents.md:142-143` and
`_builtin_buddy.py:198-201` make "wipe the PKB = wipe memory" a documented privacy contract.

Schema, invariants, and the fact frontmatter are specified in `docs/conversation-memory.md`.
Summary of the invariants the builder must enforce:

- A turn with **no terminal event is an orphan** (this is the crash-recovery mechanism, and it
  makes the sweep idempotent).
- At most one in-flight turn per **`(conversation_id, branch)`** — *not* per conversation;
  compare mode runs two branches (`chat.html:2788`/`2942`).
- `seq` is monotonic per turn and counts **events, not tokens** — this collapses streaming and
  single-delta backends (`app.py:6308`, `:6339`) into one protocol.
- `turn.progress` carries the **incremental** slice, never cumulative (else O(n²) bytes).
- `.jsonl`, never `.json` (`pkb.py:376`).

## 5. Data flow

```
POST /api/chat/stream ──> create-or-attach ──> DETACHED TASK (owns generation)
                              │                     │
                              │                     ├─> ring buffer (512 events)  ─┐
                              │                     ├─> accumulator (full text)    │
                              │                     └─> transcript.jsonl (durable) │
                              │                                                    │
                              └─> HTTP response = SUBSCRIBER ─────────────────────┘
                                    (disconnect kills the subscriber, NOT the task)

GET /api/chat/turns/{id}/events?from_seq=N ──> attach as another subscriber
GET /api/chat/conversations/{cid}          ──> fold transcript.jsonl → rehydration
```

This is `activity.py`'s shape exactly: producer → ring + durable append + fan-out; the endpoint
is just a subscriber.

## 6. Streaming survival

### 6.1 Mechanism: detached `asyncio.create_task` + module-level registry

**Rejected alternatives:**

- **`BackgroundTasks`** — structurally impossible. Starlette runs `await self.background()`
  *after* `stream_response` returns; it can never produce the body it is meant to stream.
- **`asyncio.shield`** — cannot wrap an async generator's iteration. The outer await still
  raises `CancelledError`, `stream_response`'s `async for` still unwinds, the generator still
  gets `GeneratorExit`. The shielded task keeps running but **has nowhere to put its events** —
  so you must add a buffer and a registry, which *is* the recommended design.
- **WebSocket** — page unload kills it too. Solves nothing, adds a protocol.

**Registry location:** new `src/arail/portal/chat_turns.py` (not `app.py`, already 11,345
lines), module-level singleton on `activity.py`'s `__new__` pattern. Module state is
independent of app lifecycle, so legacy `@app.on_event` vs lifespan is a non-issue.
PKB layout stays in `pkb.py` next to `write_teacher_qa` (`:796`).

### 6.2 Slot lifetime must follow the thread, not the coroutine

This is the §2.1 bug fix. Release from **thread completion**, not from the await:

```python
await slot.acquire()
fut = loop.run_in_executor(None, fn, ...)
fut.add_done_callback(lambda _: slot.release())   # fires when the THREAD ends
```

Needs an additive `scheduler.acquire_slot(label)` / `release_slot()` alongside the existing
context manager (`scheduler.py:145-194`) — **keep the CM**, `world_routes.py` has five call
sites. For the router path, release on `_stream_sync_iterator`'s **sentinel** (`app.py:6224`),
not on generator close.

**Honest limit:** a wedged backend now holds the slot until restart, and at capacity 1 that
kills chat. This is unfixable in-process — you cannot stop a running thread. Mitigation is
diagnosis, not recovery: surface in-flight turn ids next to `scheduler.snapshot()` in the admin
perf card and document that a wedged backend needs a restart. Do not pretend otherwise.

### 6.3 Persistence is keyed on `conversation_id` presence

No `conversation_id` → fully ephemeral, current behavior verbatim. This is both the migration
lever and the fix for `loadModel()` (§2.2) — it simply never sends one.

### 6.4 Wire protocol

Strictly additive. `ev.delta` is preserved (`chat.html:2876` reads it), so existing readers —
including Teacher — keep working.

```
POST /api/chat/stream                            # path unchanged; body gains
                                                 #   conversation_id?, branch?, client_turn_id?
GET  /api/chat/turns/{turn_id}/events?from_seq=N # resume — SHAPE-IDENTICAL to POST output
GET  /api/chat/conversations/{conversation_id}   # rehydration: messages + turn statuses
```

Resume output being shape-identical is what lets **one client reader** handle both.

```jsonc
{"v":1,"type":"start","turn_id":"t_…","conversation_id":"c_…","branch":"A","seq":0,
 "ts":"…","backend":"mlx","model":"…","deep":false}
{"v":1,"type":"delta","turn_id":"t_…","seq":1,"delta":"Hello"}
{"v":1,"type":"final","turn_id":"t_…","seq":2,"reply":"Hello","tokens_used":2,"latency_ms":812}
{"v":1,"type":"heartbeat","turn_id":"t_…","seq":1,"elapsed_ms":42000}  // transient; seq does NOT advance
{"v":1,"type":"rebase","turn_id":"t_…","seq":9,"text":"<full accumulated text>"}  // resume only
```

`heartbeat` exists because a blocking single-delta backend (§2.4) can show nothing for minutes;
it is ring-only and never persisted.

### 6.5 The accumulator makes the ring cap a non-issue

The task already holds full accumulated text (it needs it for the final record). On attach:

- `from_seq == last_seq` → live only
- `from_seq >= earliest_ring_seq` → replay the slice, then live
- else → `rebase` with the accumulator, then live

So `from_seq` is an **optimization, not a correctness requirement**, and the ring is a fan-out
jitter buffer rather than a correctness mechanism.

**The attach race** — snapshot `(acc_text, last_seq, status)` and register the subscriber queue
with **no `await` between them**. asyncio is cooperative and single-threaded, so that sequence
is atomic. This is exactly why `activity.py`'s `emit` (buffer-append `:66` → fan-out `:87`) has
no gap. Our fan-out is loop-local (the producer is a coroutine), so unlike `activity.py` we do
**not** need `call_soon_threadsafe`.

### 6.6 Two deliberate divergences from `activity.py`

1. **Never silently drop.** `activity.py` drops on `QueueFull` (`:101`). Fine for advisory
   events; **a dropped delta silently corrupts the transcript.** On QueueFull, mark the
   subscriber desynced and force a `rebase` (or drop the connection and let it resume).
2. **Per-line JSON tolerance.** `activity.py` wraps the *whole* replay loop in one
   `except (OSError, JSONDecodeError)` (`:46-52`) — one bad line aborts the replay and silently
   truncates. For a transcript that eats the user's conversation. Use **per-line** skip + count
   + log. Safe because O_APPEND + flush-per-record means only the last line can be torn.

### 6.7 Client flow

Read `localStorage['arail.chat.conversationId']` — **pointer only**; the server is truth and
localStorage never stores messages (matches the `arail.*` convention at `:2667`). Then
`GET /api/chat/conversations/{id}` → render via the existing `appendUser`/`appendAssistant` →
for each turn with `status:"running"`, open the resume stream into the slot keyed by `branch`;
`status:"interrupted"` → render partial + marker + retry.

### 6.8 Structural bug fixes that fall out

Once the server owns the transcript, **`history` stops being a client input** (`buildBody`,
`:2756`) — the server reads the last N turns from its own JSONL. That structurally kills:

- **(a) The dangling-user-turn corruption.** There is no `AbortController` anywhere in
  `chat.html` (grep count 0). On any throw, the catch at `:2797-2806` paints the error and
  control never reaches the assistant-push at `:2942` — leaving an orphan user turn in
  `State.history` that ships to the server on the next `buildBody()`. History is no longer
  client-accumulated, so this cannot happen.
- **(b) Compare-mode interleave.** `read_history(conversation_id, branch)` filters
  `branch in (None, requested)`, so B never sees A's replies — fixing the flat-`State.history`
  bug at `:2788`/`:2942`.
- **(c) Client-side history tampering.** `_CHAT_HISTORY_LIMIT` (`:5792`/`:6032`) becomes
  authoritative rather than advisory.

### 6.9 Tuning

| Knob | Value | Justification |
|---|---|---|
| Ring | 512 events/turn | ~10s of slack at 50 tok/s; ~20 KB/turn; bounded by semaphore capacity (1–4) |
| Accumulator cap | 1 MiB → mark `truncated` | Real bound is `max_tokens`, **client-controlled and unclamped** (`:6781`) — clamp it too |
| `TTL_COMPLETED` | 300 s | Pure latency optimization; the JSONL fallback is exact, so keep it short |
| Wall-clock cap | 30 min → `failed{timeout}` | Marks the turn; **does not** release the slot (§6.2) |
| Checkpoint | every 2 s **or** 512 chars | ≤2 s of token loss on crash; ~2× write amplification |

## 7. Agent consumption

`BuddyHost` (`_builtin_buddy.py:68-95`) exposes `get_pkb_root()` but **no search method** —
Buddy cannot reach `search_for_agents` today. Add one host method:

```python
def recall_user_facts(self, kinds: list[str] | None = None, limit: int = 8) -> list[dict]: ...
```

Backed by `search_for_agents`, so it inherits the Compiled-KB gate for free. Buddy folds the
result into `_compose_prompt` (`:1057-1090`) alongside the existing dream block.

Chat-side injection goes in `lab_brain.build_chat_messages` (`:604`) — **token-bounded top-K
approved facts, never the raw transcript**. Transcript growth must never grow the prompt; that
is the point of two tiers.

> **Verify at build time:** `build_chat_payload` (`:644-693`) splits a frozen (cached) prefix
> from volatile state for Claude prompt caching (docstring `:662-667`). Facts change rarely, so
> they belong in the **frozen** prefix — but confirm against that docstring before wiring, since
> putting them in the volatile section would defeat the split.

Full distillation is a fast-follow. The interface and the gate are fixed here.

## 8. Failure modes

| Failure | Behavior / mitigation |
|---|---|
| **Server restart mid-stream** (*routine* — `--reload`) | Ring + task die; JSONL has `started` + progress, no terminal. Startup sweep (`app.py:737`) folds and appends `turn.interrupted{reason:"server_restart", partial_text}`. Client renders partial + retry. Generation cannot resume — only the partial survives. |
| SIGKILL / power loss | Same sweep. **This is why the sweep, not the shutdown hook, is authoritative** — SIGKILL writes no marker. |
| Shutdown (`app.py:1074`) | Bounded ~2 s: stop accepting, best-effort markers, drop refs. **Never await generations** — `--reload` + a 10-min AirLLM turn hangs the dev loop, and `loop.shutdown_default_executor()` already blocks on `to_thread` threads. |
| Two tabs POST same `(cid, branch)` | Check-and-set with no `await` between → **409** `{"error":"turn_in_flight","turn_id":…,"resume":"…"}`. **Note:** 409 trips `if (!r.ok) throw` at `:2832` — the client must special-case it and *join* the stream. |
| Retried POST (network flake) | `client_turn_id` idempotency key → attach, don't create. |
| Client leaves forever | Bounded by accumulator cap; turn completes → persists → TTL evicts. Slot held for the real generation duration — correct, that's the point. 10 fire-and-leave prompts burn 10 serial generations; intended. |
| Backend wedges | Slot held until restart; capacity 1 → chat dead. **Unfixable in-process** (§6.2). Diagnose via `scheduler.snapshot()` + in-flight turn ids; document restart-required. |
| Torn last JSONL line | Per-line skip + count + log (§6.6.2). |
| Compare mode | Two branches, two turns, two slots; at capacity 1, B queues behind A — already true today. Branch dimension in the invariant + `read_history(cid, branch)`. |
| `rm -rf lab/pkb` while running | `open(path,"a")` → FileNotFoundError; **the in-memory ring still holds plaintext**, violating "wipe = forget". mkdir-per-write (copy `write_teacher_qa:807`, *not* `activity.py`'s mkdir-once) + a `purge()` that drops rings. |
| Unclamped `max_tokens` (`:6781`) | Clamp — it currently bounds the accumulator. |
| Storage growth | ~2× reply bytes + framing ≈ 5 KB/turn ≈ 180 MB/yr at 100 turns/day. Acceptable. Compaction (rewrite + atomic rename, dropping `progress` for settled turns) is compatible with append-only — that forbids in-place mutation, not rewriting. Defer; `reset pkb` is the user's lever. |

## 9. Test strategy

Per ARAIL's QA gating (30% setup / 30% Buddy / 20% security / 10% happy / 10% regression).
pytest, flat `tests/`, markers `qa` / `e2e` / `perf`.

> **Testability contract:** every new function takes `pkb_root: Path | None = None`. This is the
> repo-wide convention (`tests/conftest.py`) that makes `tmp_path` isolation work — the agent/PKB
> path already follows it everywhere.

- **Invariants** — one in-flight turn per `(cid, branch)`; `seq` monotonic; orphan = no terminal
  event; fold determinism; `turn.completed` immutable.
- **Regression, the §2.1 bug** — assert the slot is **not** released while the worker thread
  runs (fails on current code); assert two concurrent generations cannot start at capacity 1.
- **Privacy (security tier)** — `loadModel()` warm ping writes **nothing**; `.jsonl` stays out of
  `_PKB_TEXT_SUFFIXES`; PKB wipe removes transcripts **and** in-memory rings; no transcript
  egress (`egress.py`).
- **Gate** — a fact with no locatable span is rejected; a fact distilled from *assistant* output
  is rejected; unapproved facts are invisible to `search_for_agents`.
- **Crash** — kill mid-stream → restart → no turn stuck running; partial preserved; sweep is
  idempotent across two runs.
- **Torn line** — truncated last line → prior turns still readable.
- **Teacher regression** — `/api/teacher/stream` (`:11257-11289`) still works.
- **Resume** — offset math; navigate-away-and-return; two tabs joining one stream; `rebase` when
  `from_seq` predates the ring.

## 10. Code seams (build phase)

| File:line | Change |
|---|---|
| **new** `src/arail/portal/chat_turns.py` | Registry, rings, accumulator, fan-out, TTL, sweep (`activity.py` pattern + the two divergences in §6.6) |
| **new** `src/arail/portal/static/js/ndjson.js` | Shared NDJSON transport + `AbortController` (matches the `/static/js/*.js` convention; `chat.html:5` already loads `chat-highlight.js`) |
| `src/arail/pkb.py:796` | `chat_transcript_path` / `append_chat_event` / `read_chat_events` next to `write_teacher_qa`; **mkdir-per-write** |
| `src/arail/pkb.py:376` | Invariant + test: `.jsonl` stays out of `_PKB_TEXT_SUFFIXES` |
| `src/arail/portal/scheduler.py:145-194` | Additive `acquire_slot`/`release_slot`; **keep the CM** for `world_routes.py`'s 5 sites |
| `src/arail/portal/app.py:737` | Startup: `reconcile_orphans()` + janitor task — **hold the task ref** (§2.4) |
| `src/arail/portal/app.py:1074` | Shutdown: bounded drain, markers, **never await generations** |
| `src/arail/portal/app.py:6213-6235` | `_stream_sync_iterator`: release slot on sentinel, not generator close |
| `src/arail/portal/app.py:6238` | `_run_chat_completion_stream` → detached-task producer (**Teacher shares this**) |
| `src/arail/portal/app.py:6277`/`6321` | Slot lifetime → thread lifetime (`add_done_callback`) |
| `src/arail/portal/app.py:6748-6790`, `6781` | Create-or-attach; persist iff `conversation_id`; 409 path; clamp `max_tokens` |
| `src/arail/portal/app.py:11257-11289` | Teacher must keep working through the refactor |
| `src/arail/agents/_builtin_buddy.py:68-95`, `:1057-1090` | `recall_user_facts` host method + prompt fold |
| `src/arail/lab_brain.py:604`, `:644-693` | Token-bounded fact injection; verify frozen-vs-volatile placement |
| `chat.html:2743/2777/2826/2942/3418` | `buildBody` drops `history`; `send` carries cid/branch/idempotency; `streamChat` gains resume + abort; rehydrate on load; `loadModel` sends **no** `conversation_id` |

**The three readers stay separate.** Extract the *transport* (`getReader` + `TextDecoder` +
newline splitting + bad-line tolerance + `AbortController`), not the semantics. `streamChat`
needs reconnect/rebase; `loadModel` needs error-detection only and must never persist;
`teacher.html:281` has its own save path. All three already ignore unknown fields, so `seq` /
`rebase` / `heartbeat` are safe additions. Forcing shared semantics would couple Teacher and the
warm ping to chat's resume logic for no benefit.

## 11. Open risks

- **The slot/thread fix (§6.2) is load-bearing and not fully traced.** If any backend spawns its
  *own* threads or subprocesses, thread-completion is still the wrong release boundary. Verify
  every `deep_backend.complete()` implementation before committing.
- **Unverified:** whether `reset.sh` requires the server stopped. If it can run against a live
  portal, the `rm -rf` + live-ring case is a real contract violation rather than theoretical.
- **Single-worker assumption — now a permanent invariant, not a risk.** The founder ruled on
  2026-07-16 that **ARAIL will never have multi-user hosted memory** ([ADR-0003](../../docs/adr/0003-why-not-letta-memgpt.md)),
  so the module-level registry needs no sharding story. Still document at the registry that it
  would shard silently under `--workers > 1`, since that is a foot-gun regardless of tenancy.
  Note this does **not** retire concurrent *tabs* (one user, two windows) — that stays real and
  is handled by the `(conversation_id, branch)` invariant and the 409 path.
- **No `user_id`, ever.** Per ADR-0003, `conversation_id` is the only identity in the schema.
  If a future change wants a user column, that is a signal something has gone wrong upstream.
- **Deliberately not designed: a stop/cancel button.** It becomes *expressible* (mark the turn
  abandoned), but **the compute cannot be stopped** — no path in this codebase can interrupt a
  running generation thread. A "Stop" button that doesn't stop anything is worse than none. Real
  cancellation needs process isolation for the backend.
