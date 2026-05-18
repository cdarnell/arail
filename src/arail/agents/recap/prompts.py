"""ReCAP §D.1 prompt templates and render helpers.

Five templates (paper §D.1):
  D.1.1  INITIAL_DECOMP         — initial task decomposition
  D.1.2  RECURSIVE_DOWNWARD     — sub-task decomposition (re-injects parent)
  D.1.3  LEAF_BACKTRACK         — primitive action failed; replan within node
  D.1.4  NONLEAF_COMPLETION     — child subtask finished; update or summarise
  D.1.5  LEAF_FAILURE           — primitive action exhausted retries; signal failure

Plus:
  SYSTEM_RULES                  — pinned system message (entry 0 in history)
  PERIODIC_RULE_REMINDER        — re-inserted every N=10 calls (§A)

All templates use str.format_map() so callers can pass only the keys they
need; extra keys are silently ignored via a permissive mapping helper.
"""

from __future__ import annotations

from typing import Any, Dict


# ---------------------------------------------------------------------------
# Utility: format_map that ignores missing keys
# ---------------------------------------------------------------------------
class _IgnoreMissing(dict):
    def __missing__(self, key: str) -> str:  # type: ignore[override]
        return f"{{{key}}}"


def render(template: str, **kwargs: Any) -> str:
    """Render a template, leaving unresolved placeholders as-is."""
    return template.format_map(_IgnoreMissing(kwargs))


# ---------------------------------------------------------------------------
# Pinned system rules  (entry 0 of every node's history)
# ---------------------------------------------------------------------------
SYSTEM_RULES = """\
You are a ReCAP planning agent (arXiv:2510.23822).
Your job is to decompose tasks and execute them step by step.

Rules:
1. Always respond with a JSON object inside a ```json``` fenced block.
2. The JSON must have keys "think" (free-text reasoning) and "subtasks" (list).
3. Each subtask: {"id": str, "desc": str, "primitive": bool, "action": str (if primitive)}.
4. Primitive subtasks are direct environment actions; non-primitive ones are decomposed further.
5. Keep subtask lists small (3-7 items). Depth limit is 8.
6. If a previous action failed, reason about the failure in "think" before replanning.
"""

# ---------------------------------------------------------------------------
# Periodic rule reminder  (§A — re-inserted every N calls)
# ---------------------------------------------------------------------------
PERIODIC_RULE_REMINDER = """\
[REMINDER] Always respond with a ```json``` fenced block containing
{"think": "...", "subtasks": [...]}.  Primitive subtasks need an "action" key.
"""

# ---------------------------------------------------------------------------
# D.1.1  Initial decomposition
# ---------------------------------------------------------------------------
INITIAL_DECOMP = """\
You are starting a new task.

Goal: {goal}

Decompose this goal into a plan. For each subtask, decide if it is
primitive (can be executed directly in the environment) or non-primitive
(needs further decomposition).

Respond with a JSON plan following the schema in SYSTEM_RULES.
"""

# ---------------------------------------------------------------------------
# D.1.2  Recursive downward (re-inject parent task + parent state window)
# ---------------------------------------------------------------------------
RECURSIVE_DOWNWARD = """\
You are decomposing a sub-task.

Parent task: {parent_T}

Parent context (recent state):
{parent_S_window}

Current sub-task: {subtask_T}

Decompose this sub-task into a plan. Use the parent context to avoid
repeating steps already done. Respond with a JSON plan.
"""

# ---------------------------------------------------------------------------
# D.1.3  Leaf backtrack (primitive action failed; replan within this node)
# ---------------------------------------------------------------------------
LEAF_BACKTRACK = """\
A primitive action failed. You must replan the remaining steps.

Failed action: {failed_action}
Failure observation: {failure_obs}

Task: {task_T}

Current state so far:
{state_summary}

Produce a revised plan that works around this failure. Respond with a JSON plan.
"""

# ---------------------------------------------------------------------------
# D.1.4  Non-leaf completion (child finished; update parent or summarise)
# ---------------------------------------------------------------------------
NONLEAF_COMPLETION = """\
A child sub-task has completed.

Parent task: {task_T}

Child sub-task: {child_id}
Child result: {child_result}

{failure_context}
Remaining sub-tasks (if any) and the overall parent plan may need updating.
Respond with a JSON plan for the remaining work, or an empty subtasks list
if the parent task is now complete.
"""

# ---------------------------------------------------------------------------
# D.1.5  Leaf failure (primitive exhausted retries; propagate failure upward)
# ---------------------------------------------------------------------------
LEAF_FAILURE = """\
A primitive action has failed after all retries.

Task: {task_T}
Failed action: {failed_action}
Last observation: {failure_obs}

Summarise what was accomplished and why this sub-task could not complete.
This summary will be returned to the parent node.

Respond with a JSON object:
```json
{"think": "explanation of what failed and why", "subtasks": []}
```
"""

# ---------------------------------------------------------------------------
# Render helpers for each template
# ---------------------------------------------------------------------------

def render_initial_decomp(*, goal: str) -> str:
    return render(INITIAL_DECOMP, goal=goal)


def render_recursive_downward(
    *,
    parent_T: str,
    parent_S_window: str,
    subtask_T: str,
) -> str:
    return render(
        RECURSIVE_DOWNWARD,
        parent_T=parent_T,
        parent_S_window=parent_S_window,
        subtask_T=subtask_T,
    )


def render_leaf_backtrack(
    *,
    failed_action: str,
    failure_obs: str,
    task_T: str,
    state_summary: str,
) -> str:
    return render(
        LEAF_BACKTRACK,
        failed_action=failed_action,
        failure_obs=failure_obs,
        task_T=task_T,
        state_summary=state_summary,
    )


def render_nonleaf_completion(
    *,
    task_T: str,
    child_id: str,
    child_result: str,
    failure_context: str = "",
) -> str:
    return render(
        NONLEAF_COMPLETION,
        task_T=task_T,
        child_id=child_id,
        child_result=child_result,
        failure_context=failure_context,
    )


def render_leaf_failure(
    *,
    task_T: str,
    failed_action: str,
    failure_obs: str,
) -> str:
    return render(
        LEAF_FAILURE,
        task_T=task_T,
        failed_action=failed_action,
        failure_obs=failure_obs,
    )


def state_to_summary(S: list) -> str:
    """Flatten a node's S list to a readable string for prompt injection."""
    lines = []
    for entry in S:
        if entry[0] == "act":
            _, st, obs = entry
            action_str = st.get("action", str(st)) if isinstance(st, dict) else str(st)
            lines.append(f"  - action: {action_str} => {obs.text}")
        elif entry[0] == "child_return":
            _, child_id, summary = entry
            lines.append(f"  - child '{child_id}' returned: {summary}")
        elif entry[0] == "note":
            lines.append(f"  - note: {entry[1]}")
    return "\n".join(lines) if lines else "(no state yet)"
