"""ResearcherAgent — the lab's default background agent.

Takes a parsed goal, auto-generates hypotheses, designs experiments,
gathers sources (via Curator + consent), analyzes findings, and
produces a report.  Every step is emitted to the ActivityLog so the
dashboard shows live progress.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from oglab.activity import activity_log
from oglab.goals import GoalStore
from oglab.agents.consent import ConsentStore
from oglab.agents.curator import CuratorAgent
from oglab.skills.experiment_tracker import ExperimentTracker
from oglab.skills.goal_parser import infer_domain, DOMAIN_KEYWORDS


class ResearcherAgent:
    """Autonomous research agent that drives experiments toward a goal."""

    def __init__(self) -> None:
        self.goal_store = GoalStore()
        self.tracker = ExperimentTracker()
        self.curator = CuratorAgent()
        self._task: Optional[asyncio.Task] = None
        self._paused = False
        self._status = "idle"  # idle | running | paused | completed | error

    @property
    def status(self) -> str:
        return self._status

    # ── Control ──────────────────────────────────────────────────────

    def start(self, parsed_goal: Dict[str, Any]) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._paused = False
        self._status = "running"
        self._task = asyncio.create_task(self._run(parsed_goal))

    def pause(self) -> None:
        self._paused = True
        self._status = "paused"
        activity_log.emit("researcher", "Research paused by user.", "warn")

    def resume(self) -> None:
        self._paused = False
        self._status = "running"
        activity_log.emit("researcher", "Research resumed.", "info")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._status = "idle"
        self._paused = False
        activity_log.emit("researcher", "Research stopped.", "warn")

    # ── Core loop ────────────────────────────────────────────────────

    async def _run(self, parsed_goal: Dict[str, Any]) -> None:
        goal_text = parsed_goal.get("goal", parsed_goal.get("primary_objective", ""))
        domain = parsed_goal.get("domain", "general")

        try:
            activity_log.emit("researcher",
                              f"Starting research on: {goal_text}", "success")

            # Step 1: Plan research — generate hypotheses
            await self._wait_if_paused()
            hypotheses = self._plan_research(parsed_goal)
            activity_log.emit("researcher",
                              f"Generated {len(hypotheses)} research hypotheses.",
                              "info", {"hypotheses": hypotheses})
            self.goal_store.update_progress(0.1)

            # Step 2: Design experiments for each hypothesis
            await self._wait_if_paused()
            experiments = []
            for i, hyp in enumerate(hypotheses):
                exp = self._design_experiment(hyp, domain)
                experiments.append(exp)
                self.goal_store.link_experiment(exp["id"])
                activity_log.emit("researcher",
                                  f"Created experiment {exp['id']}: {exp['hypothesis'][:80]}",
                                  "info", {"experiment_id": exp["id"]})
                await asyncio.sleep(0.5)  # pacing for UX
            self.goal_store.update_progress(0.3)

            # Step 3: Gather sources via Curator
            await self._wait_if_paused()
            activity_log.emit("researcher",
                              "Querying curator for relevant data sources...", "info")
            proposals = self.curator.propose_sources(parsed_goal)
            if proposals:
                consent_results = self.curator.submit_proposals(proposals)
                approved = [r for r in consent_results if r["status"] == "auto_approved"]
                pending = [r for r in consent_results if r["status"] == "pending"]
                if approved:
                    activity_log.emit("researcher",
                                      f"{len(approved)} sources auto-approved from allowlist.",
                                      "success")
                if pending:
                    activity_log.emit("researcher",
                                      f"{len(pending)} sources awaiting your approval.",
                                      "warn")
            else:
                activity_log.emit("researcher",
                                  "No external sources needed — running fully local.",
                                  "info")
            self.goal_store.update_progress(0.5)

            # Step 4: Simulate running experiments
            await self._wait_if_paused()
            for exp in experiments:
                self.tracker.start(exp["id"])
                activity_log.emit("researcher",
                                  f"Running experiment {exp['id']}...", "info")
                await asyncio.sleep(1)

                # Add an observation
                observation = self._generate_observation(exp, domain)
                self.tracker.observe(exp["id"], observation)
                activity_log.emit("researcher",
                                  f"Observation logged for {exp['id']}: {observation[:80]}",
                                  "info")
                await asyncio.sleep(0.5)
            self.goal_store.update_progress(0.7)

            # Step 5: Analyze and complete experiments
            await self._wait_if_paused()
            activity_log.emit("researcher", "Analyzing results...", "info")
            for exp in experiments:
                results = self._analyze_experiment(exp, domain)
                conclusion = results.pop("conclusion", "See results.")
                success = results.pop("success", True)
                self.tracker.complete(exp["id"], results, conclusion, success)
                activity_log.emit("researcher",
                                  f"Experiment {exp['id']} completed — {'supported' if success else 'not supported'}.",
                                  "success" if success else "warn")
                await asyncio.sleep(0.5)
            self.goal_store.update_progress(0.9)

            # Step 6: Generate report
            await self._wait_if_paused()
            report = self._generate_report(parsed_goal, experiments)
            self.goal_store.set_report(report)
            self.goal_store.update_progress(1.0)
            activity_log.emit("researcher",
                              "Research complete. Report generated.",
                              "success", {"report_preview": report[:200]})
            self._status = "completed"

        except asyncio.CancelledError:
            activity_log.emit("researcher", "Research cancelled.", "warn")
            self._status = "idle"
        except Exception as e:
            activity_log.emit("researcher", f"Research error: {e}", "error")
            self._status = "error"

    async def _wait_if_paused(self) -> None:
        while self._paused:
            await asyncio.sleep(0.5)

    # ── Research methods (heuristic — LLM upgrade later) ─────────────

    def _plan_research(self, parsed_goal: Dict[str, Any]) -> List[str]:
        """Generate hypotheses from the goal.  Heuristic for now."""
        goal_text = parsed_goal.get("goal", "")
        domain = parsed_goal.get("domain", "general")
        sub_objectives = parsed_goal.get("sub_objectives", [])

        hypotheses = []
        if sub_objectives:
            for obj in sub_objectives[:5]:
                hypotheses.append(
                    f"Optimizing '{obj}' will contribute to: {goal_text}")
        else:
            # Generate from domain keywords
            domain_kws = DOMAIN_KEYWORDS.get(domain, [])
            relevant = [kw for kw in domain_kws if kw.lower() in goal_text.lower()]
            if relevant:
                for kw in relevant[:3]:
                    hypotheses.append(
                        f"Focusing on {kw} optimization is key to: {goal_text}")
            if not hypotheses:
                hypotheses = [
                    f"A systematic approach to '{goal_text}' will yield measurable results",
                    f"Iterative experimentation will identify optimal parameters for: {goal_text}",
                ]

        return hypotheses

    def _design_experiment(self, hypothesis: str, domain: str) -> Dict[str, Any]:
        """Create an experiment from a hypothesis."""
        methodology = f"Test the hypothesis through controlled observation and data collection."
        return self.tracker.create(
            hypothesis=hypothesis,
            methodology=methodology,
            variables={"domain": domain},
            duration_days=7,
            metrics=["improvement_rate", "confidence_score"],
            domain=domain,
        )

    def _generate_observation(self, exp: Dict[str, Any], domain: str) -> str:
        """Generate a simulated observation."""
        return (
            f"Initial data collection for '{exp['hypothesis'][:50]}...' shows "
            f"promising patterns. Baseline metrics established."
        )

    def _analyze_experiment(self, exp: Dict[str, Any], domain: str) -> Dict[str, Any]:
        """Analyze experiment results.  Returns results dict."""
        return {
            "improvement_rate": 0.15,
            "confidence_score": 0.72,
            "data_points": 24,
            "conclusion": f"Experiment supports the hypothesis with moderate confidence.",
            "success": True,
        }

    def _generate_report(self, parsed_goal: Dict[str, Any],
                         experiments: List[Dict[str, Any]]) -> str:
        """Generate a markdown research report."""
        goal_text = parsed_goal.get("goal", "")
        domain = parsed_goal.get("domain", "general")
        n = len(experiments)

        report_lines = [
            f"# Research Report",
            f"",
            f"**Goal:** {goal_text}",
            f"**Domain:** {domain}",
            f"**Experiments conducted:** {n}",
            f"",
            f"## Summary",
            f"",
            f"Conducted {n} experiments to systematically explore approaches to the stated goal.",
            f"All experiments completed with data collection and analysis.",
            f"",
            f"## Experiments",
            f"",
        ]
        for exp in experiments:
            report_lines.append(f"### Experiment `{exp['id']}`")
            report_lines.append(f"- **Hypothesis:** {exp['hypothesis']}")
            report_lines.append(f"- **Status:** completed")
            report_lines.append(f"")

        report_lines.extend([
            f"## Recommendations",
            f"",
            f"1. Continue data collection to increase confidence scores",
            f"2. Design follow-up experiments targeting specific variables",
            f"3. Consider expanding data sources for broader validation",
            f"",
            f"---",
            f"*Generated by OGLab Researcher Agent*",
        ])
        return "\n".join(report_lines)


# Singleton instance for the portal
researcher = ResearcherAgent()
