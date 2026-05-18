"""RecapAgent — Algorithm 1 implementation (paper arXiv:2510.23822).

Implements recursive plan-ahead decomposition with:
  - parent re-injection on recursive descent (§2.2 / D.1.2)
  - leaf backtrack on primitive failure (D.1.3)
  - leaf failure propagation on retry exhaustion (D.1.5)
  - non-leaf replan on child failure (D.1.4)
  - sliding-window K=64 memory (§2.4)
  - hard caps: MAX_DEPTH=8, LEAF_RETRY_CAP=2, NONLEAF_RETRY_CAP=2
  - step budget (DEFAULT_STEP_BUDGET=120)
  - cost ceiling (RECAP_COST_CEILING_USD, default $5)
  - periodic rule reminder every REMINDER_EVERY=10 LLM calls (§A)
"""

from __future__ import annotations

import enum
import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from arail.agents.recap.environment import Action, Environment, Observation
from arail.agents.recap.prompts import (
    SYSTEM_RULES,
    render_initial_decomp,
    render_leaf_backtrack,
    render_leaf_failure,
    render_nonleaf_completion,
    render_recursive_downward,
    state_to_summary,
    PERIODIC_RULE_REMINDER,
)
from arail.agents.recap.schema import SchemaError, ThinkSubtasks, parse_think_subtasks
from arail.agents.recap.state import ContextNode, ContextTree

if TYPE_CHECKING:
    from arail.agents.recap.router_adapter import RouterAdapter

logger = logging.getLogger(__name__)


class _CostCeilingError(Exception):
    """Internal sentinel raised by _llm_call when cost ceiling is breached."""
    def __init__(self, result: "NodeResult") -> None:
        super().__init__(result.summary)
        self.result = result


# ---------------------------------------------------------------------------
# Constants (overridable via env vars for testing)
# ---------------------------------------------------------------------------
MAX_DEPTH: int = int(os.getenv("RECAP_MAX_DEPTH", "8"))
LEAF_RETRY_CAP: int = int(os.getenv("RECAP_LEAF_RETRY_CAP", "2"))
NONLEAF_RETRY_CAP: int = int(os.getenv("RECAP_NONLEAF_RETRY_CAP", "2"))
DEFAULT_STEP_BUDGET: int = int(os.getenv("RECAP_STEP_BUDGET", "120"))
REMINDER_EVERY: int = int(os.getenv("RECAP_REMINDER_EVERY", "10"))
RECAP_COST_CEILING_USD: float = float(
    os.getenv("RECAP_COST_CEILING_USD", "5.0")
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
class ResultKind(enum.Enum):
    OK = "ok"
    FAILED = "failed"
    BUDGET_EXCEEDED = "budget_exceeded"
    COST_EXCEEDED = "cost_exceeded"
    DEPTH_EXCEEDED = "depth_exceeded"


@dataclass
class NodeResult:
    kind: ResultKind
    summary: str = ""
    node: Optional[ContextNode] = None

    @property
    def ok(self) -> bool:
        return self.kind == ResultKind.OK

    @property
    def failed(self) -> bool:
        return self.kind != ResultKind.OK


@dataclass
class RunResult:
    kind: ResultKind
    summary: str = ""
    tree: Optional[ContextTree] = None
    steps_taken: int = 0
    llm_calls: int = 0


# ---------------------------------------------------------------------------
# RecapAgent
# ---------------------------------------------------------------------------
class RecapAgent:
    """Runs Algorithm 1 on a goal string using ``env`` and ``adapter``.

    Args:
        env:      An ``Environment`` implementation.
        adapter:  A ``RouterAdapter`` wrapping a ``ModelRouter``.
        step_budget:  Maximum number of primitive env steps.
        max_depth:    Hard recursion-depth cap.
    """

    def __init__(
        self,
        env: Environment,
        adapter: "RouterAdapter",
        *,
        step_budget: int = DEFAULT_STEP_BUDGET,
        max_depth: int = MAX_DEPTH,
    ) -> None:
        self.env = env
        self.adapter = adapter
        self.step_budget = step_budget
        self.max_depth = max_depth
        self._steps: int = 0
        self._llm_calls: int = 0

    # ------------------------------------------------------------------
    def run(self, goal_text: str) -> RunResult:
        """Entry point — implements Algorithm 1 §2.1."""
        self._steps = 0
        self._llm_calls = 0

        obs = self.env.reset()
        logger.debug("env reset: %s", obs.text)

        root = ContextNode(T=goal_text, S=[], parent=None, depth=0)
        tree = ContextTree(root)

        # Step 1 — initial decomposition (D.1.1)
        system_msg = {"role": "system", "content": SYSTEM_RULES}
        user_msg = {
            "role": "user",
            "content": render_initial_decomp(goal=goal_text),
        }
        root.history = [system_msg, user_msg]

        try:
            resp_text = self._llm_call(root.history, depth=0)
        except _CostCeilingError as exc:
            return RunResult(
                kind=ResultKind.COST_EXCEEDED,
                summary=exc.result.summary,
                tree=tree,
                steps_taken=self._steps,
                llm_calls=self._llm_calls,
            )
        except Exception as exc:
            return RunResult(
                kind=ResultKind.FAILED,
                summary=f"Initial decomposition failed: {exc}",
                tree=tree,
                steps_taken=self._steps,
                llm_calls=self._llm_calls,
            )

        root.history.append({"role": "assistant", "content": resp_text})

        try:
            root.plan = self._parse(resp_text, root, context="initial_decomp")
        except SchemaError as exc:
            return RunResult(
                kind=ResultKind.FAILED,
                summary=f"Schema error on initial decomp: {exc}",
                tree=tree,
                steps_taken=self._steps,
                llm_calls=self._llm_calls,
            )

        try:
            result = self._descend(root, tree)
        except _CostCeilingError as exc:
            return RunResult(
                kind=ResultKind.COST_EXCEEDED,
                summary=exc.result.summary,
                tree=tree,
                steps_taken=self._steps,
                llm_calls=self._llm_calls,
            )
        return RunResult(
            kind=result.kind,
            summary=result.summary,
            tree=tree,
            steps_taken=self._steps,
            llm_calls=self._llm_calls,
        )

    # ------------------------------------------------------------------
    def _descend(self, node: ContextNode, tree: ContextTree) -> NodeResult:
        """Recursive descent — one node's subtask list."""
        if node.plan is None or not node.plan.subtasks:
            # Empty plan = done for this node
            return NodeResult(kind=ResultKind.OK, summary="(empty plan)", node=node)

        subtasks = list(node.plan.subtasks)

        for subtask in subtasks:
            # Budget check before each env step or recursive call
            if self._steps >= self.step_budget:
                return NodeResult(
                    kind=ResultKind.BUDGET_EXCEEDED,
                    summary=f"Step budget {self.step_budget} exhausted",
                    node=node,
                )

            # Cost ceiling check (also done in _llm_call; belt-and-suspenders here)
            if self._llm_calls > 0 and self._llm_calls % REMINDER_EVERY == 0:
                cost_check = self._check_cost_ceiling()
                if cost_check is not None:
                    return cost_check

            # Depth cap: force primitive if too deep
            if not subtask.primitive and node.depth >= self.max_depth:
                logger.warning(
                    "MAX_DEPTH %d reached at node depth %d; forcing primitive",
                    self.max_depth, node.depth,
                )
                subtask = type(subtask)(
                    id=subtask.id,
                    desc=subtask.desc,
                    primitive=True,
                    action=subtask.action or f"FORCED({subtask.desc[:40]})",
                )

            if subtask.primitive:
                result = self._execute_primitive(subtask, node, tree)
                if result is not None:
                    return result
            else:
                # Non-primitive: recurse
                result = self._execute_nonprimitive(subtask, node, tree)
                if result is not None and result.failed:
                    # Non-leaf replan (D.1.4)
                    if node.retries < NONLEAF_RETRY_CAP:
                        replan_result = self._nonleaf_replan(node, tree, subtask, result)
                        if replan_result is not None:
                            return replan_result
                        # replan succeeded — continue outer loop with updated plan
                        subtasks = list(node.plan.subtasks)
                        continue
                    else:
                        return NodeResult(
                            kind=ResultKind.FAILED,
                            summary=(
                                f"Non-leaf '{subtask.id}' failed after "
                                f"{NONLEAF_RETRY_CAP} replans: {result.summary}"
                            ),
                            node=node,
                        )

        # All subtasks completed — emit non-leaf-completion summary (D.1.4)
        summary_resp = self._nonleaf_completion_summary(node)
        return NodeResult(kind=ResultKind.OK, summary=summary_resp, node=node)

    # ------------------------------------------------------------------
    def _execute_primitive(
        self,
        subtask: Any,
        node: ContextNode,
        tree: ContextTree,
    ) -> Optional[NodeResult]:
        """Execute a primitive subtask. Returns a NodeResult only on terminal failure."""
        action = Action.from_subtask(subtask)
        try:
            obs = self.env.step(action)
        except Exception as exc:
            logger.warning("env.step raised: %s", exc)
            obs = Observation(
                text=str(exc), failed=True, info={"exception": type(exc).__name__}
            )
        self._steps += 1
        node.S.append(("act", subtask.to_dict(), obs))

        if obs.failed:
            if node.retries < LEAF_RETRY_CAP:
                # Leaf-backtrack (D.1.3)
                backtrack_result = self._leaf_backtrack(subtask, obs, node, tree)
                return backtrack_result
            else:
                # Leaf-failure (D.1.5)
                failure_summary = self._leaf_failure(subtask, obs, node)
                return NodeResult(
                    kind=ResultKind.FAILED,
                    summary=failure_summary,
                    node=node,
                )
        return None  # success — continue outer loop

    def _leaf_backtrack(
        self,
        subtask: Any,
        obs: Observation,
        node: ContextNode,
        tree: ContextTree,
    ) -> Optional[NodeResult]:
        """Issue D.1.3 prompt, replan node, re-descend."""
        node.retries += 1
        backtrack_content = render_leaf_backtrack(
            failed_action=subtask.action if hasattr(subtask, "action") else str(subtask),
            failure_obs=obs.text,
            task_T=node.T,
            state_summary=state_to_summary(node.S),
        )
        node.history.append({"role": "user", "content": backtrack_content})
        try:
            resp = self._llm_call(node.history, depth=node.depth)
        except _CostCeilingError:
            raise
        except Exception as exc:
            return NodeResult(
                kind=ResultKind.FAILED,
                summary=f"LLM call failed during backtrack: {exc}",
                node=node,
            )
        node.history.append({"role": "assistant", "content": resp})
        try:
            node.plan = self._parse(resp, node, context="leaf_backtrack")
        except SchemaError as exc:
            return NodeResult(
                kind=ResultKind.FAILED,
                summary=f"Schema error on backtrack: {exc}",
                node=node,
            )
        return self._descend(node, tree)

    def _leaf_failure(
        self,
        subtask: Any,
        obs: Observation,
        node: ContextNode,
    ) -> str:
        """Issue D.1.5 prompt and return the failure summary."""
        failure_content = render_leaf_failure(
            task_T=node.T,
            failed_action=subtask.action if hasattr(subtask, "action") else str(subtask),
            failure_obs=obs.text,
        )
        node.history.append({"role": "user", "content": failure_content})
        try:
            resp = self._llm_call(node.history, depth=node.depth)
            node.history.append({"role": "assistant", "content": resp})
            return resp
        except _CostCeilingError:
            raise
        except Exception as exc:
            return f"Leaf failure (LLM unavailable: {exc})"

    # ------------------------------------------------------------------
    def _execute_nonprimitive(
        self,
        subtask: Any,
        node: ContextNode,
        tree: ContextTree,
    ) -> Optional[NodeResult]:
        """Recurse into a non-primitive subtask."""
        child = ContextNode(T=subtask.desc, S=[], parent=node, depth=node.depth + 1)
        node.add_child(child)
        tree.add(child)

        # Recursive-downward (D.1.2) — re-inject parent T and windowed parent S
        # INVARIANT: parent_T and parent_S come from the node object, NOT from chat
        # history, so truncation never loses this context.
        parent_S_str = state_to_summary(node.S)
        downward_content = render_recursive_downward(
            parent_T=node.T,
            parent_S_window=parent_S_str,
            subtask_T=subtask.desc,
        )

        child_system = {"role": "system", "content": SYSTEM_RULES}
        child_user = {"role": "user", "content": downward_content}
        child.history = [child_system, child_user]

        try:
            resp = self._llm_call(child.history, depth=child.depth)
        except _CostCeilingError:
            raise
        except Exception as exc:
            return NodeResult(
                kind=ResultKind.FAILED,
                summary=f"LLM call failed for child '{subtask.id}': {exc}",
                node=child,
            )
        child.history.append({"role": "assistant", "content": resp})

        try:
            child.plan = self._parse(resp, child, context="recursive_downward")
        except SchemaError as exc:
            return NodeResult(
                kind=ResultKind.FAILED,
                summary=f"Schema error on child '{subtask.id}': {exc}",
                node=child,
            )

        child_result = self._descend(child, tree)
        # Propagate child summary to parent.S (paper §2.2)
        node.S.append(("child_return", subtask.id, child_result.summary))
        return child_result

    def _nonleaf_replan(
        self,
        node: ContextNode,
        tree: ContextTree,
        failed_subtask: Any,
        child_result: NodeResult,
    ) -> Optional[NodeResult]:
        """D.1.4 — parent replans after child failure."""
        node.retries += 1
        failure_ctx = (
            f"Child subtask '{failed_subtask.id}' failed: {child_result.summary}\n"
        )
        completion_content = render_nonleaf_completion(
            task_T=node.T,
            child_id=failed_subtask.id,
            child_result=child_result.summary,
            failure_context=failure_ctx,
        )
        node.history.append({"role": "user", "content": completion_content})
        try:
            resp = self._llm_call(node.history, depth=node.depth)
        except _CostCeilingError:
            raise
        except Exception as exc:
            return NodeResult(
                kind=ResultKind.FAILED,
                summary=f"LLM call failed during nonleaf replan: {exc}",
                node=node,
            )
        node.history.append({"role": "assistant", "content": resp})
        try:
            node.plan = self._parse(resp, node, context="nonleaf_replan")
        except SchemaError as exc:
            return NodeResult(
                kind=ResultKind.FAILED,
                summary=f"Schema error on nonleaf replan: {exc}",
                node=node,
            )
        # Empty plan after replan = success (nothing left to do)
        if not node.plan.subtasks:
            return None  # caller treats None as "replan succeeded, continue"
        return None  # descend will be re-entered by the outer loop

    def _nonleaf_completion_summary(self, node: ContextNode) -> str:
        """D.1.4 — emit a completion summary when all subtasks succeed."""
        completion_content = render_nonleaf_completion(
            task_T=node.T,
            child_id="all",
            child_result="All subtasks completed successfully.",
        )
        node.history.append({"role": "user", "content": completion_content})
        try:
            resp = self._llm_call(node.history, depth=node.depth)
            node.history.append({"role": "assistant", "content": resp})
            return resp
        except _CostCeilingError:
            raise
        except Exception as exc:
            return f"(completion summary unavailable: {exc})"

    # ------------------------------------------------------------------
    def _llm_call(self, history: List[Dict[str, Any]], *, depth: int) -> str:
        """Issue one LLM call; inject periodic rule reminder every N calls.
        Also checks the cost ceiling after incrementing the counter.
        """
        self._llm_calls += 1
        # Cost ceiling: check after every call so ceiling=0 is caught immediately.
        cost_check = self._check_cost_ceiling()
        if cost_check is not None:
            raise _CostCeilingError(cost_check)
        msgs = list(history)
        if self._llm_calls % REMINDER_EVERY == 0:
            msgs = msgs + [{"role": "system", "content": PERIODIC_RULE_REMINDER}]
        return self.adapter.chat(msgs, depth=depth)

    def _parse(
        self,
        text: str,
        node: ContextNode,
        context: str = "",
    ) -> ThinkSubtasks:
        """Parse LLM response; issue one re-prompt via adapter if needed."""
        def _retry_fn(reprompt: str) -> str:
            node.history.append({"role": "user", "content": reprompt})
            resp = self._llm_call(node.history, depth=node.depth)
            node.history.append({"role": "assistant", "content": resp})
            return resp

        return parse_think_subtasks(text, retry_fn=_retry_fn)

    # ------------------------------------------------------------------
    def _check_cost_ceiling(self) -> Optional[NodeResult]:
        """Return a COST_EXCEEDED result if billing ceiling reached, else None."""
        try:
            from arail.costs import cost_tracker
            if cost_tracker.total_billed_usage_usd >= RECAP_COST_CEILING_USD:
                msg = (
                    f"Cost ceiling ${RECAP_COST_CEILING_USD:.4f} reached "
                    f"(billed ${cost_tracker.total_billed_usage_usd:.4f})"
                )
                logger.warning("recap cost_exceeded: %s", msg)
                return NodeResult(kind=ResultKind.COST_EXCEEDED, summary=msg)
        except Exception:
            pass
        return None
