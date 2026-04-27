# Missions, explained

You typed a goal. You hit **Draft Swarm Plan**. Some boxes appeared.
This page explains what every word on that screen actually means and
what happens when you hit **Approve & Run**.

## The one-sentence version

**A mission is your goal plus the swarm of worker agents currently
running against it.**

One mission is active at a time. It lives on disk at
`lab/data/goals/current.json`. The dashboard's Mission card is a
view onto that file.

## The flow at a glance

```
type goal  →  Draft Swarm Plan  →  preview appears  →  edit / approve  →  researcher runs
   (you)         (no run yet)          (still no run)      (you)              (lab works)
```

Three things to internalize:

1. **`Draft Swarm Plan` does not run anything.** It only produces a
   reviewable plan. You can throw it away.
2. **You always get to look before you commit.** The preview shows the
   parsed goal, the lanes that will run, the phases, and the open
   questions. Edit it, untick lanes, rewrite the brief, then approve.
3. **`Approve & Run` is the trigger.** That's the moment the lab
   actually starts working. `Approve Only` stages the mission as
   active but holds the researcher at the gate.

## What `Draft Swarm Plan` actually does

When you click the button, the page POSTs `{ goal, scale }` to
`/api/goal/preview`. On the server:

1. **Parse the goal.** `GoalParser` (in
   `src/arail/skills/goal_parser/`) asks an LLM to extract:
   - **domain** (travel, ml-research, ops, general, …)
   - **primary_objective** — one crisp sentence
   - **sub_objectives** — the obvious branches
   - **success_metrics** — how you'd know you got it
   - **timeline** and **constraints**
   - **resources_needed**
   - a **confidence** score

   If the LLM is offline, a heuristic parser fills in the same shape
   from keyword matches. Either way you get the same output schema.

2. **Pick a goal archetype.** `detect_goal_archetype` (in
   `src/arail/swarm_goals.py`) looks at your goal text and assigns one
   of:
   - `travel` — trips, flights, hotels, rail, itineraries
   - `research` — benchmarks, evals, models, datasets, RAG, latency
   - `operations` — deploys, incidents, SLOs, runbooks, capacity
   - `general` — anything that doesn't match the above

   The archetype controls **which specialists are available** as lanes.

3. **Compile the swarm.** `compile_swarm_plan` builds the worker
   roster: always Scout + Critic at the front, then the archetype's
   specialists, sliced down to the **scale limit** you picked
   (see below).

4. **Save the preview.** It lands in `lab/data/goals/preview.json`
   with `status: "draft"`. **Nothing else has happened yet.** No
   agent is running, no files have been written to your knowledge
   base, no LLM tokens are being burned in a loop. You're holding
   a paper plan.

## Swarm scale — Compact, Balanced, Expanded

The scale word controls **how many parallel worker agents (lanes)**
the swarm spawns. The numbers come from `_SCALE_LIMITS` in
[src/arail/swarm_goals.py](../src/arail/swarm_goals.py):

| Scale | Lanes | Who's in the swarm | When to pick it |
|---|---|---|---|
| **Compact** | 3 | Scout + Critic + 1 specialist | Quick reconnaissance, cheap iteration, you just want a sketch |
| **Balanced** | 4 | Scout + Critic + 2 specialists | Default — solid coverage without overkill |
| **Expanded** | up to 6 | Scout + Critic + the archetype's full specialist roster | Thorough sweep, you want every angle covered |

Two things to know:

- **Lanes run in parallel.** Wider scale = more parallel work, more
  tokens, more time spent synthesizing.
- **`general` archetype caps at 5.** It only has 3 specialists, so
  Expanded gives you 5 lanes there, not 6. Travel, research, and
  operations all have 4 specialists and hit the full 6.

You can also set the default with the `ARAIL_SWARM_SCALE` env var.

## What a "lane" is

A lane is **one parallel worker agent**. Each lane has:

- a **label** (e.g. `Scout`, `Routing`, `Eval`)
- a **role** — one-line description of its job
- a **deliverable** — what it returns at the end
- an **enabled** flag — uncheck the box in the preview to drop it

### The two base lanes (always present)

| Lane | Job |
|---|---|
| **Scout** | Map the search space. Survey what options, sources, and routes matter before the lead narrows down. |
| **Critic** | Stress-test assumptions. Surface hidden risks, contradictions, and weak assumptions before the swarm commits. |

### The specialist lanes (depend on archetype)

For example, a `travel` archetype goal pulls in: **Seasonality**
(timing/weather/crowds), **Routing** (transport plan),
**Lodging** (stay shortlist), **Budget** (cost tradeoffs).

A `research` archetype goal pulls in: **Literature**, **Eval**,
**Variants**, **Synthesizer**.

`operations`: **Signals**, **Runbooks**, **Capacity**, **Reviewer**.

`general`: **Mapper**, **Evaluator**, **Synthesizer**.

The full catalog lives in `_BASE_WORKERS` and `_ARCHETYPE_WORKERS`
in [src/arail/swarm_goals.py](../src/arail/swarm_goals.py) — that
file is the source of truth.

## Editing the preview

In the preview panel you can:

- **Rewrite the Mission Brief.** This overrides the LLM's framing of
  the goal and is what the lead researcher reads first.
- **Add Operator Notes.** Extra steering for the swarm — constraints,
  preferences, things you want emphasized.
- **Uncheck lanes.** Any lane you uncheck is dropped from the run and
  removed from the phase plans that depended on it.

Changes only persist when you hit Approve. Discard Draft throws the
whole preview away (`DELETE /api/goal/preview`).

## Approve & Run vs Approve Only

Both buttons call `/api/goal/confirm` and promote the preview to the
**active goal** (`lab/data/goals/preview.json` → `current.json`,
status flips to `active`).

The difference is one flag:

| Button | `auto_start` | What changes |
|---|---|---|
| **Approve & Run** | `true` | Researcher loop kicks off immediately. Workers start producing deliverables. The activity feed lights up. |
| **Approve Only** | `false` | Mission is staged as active but the researcher waits. Useful when you want to inspect the dossier before letting agents loose. |

Both also fire a fire-and-forget `_auto_draft_program` task that
writes a research program to `lab/pkb/research/program.md`
(hypotheses, experiments, success criteria, expected timeline).

## What happens after Approve & Run

1. **Preview promoted to active goal.** Goal record now has the full
   parsed goal, swarm plan, and `status: "active"`.
2. **Researcher starts.** `researcher.start(parsed_goal)` (in
   `src/arail/agents/researcher.py`) sets the objective, flips status
   to `running`, and spawns an async loop that reads the parsed goal
   and the swarm plan.
3. **Workers run by lane.** Each enabled lane runs its role and
   produces its deliverable. Phases group lanes together
   (`shape → explore → synthesize`-style).
4. **Program drafter writes `program.md`.** A standalone draft of the
   research program lands at `lab/pkb/research/program.md` so a human
   can read the experimental plan in plain markdown.
5. **The dashboard streams progress.** The activity feed (SSE) emits
   events as phases land and deliverables arrive. The Mission card
   updates in place.

## Where to look next

- **Curated view →** in the Mission card header takes you to
  `/mission`, the full dossier: brief, lanes, phases, deliverables,
  open questions, activity log, and report.
- **`lab/data/goals/current.json`** — the raw goal record on disk.
  Everything the dashboard renders comes from here.
- **`lab/data/goals/preview.json`** — exists only between Draft and
  Approve. Goes away on Discard or after Approve.
- **`lab/pkb/research/program.md`** — the human-readable research
  program drafted on Approve.

## Discarding, replacing, restarting

- **Discard Draft** removes the preview only. The active goal (if
  any) is untouched.
- **Re-running Draft Swarm Plan** overwrites the staged preview but
  does **not** stop a goal that's already active.
- **Setting a new goal while one is active** promotes the new one to
  `current.json` on Approve. The previous goal record is archived
  under `lab/data/goals/history/`.

That's the whole loop. Type the goal, draft the plan, look at it,
approve it, watch it work.
