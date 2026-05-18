# Architecture: recap-core (Sprint 1)

**Date:** 2026-05-17
**Spec:** [/Users/netsushi/.claude/plans/i-feel-like-we-radiant-snail.md](file:///Users/netsushi/.claude/plans/i-feel-like-we-radiant-snail.md) (approved); paper arXiv:2510.23822
**Sprint ledger:** [SPRINT.md](./SPRINT.md)

## Restatement

Build a self-contained, model-agnostic Python module at `src/arail/agents/recap/` that implements ReCAP Algorithm 1 — plan-ahead decomposition, recursive descent into non-primitive subtasks, parent re-injection on backtrack, sliding-window K=64 memory — on top of the existing `arail.router.ModelRouter`. Five paper-§D.1 prompt templates drive the LLM. State lives in a context tree of `(T, S)` nodes (task description, accumulated state). An `Environment` Protocol is the seam to (later) the Researcher; for Sprint 1, only a Robotouille-shaped mock fixture implements it. No backend changes, no UI, no Researcher wiring (Sprint 2). Existing `ModelRouter.complete(prompt, ...)` callers remain bit-identical. `arail.costs.CostTracker.track()` gains an optional `recap_depth=` field, defaulting to `None` so non-ReCAP callers are unaffected. Exit: pytest green; mock-env Robotouille task succeeds within step budget.

## Assumptions

- The five §D.1 prompt templates as written are sufficient — no in-house prompt tuning needed for Sprint 1.
- ModelRouter's underlying backends will not honor structured-output / function-calling APIs uniformly; we will rely on text JSON inside a fenced block and a tolerant parser.
- Sliding-window K=64 LLM **calls** of context (per paper §2.4); a "call entry" = one (prompt, response) pair.
- Backends accept only `prompt: str` (verified — see `src/arail/router/backends.py:63`). Multi-turn history is flattened by the adapter, not pushed into a backend message-list API.
- Recursion depth in practice ≤ 6 (paper observed depths of 3–5 on Robotouille / SWE-bench). Hard cap at 8 in code.
- Mock fixture is sufficient evidence — we are **not** required to install Robotouille; we replicate its action/observation shape only.
- `arail.costs.cost_tracker` is a module-level singleton (verified at `src/arail/router/core.py:10`).

## Data flow

```
                    +---------------------------+
   user goal  --->  | recap.core.RecapAgent.run |
                    +-------------+-------------+
                                  |
                                  v
                        +---------------------+
                        |   ContextTree root  |  state.py
                        +---------+-----------+
                                  |
              (1) initial decomposition prompt (D.1.1)
                                  v
                       +----------+----------+
                       |  RouterAdapter      |  router_adapter.py
                       |  .chat(messages)    |
                       +----------+----------+
                                  |
                                  v
                       arail.router.ModelRouter.complete(prompt)
                                  |
                          response text
                                  v
                  +---------------+----------------+
                  | schema.parse_think_subtasks    |  schema.py
                  +---------------+----------------+
                                  |
                  {think, subtasks: [{id, desc, primitive}]}
                                  |
              for each subtask:
                  primitive=True  -> env.step(action); record obs
                  primitive=False -> recurse: new ContextNode,
                                     recursive-downward prompt (D.1.2)
                                  |
              on child return:    parent-completion (D.1.4)
                                     or leaf-backtrack (D.1.3) /
                                     leaf-failure (D.1.5)
                                  |
                                  v
              final answer / terminal env state
                                  |
                                  v
              cost_tracker.track(..., recap_depth=node.depth) per call
```

## Module layout

`src/arail/agents/recap/`

| File | Purpose |
|---|---|
| `__init__.py` | Re-exports `RecapAgent`, `Environment`, `ContextNode`. |
| `core.py` | `RecapAgent` class + `run()` driving Algorithm 1; recursion, backtrack, retry counters, step budget. |
| `prompts.py` | Five §D.1 templates as module-level constants + `.format()` helpers: `INITIAL_DECOMP` (D.1.1), `RECURSIVE_DOWNWARD` (D.1.2), `LEAF_BACKTRACK` (D.1.3), `NONLEAF_COMPLETION` (D.1.4), `LEAF_FAILURE` (D.1.5). Also the periodic-rule-reminder snippet (§A). |
| `state.py` | `ContextNode` dataclass (T, S, parent, children, depth, retries, history list), `ContextTree`, sliding-window enforcement (`window(history, k=64)`), history-truncation policy from §A (keep entry 0, drop entries 2–3 on overflow). |
| `schema.py` | JSON schema definition + `parse_think_subtasks(text) -> ThinkSubtasks` with tolerant best-effort fallback. Confined to one file so the schema contract is easy to audit. |
| `router_adapter.py` | `RouterAdapter` wrapping `ModelRouter`; exposes `chat(messages, max_tokens, temperature, depth) -> str`. Flattens messages into a single prompt; threads `recap_depth` into `cost_tracker.track()` via the new kwarg. |
| `environment.py` | `Environment` Protocol (`reset() -> Observation`, `step(action) -> Observation`, `is_terminal() -> bool`, `score() -> float | None`). Plus `Action` / `Observation` value types. |
| `fixtures/robotouille_mock.py` | Deterministic Robotouille-shaped mock env for tests. Discrete action verbs, observation strings. Used by both unit tests and the integration test. |

I confirm the plan's four named files and **add three**: `schema.py` (JSON contract isolation), `environment.py` (Protocol + value types — explicitly required by Sprint 2's seam), and `fixtures/robotouille_mock.py` (so tests don't redefine the mock five times).

A `tree.py` is **not** needed; `ContextNode` + a thin `ContextTree` in `state.py` are sufficient at Sprint-1 scope.

## Algorithm 1 in code (pseudocode)

```
# Reference: Paper §2 Algorithm 1; prompts in §D.1
def RecapAgent.run(goal_text) -> RunResult:
    root = ContextNode(T=goal_text, S=[], parent=None, depth=0)
    tree = ContextTree(root)

    # Step 1 — initial decomposition (paper §2.1 / D.1.1)
    resp = adapter.chat(messages=[{"role":"system","content":SYSTEM_RULES},
                                  {"role":"user","content":INITIAL_DECOMP.format(goal=goal_text)}],
                        depth=0)
    plan = schema.parse_think_subtasks(resp)
    root.plan = plan

    steps = 0
    return _descend(root, tree, steps_budget)

def _descend(node, tree, budget) -> NodeResult:
    for subtask in node.plan.subtasks:
        if steps >= budget: return NodeResult.BUDGET_EXCEEDED
        if subtask.primitive:
            # Leaf — execute in environment
            obs = env.step(Action.from_subtask(subtask))
            node.S.append(("act", subtask, obs))
            steps += 1
            if obs.failed and node.retries < LEAF_RETRY_CAP:
                # Leaf-backtrack (D.1.3)
                resp = adapter.chat(_messages_for(node, LEAF_BACKTRACK, obs), depth=node.depth)
                node.plan = schema.parse_think_subtasks(resp)  # replan within this node
                node.retries += 1
                return _descend(node, tree, budget)
            elif obs.failed:
                # Leaf-failure (D.1.5) — signal failure upward
                resp = adapter.chat(_messages_for(node, LEAF_FAILURE, obs), depth=node.depth)
                return NodeResult.FAILED(reason=resp)
        else:
            # Non-primitive: recurse with parent re-injection
            child = ContextNode(T=subtask.desc, S=[], parent=node, depth=node.depth+1)
            tree.add(child)
            # Recursive-downward (D.1.2) — re-inject parent T and parent S window
            resp = adapter.chat(_messages_for(child, RECURSIVE_DOWNWARD,
                                              parent_plan=node.plan, parent_state=window(node.S)),
                                depth=child.depth)
            child.plan = schema.parse_think_subtasks(resp)
            result = _descend(child, tree, budget)
            # Propagate child summary back to parent.S (paper §2.2)
            node.S.append(("child_return", subtask.id, result.summary))
            if result.failed and node.retries < NONLEAF_RETRY_CAP:
                # Non-leaf-completion replan with failure context (D.1.4)
                resp = adapter.chat(_messages_for(node, NONLEAF_COMPLETION, child_result=result),
                                    depth=node.depth)
                node.plan = schema.parse_think_subtasks(resp)
                node.retries += 1
                return _descend(node, tree, budget)
    # All subtasks completed — emit non-leaf-completion summary upward (D.1.4)
    resp = adapter.chat(_messages_for(node, NONLEAF_COMPLETION, completed=True), depth=node.depth)
    return NodeResult.OK(summary=resp)
```

Constants: `LEAF_RETRY_CAP=2`, `NONLEAF_RETRY_CAP=2`, `MAX_DEPTH=8`, `DEFAULT_STEP_BUDGET=120`. Every `MAX(_)`th call inserts the §A periodic rule reminder into the system slot.

## State model

`ContextNode` (dataclass):

| Field | Type | Notes |
|---|---|---|
| `T` | `str` | Task description (paper §2.1). |
| `S` | `list[StateEntry]` | Accumulated state; entries are typed (`("act", subtask, obs)`, `("child_return", id, summary)`, `("note", text)`). |
| `parent` | `ContextNode | None` | None for root. |
| `children` | `list[ContextNode]` | |
| `depth` | `int` | Root=0. |
| `retries` | `int` | This node's replan count. |
| `plan` | `ThinkSubtasks | None` | Last LLM decomposition output. |
| `history` | `list[dict]` | Chat-message history for this node (used by adapter; sliding-window applied at call time, not at append time, so we preserve full history on disk for debug). |

`ContextTree` provides `add`, iteration, and `serialize_for_debug()` (JSON dump). Tree is in-memory only Sprint 1.

**Sliding-window K=64** (paper §2.4): enforced by `state.window(history, k=64)`, called by `RouterAdapter.chat` right before flattening. The first entry (system rules + initial decomp summary) is **always** kept (paper §A pinning rule). Of the remaining `len-1` entries, keep the most recent `k-1`. Active prompt cost is therefore O(K·L̄). The full `history` lives in the node (external state O(d·L̄)) and is never pruned in memory — only what's passed to the LLM is windowed.

**§A truncation policy** (when a single concatenated prompt exceeds backend context): keep entry 0, drop entries 2–3, then re-emit the periodic rule reminder. Implemented as `state.truncate_for_context(history, max_tokens)` invoked by the adapter when its naive flatten exceeds `RECAP_PROMPT_TOKEN_BUDGET` (default 6000 chars ≈ 1500 tokens; configurable env var).

## JSON schema contract

The LLM must emit, in a fenced ```json``` block:

```json
{
  "think": "free-text reasoning",
  "subtasks": [
    {"id": "s1", "desc": "...", "primitive": true,  "action": "OPEN(door_1)"},
    {"id": "s2", "desc": "...", "primitive": false}
  ]
}
```

Schema (paper §C.4): `think: str` required; `subtasks: list` required, each item with `id: str`, `desc: str`, `primitive: bool`. `action: str` is required iff `primitive=true`. Extra fields ignored.

**Recommendation: tolerant parse with strict re-prompt on failure.** Reasoning:

1. Backends are heterogeneous (MLX small models, cloud big models, AirLLM mid). Strict-only fails too often on small local models — fatal for `minimalist` tier.
2. Pure best-effort silently masks model misbehavior — bad for debugging and for cost.

Implementation in `schema.parse_think_subtasks(text)`:

1. Extract fenced ```json block; if absent, scan for the first balanced `{...}`.
2. `json.loads` → validate against the schema.
3. On `ValidationError`: emit one **re-prompt** (`"Your last response did not match the required JSON shape. Re-emit only the JSON object."`) — exactly one retry.
4. If the retry also fails: raise `SchemaError`. The caller (`core._descend`) treats `SchemaError` as a node failure, triggers `LEAF_FAILURE` or replans via `NONLEAF_COMPLETION` like any other failure. Logged at `warn` to `activity_log`.

Activity-log emission on schema failures uses the same `prompt_trace` key the Researcher already uses (`researcher.py:196`) so the Prompt Inspector picks them up.

## Router adapter

Existing surface in `src/arail/router/core.py`:

```
ModelRouter.complete(prompt: str, max_tokens=512, temperature=0.7, top_p=None) -> ModelResponse
```

Constraint: existing callers untouched. Backends accept only a single prompt string (verified `backends.py:63, 131, 253, ...`) — no backend currently has a `messages=` parameter.

**Decision: do NOT modify `ModelRouter`. Instead, add a wrapper class.**

```python
# src/arail/agents/recap/router_adapter.py
class RouterAdapter:
    def __init__(self, router: ModelRouter, *,
                 max_tokens: int = 512, temperature: float = 0.7,
                 prompt_token_budget: int = 6000):
        self.router = router; ...

    def chat(self, messages: list[dict], *,
             depth: int = 0,
             max_tokens: int | None = None,
             temperature: float | None = None) -> str:
        flat = self._flatten(messages)  # role-tagged single string
        if len(flat) > self.prompt_token_budget * 4:  # rough chars->tokens
            messages = truncate_for_context(messages, ...)
            flat = self._flatten(messages)
        # Pass depth via thread-local so the cost_tracker.track() inside
        # ModelRouter.complete picks it up without changing complete()'s
        # signature. (See "Cost telemetry" below.)
        with _recap_depth_context(depth):
            resp = self.router.complete(flat,
                                        max_tokens=max_tokens or self.max_tokens,
                                        temperature=temperature or self.temperature)
        return resp.text
```

Flatten format (role-tagged, model-agnostic):

```
<<SYSTEM>>
{system content}

<<USER>>
{user content}

<<ASSISTANT>>
{assistant content}

<<USER>>
{...}
```

Rationale for `RouterAdapter` rather than a new `ModelRouter.complete_chat(messages, ...)`:

- No risk to non-ReCAP callers (regression goal in QA allocation).
- Backends would all need a parallel `complete_chat` implementation; out of scope for Sprint 1.
- If/when a backend gains native chat support (e.g., Claude SDK already does), `RouterAdapter._flatten` can be made backend-aware behind a single conditional without re-plumbing ModelRouter.

**Tech debt note:** future sprint should promote chat-formatting into `ModelRouter` once at least two backends benefit. Recorded below.

## Environment abstraction

```python
# src/arail/agents/recap/environment.py
from typing import Protocol

@dataclass(frozen=True)
class Action:
    verb: str
    args: tuple[str, ...] = ()
    @classmethod
    def from_subtask(cls, st) -> "Action": ...

@dataclass(frozen=True)
class Observation:
    text: str
    failed: bool = False
    info: dict | None = None

class Environment(Protocol):
    def reset(self) -> Observation: ...
    def step(self, action: Action) -> Observation: ...
    def is_terminal(self) -> bool: ...
    def score(self) -> float | None: ...  # None if env can't score mid-run
```

Sprint 2 will wire the Researcher's pipeline stages (plan/design/sources/run/analyze/report) as a thin `ResearcherEnvironment` adapter — out of scope here, only the Protocol shape must accommodate that.

**Mock fixture** (`fixtures/robotouille_mock.py`):

- Verbs: `PICK`, `PLACE`, `COOK`, `CHOP`, `SERVE`, `OPEN`, `CLOSE`, `INSPECT`.
- Deterministic recipe goal ("cook burger and serve") solvable in ~12–18 steps.
- Optional `inject_failure(at_step=N, mode={"invalid_action","resource_missing"})` to test backtrack/replan paths.
- Pure-Python, no external deps.

## Cost telemetry

`arail.costs.CostTracker.track()` (line 238) signature today:

```python
def track(self, backend, model, tokens_in, tokens_out, latency_ms, source="agent") -> CostRecord:
```

**Change:** add optional `recap_depth: int | None = None`. Default preserves every existing caller. Record stores it; in-memory `_history` rolling buffer (line 303) gains `"recap_depth": recap_depth`. Aggregation: a new `self.calls_by_recap_depth: dict[int,int]` counter.

`ModelRouter.complete()` and `stream_complete()` (router/core.py:45, 63) do **not** change signature. Instead, `track()` is called by `ModelRouter` reading a thread-local set by the `RouterAdapter` context manager:

```python
# src/arail/costs.py — new helper
_recap_depth_tls: contextvars.ContextVar[int | None] = ContextVar("recap_depth", default=None)

def current_recap_depth() -> int | None: return _recap_depth_tls.get()
```

`ModelRouter.complete()` adds **one line**:

```python
cost_tracker.track(..., source=self.billing_source, recap_depth=current_recap_depth())
```

This is the minimum invasive change required. All non-ReCAP callers see `recap_depth=None` (the contextvar default), and behavior is unchanged.

## Failure modes & invariants

| Failure | Detection | Recovery / Invariant |
|---|---|---|
| LLM emits malformed/missing JSON | `schema.parse_think_subtasks` fails to extract or validate | One re-prompt; if still bad, raise `SchemaError`, treat as node failure, replan via D.1.5 / D.1.4. Logged to `activity_log` at warn with `prompt_trace`. |
| Recursion depth runaway (model keeps decomposing) | `node.depth >= MAX_DEPTH` (=8) | Force `primitive=True` on remaining subtasks at that node; emit leaf failure if env rejects. Counted toward step budget. |
| Step budget exhausted | `steps >= budget` checked before each env action and each LLM call | Return `NodeResult.BUDGET_EXCEEDED` with partial state; do not silently succeed. |
| Sliding window evicts the system rules / initial decomp | `state.window()` pins entry 0 | Invariant: `windowed[0] is history[0]` always. Unit test asserts this for window sizes K=1..64. |
| History truncation loses parent plan during deep recursion | `_messages_for(child, RECURSIVE_DOWNWARD, ...)` always re-injects `parent.T` and `window(parent.S)` from the **parent node object**, not from chat history | Invariant: the recursive-downward prompt's parent-plan slot is always populated from the tree, independent of windowed history. Unit test: drop chat history to k=1, recursive descent still re-injects parent T+S. |
| Env raises exception | try/except around `env.step()` in `core._descend` | Treat as a failed observation (`Observation(failed=True, text=str(exc))`); continue with leaf-backtrack path. Never propagate raw exceptions through `RecapAgent.run`. |
| Infinite replan loop (same node replans forever) | `node.retries` cap (LEAF=2, NONLEAF=2) | After cap, propagate `NodeResult.FAILED` upward — parent gets a chance to replan around it. |
| Cost runaway | `cost_tracker.total_billed_usage_usd` checked once per N=10 LLM calls against `RECAP_COST_CEILING_USD` (env, default $5/run) | Abort with `NodeResult.COST_EXCEEDED`; emit warn activity event. |
| Backend prompt-size overflow | Adapter pre-check on `len(flat) > prompt_token_budget*4` | Run `truncate_for_context` per §A (drop entries 2–3, keep 0, re-emit reminder); if still over, drop oldest non-pinned until fits. |
| Concurrent `RecapAgent.run` calls clobbering each other's `recap_depth` contextvar | `contextvars.ContextVar` is per-async-context / per-thread by default | No shared mutable state; each `run()` operates on its own `ContextTree`; verified via concurrent unit test. |
| Ambiguous `primitive` field (model says non-primitive for a clearly-leaf action) | Schema permits whatever the model says | Always honored; if env rejects, leaf-backtrack handles it. Documented behavior. |

## Test strategy

QA allocation (per SPRINT.md): **60% correctness / 20% edge / 10% cost / 10% regression**.

### Unit (`tests/test_recap_state.py`, `tests/test_recap_schema.py`, `tests/test_recap_adapter.py`)
- `state.window`: pinning of entry 0; K=1..64 size honored; idempotence.
- `state.truncate_for_context`: §A policy verified (drop 2–3, keep 0, reminder re-emitted).
- `schema.parse_think_subtasks`: valid JSON; fenced JSON; bare JSON; missing field → ValidationError; primitive=true without action → ValidationError; tolerant re-prompt path.
- `router_adapter.chat`: message flatten format stable across role orderings; prompt-budget truncation; `recap_depth` contextvar set during call and reset after.
- `ContextNode`/`ContextTree`: parent links, depth math, serialization round-trip.

### Algorithm correctness (`tests/test_recap_core.py`) — primary
Uses a **scripted LLM stub** (deterministic responses keyed by prompt-prefix match) and the Robotouille mock env.

- Happy path: scripted decomp → all leaves succeed → success returned in ≤ budget.
- Recursive descent: depth-2 plan, both branches succeed; verify parent re-injection (assert recursive-downward prompt contains parent's T).
- Leaf-backtrack: env injected failure at step N; assert LEAF_BACKTRACK prompt fires; node retries; succeeds on retry.
- Leaf-failure cap: failures exceed `LEAF_RETRY_CAP`; assert LEAF_FAILURE prompt fires; node returns FAILED.
- Non-leaf replan: child returns FAILED; parent fires NONLEAF_COMPLETION-with-failure; replans; succeeds.
- Sliding window: drive history past K=64 entries; assert prompt sent to LLM stub always contains entry-0 and only K newest others.
- Parent-plan re-injection invariant: even with history truncated to k=1, recursive-downward still carries parent.T and parent.S window.
- Periodic rule reminder: assert it appears every 10 calls in the rendered prompt.

### Edge cases
- Malformed JSON (truncated, wrong fenced lang, prose around JSON).
- Depth runaway: stub keeps emitting `primitive=false`; assert `MAX_DEPTH` cap triggers, primitives forced.
- Step-budget exhaustion at depth 3 → BUDGET_EXCEEDED with partial trace.
- Env raises exception (`raise RuntimeError`) → treated as failed obs.

### Cost ceiling
- Test asserts `cost_tracker.calls_by_recap_depth` is populated and non-empty by depth.
- Test asserts `RECAP_COST_CEILING_USD=0.0001` aborts the run with COST_EXCEEDED.
- Regression: non-ReCAP call to `ModelRouter.complete()` stores `recap_depth=None` in `_history`.

### Regression
- `pytest tests/` (existing suite) passes with no router/cost_tracker churn.
- `grep` for callers of `cost_tracker.track(` confirms no signature break (all callers used the kwargs that remain).

### Integration
- `tests/test_recap_robotouille_mock.py` — run the full mock burger task end-to-end with the scripted-LLM stub; assert success, step count ≤ 25, depth ≥ 2 reached, at least one backtrack exercised (when failure injection enabled).

### Fixture shape
- `fixtures/robotouille_mock.py` exposes `make_env(seed=0, inject_failures: list | None = None)`.
- `fixtures/scripted_llm.py` (test-only) exposes `ScriptedRouter(responses: dict[str, list[str]])` matching prompt prefixes to canned responses; queued list per prefix; raises if exhausted (so tests fail loudly on prompt drift).

## Tech debt assessment

**Added:**
- Thread-local `recap_depth` contextvar in `arail.costs` — small global, easy to misuse. Mitigated by single-call-site contextmanager in adapter.
- `RouterAdapter` is the second LLM call surface in ARAIL (alongside `ModelRouter.complete`). Future agents may use one or the other inconsistently.
- Flatten-then-prompt loses any chat-aware structured-output capabilities (Claude/OpenAI tool-use). Acceptable for Sprint 1, paying ~3× ReCAP overhead anyway.
- Robotouille mock is paper-shaped, not paper-identical. Risk: passing the mock does not guarantee parity on real Robotouille.

**Repaid:**
- `cost_tracker.track()` gains structured per-call depth labeling — useful beyond ReCAP for any nested-call instrumentation.
- Codifies the §A truncation policy as reusable `state.truncate_for_context` — first place in ARAIL with a documented context-eviction policy.

**Net:** Slightly positive (more surface added than reduced). Acceptable for a framework module slated to grow.

**Deferred to Sprint 2+:**
- Researcher wiring (`researcher_recap.py`, env adapter, flag plumbing).
- Native chat-message support in `ModelRouter` (when ≥2 backends benefit).
- Real Robotouille integration (only if Sprint 3 bakeoff demands it).
- Persistent tree serialization for the Dashboard prompt inspector.
- LangChain-style tool-call structured output for backends that support it.

## Recommended implementation order

1. `environment.py` (Protocol + Action/Observation value types). Smallest, contract-fixing.
2. `fixtures/robotouille_mock.py` + a smoke test that it works standalone.
3. `state.py` (ContextNode, ContextTree, window, truncate_for_context) + unit tests.
4. `schema.py` (parse + validate + tolerant fallback) + unit tests.
5. `prompts.py` (verbatim §D.1 templates; render helpers).
6. Contextvar + 1-line edit in `arail/costs.py` and `arail/router/core.py`.
7. `router_adapter.py` + adapter unit tests with a scripted router.
8. `core.py` (RecapAgent + Algorithm 1) + algorithm correctness tests.
9. `tests/test_recap_robotouille_mock.py` integration test.
10. Final pytest run; sanity-grep all `cost_tracker.track(` callers; commit.

---

**Verdict: proceed.** Design is buildable as-is, no blockers found.
