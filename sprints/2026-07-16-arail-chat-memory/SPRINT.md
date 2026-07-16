# Sprint: arail-chat-memory

**ID:** 2026-07-16-arail-chat-memory
**Started:** 2026-07-16
**Product:** arail
**Reference plan:** /Users/netsushi/.claude/plans/task-design-persistent-shimmying-twilight.md (approved by user)
**Target branch:** `qukaizen/arail-chat-memory` — **not yet created.**

> **Branch note (2026-07-16):** these design artifacts were written while the ARAIL working
> tree was on `qukaizen/arail-dac-librarian`, which carries unrelated in-progress Librarian/World
> work. The `qukaizen/arail-persistent-chat-memory-2864fb` branch named in the session context
> belongs to the sibling **qukaizen-dac** worktree, not this repo. Before the build phase,
> move this sprint onto its own `qukaizen/arail-chat-memory` branch off `main` so the chat-memory
> work doesn't entangle with the Librarian sprint.

## Task

Design persistent chat memory for the Chat tab, governed by DaC-style data consistency.

Two needs:

1. **Live continuity** — the current conversation survives tab switches, reloads, and
   mid-stream navigation; an in-flight response keeps generating server-side and is
   recoverable on return.
2. **Durable understanding** — a retained record of past conversations that Buddy and other
   agents draw on to understand the user across sessions. Long-term memory, not a session cache.

**This pass is design only.** No product code. Deliverables are ARCHITECTURE.md, ADR-0002,
`docs/conversation-memory.md`, and updates to `CLAUDE.md` / `docs/agents.md`.

**Out of scope (fast-follow):** the full Tier-2 distillation loop (the interface and gate are
specified here; the extractor itself is a later sprint), a stop/cancel button (see Decisions
log), and transcript compaction.

## Phases

| Phase | Subagent | Artifact | Status | Finished | Verdict |
|---|---|---|---|---|---|
| think | visionary | VISION.md | **skipped** | — | see decisions log |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-07-16 | — |
| build | builder | BUILD_LOG.md | not started | — | — |
| review | architect (review) | REVIEW.md | not started | — | — |
| test | qa | TEST_REPORT.md | not started | — | — |
| ship | — | — | not started | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-07-16 | Skip visionary phase | The win condition is stated concretely in the task and confirmed by the user via AskUserQuestion (three architecture choices). No framing ambiguity to resolve. |
| 2026-07-16 | **DaC: discipline, not pipeline** | Confirmed by user. DaC is a build-time pipeline that explicitly defines itself against paging conversation history in/out of a mutable store (`CONTEXT_VM.md:208-210`), has no runtime (`README.md:55`), and whose one ARAIL seam runs the other direction (ADR-0004 D4: "ARAIL only reads"). Claiming DaC governs chat memory would breach DaC's own honesty rail (`README.md:65`). DaC = control plane, ARAIL = data plane — which is what DaC's ADR-0005 already says DaC is. Full argument: ADR-0002. |
| 2026-07-16 | **Storage: JSONL transcript + PKB markdown facts** | Confirmed by user. Rejected SQLite (no precedent in-repo; and siting data outside the PKB root breaks the documented "wipe the PKB = wipe memory" contract) and JSON+Lance dual-write (`agent_workflows._save` rewrites the whole file per update — O(n) per message, racy across tabs). Tier 2 as PKB notes inherits the LanceDB index, `search_for_agents`, the Compiled-KB gate, and the wipe contract with no new machinery. |
| 2026-07-16 | **Gate: reuse the Compiled-KB approval gate** | Confirmed by user. Facts are propose-only with provenance; only approved facts reach agents (`pkb.py:666-672`). Guards the real risk named in DaC's `DAC_ENGINE.md:153-155` — an agent distilling from its own output then believing itself. |
| 2026-07-16 | Streaming: detached task + subscriber response | `BackgroundTasks` runs *after* the response (structurally cannot produce the body); `asyncio.shield` cannot wrap an async generator's iteration and lands at the same design anyway; WebSocket dies on page unload. Also immune to the Starlette `spec_version` cancellation branch, which a uvicorn bump could silently flip. |
| 2026-07-16 | Invariant is per `(conversation_id, branch)`, not per conversation | Compare mode legitimately runs two generations under one user turn (`chat.html:2788`/`2942`). "One in-flight turn per conversation" would break it. |
| 2026-07-16 | Persistence keyed on `conversation_id` presence | Both the migration lever (no id → current behavior verbatim) and the fix for `loadModel()` (`chat.html:3418`), a warm-up ping that POSTs to `/api/chat/stream` and would otherwise write junk into the user's PKB on every LOAD click. |
| 2026-07-16 | **No stop/cancel button**, despite it becoming expressible | Nothing in this codebase can interrupt a running generation thread (`app.py:6218-6227` daemon thread; `to_thread` futures are uncancellable once running). A "Stop" button that doesn't stop compute is worse than no button. Real cancellation needs process isolation for the backend — a much larger change. |

## Skipped phases

**think / visionary** — skipped per the decisions log above.

## Findings that changed the design

Design-time verification overturned three premises in the task brief and surfaced a live bug.
All are recorded with evidence in ARCHITECTURE.md § "What the investigation changed".

1. **Live bug — the inference slot leaks on client disconnect.** `scheduler.inference_slot`
   releases the semaphore in a `finally` around a `yield` (`scheduler.py:184-194`), so
   navigating away releases the slot **while the GPU thread is still running**
   (`app.py:6218-6227` starts a `daemon=True` thread that drains to completion regardless of
   the consumer). With `ARAIL_INFERENCE_CONCURRENCY` defaulting to 1 — an OOM guard
   (`scheduler.py:26-30`) — the next chat starts a second concurrent generation. **This design
   fixes that bug rather than adding risk: generation is already background, just discarded and
   slot-corrupting.**
2. **`chat.html:3418` is not a chat parser** — it is `loadModel()`, a warm-up ping. The brief
   treated it as a second history reader.
3. **A third reader exists:** `POST /api/teacher/stream` (`app.py:11257-11289`) shares
   `_run_chat_completion_stream`. Any signature change breaks Teacher.
4. `start-portal.sh:6` runs `--reload` — restart-mid-stream is the default dev loop, not exotic.
5. `pkb.py:376` includes `.json` but not `.jsonl` in `_PKB_TEXT_SUFFIXES` — naming the
   transcript `.json` would vector-index every chat turn into the wiki.

## Pre-existing drift found (flagged, not fixed here)

- `CLAUDE.md:219` says `lab/pkb/.wiki-cache/lancedb/`; `pkb.py:407-408` uses `.cache/lancedb`.
- The built-in agent roster disagrees across `CLAUDE.md:201-203`, `docs/agents.md:39-47`, and
  `loader._SHIPPED` (`loader.py:62`).
- `reset.sh:94` hardcodes `lab/pkb`, ignoring the `LAB_PKB` override — a real privacy bug,
  since it makes `./arailctl reset pkb` a false success for anyone who moved their PKB.
