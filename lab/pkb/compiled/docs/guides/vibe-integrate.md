---
title: Vibe Integrate
section: docs
tags: [guide]
aliases: [vibe-integrate]
source: docs/vibe-integrate.md
generated: 2026-04-25T04:17:15Z
---
# Arail — Vibe Integration Plan

How the researcher agent naturally integrates with the user's workflow.

## Philosophy

**Set a goal. Watch it happen.** The user types a natural-language goal, and the
system takes over — parsing intent, generating hypotheses, designing experiments,
collecting data, and delivering a report. No menus, no config wizards, no
mandatory steps. Just a prompt and a progress ring filling up.

## The Flow

```
User types goal
    ↓
GoalParser extracts domain, objectives, timeline
    ↓
ResearcherAgent auto-starts (no button click needed)
    ↓
Activity feed shows live progress (SSE)
Progress ring animates from 0% → 100%
    ↓
Step 1: Hypotheses generated (LLM if available, heuristic fallback)
Step 2: Experiments created and linked to goal
Step 3: Curator proposes data sources → consent system
Step 4: Experiments executed (heuristic today; LLM-driven via router)
Step 5: Analysis with improvement/confidence metrics
Step 6: Markdown report generated
    ↓
Dashboard auto-refreshes with results
User reads report, sets new goal, or refines
```

## Design Principles

1. **Zero-config start** — Works out of the box with heuristics. LLM makes it
   better but isn't required.

2. **Progressive disclosure** — First visit shows just the goal prompt and an
   empty activity feed. Complexity appears naturally as the system works.

3. **Consent-first networking** — All external access requires explicit approval.
   The first research session is fully local.

4. **Live feedback** — Every step emits to the activity feed via SSE. The user
   sees the agent thinking in real time.

5. **Graceful fallback** — No LLM? Heuristic hypotheses. No ttyd? Helpful
   "start the service" message. No model downloaded? CPU fallback with guidance.

## Plugin Integration

Plugins extend the researcher's capabilities:
- **Data source plugins** — New domains the curator can propose
- **Experiment plugins** — Real integrations (API testing, data collection, etc.)
- **Report plugins** — Custom output formats (PDF, Jupyter notebook, etc.)

Install via the Plugins page: paste a GitHub URL, one click.

## Agent Personality

The activity feed messages are the agent's voice. They should feel:
- **Concise** — One clear sentence per event
- **Informative** — What just happened, not what will happen
- **Terminal-native** — Matches the 1337 aesthetic (no emoji, no exclamation marks)
- **Progressional** — Each message shows forward movement

## Roadmap

Planned extensions, in rough priority order:

1. **Real data collection via approved URLs** — the Curator proposes sources today; the next step is fetching and caching content through the consent gate.
2. **Domain-specific experiment templates** — agriculture, ML, web dev, culinary. Each template seeds hypotheses, metrics, and a fallback heuristic.
3. **Goal history with cross-run comparison** — compare outcomes across repeated research runs on the same goal.
4. **Plugin marketplace** — a curated list of community plugins installable from the dashboard.
5. **Multi-agent collaboration** — specialist agents per domain coordinating through the shared activity log.

Contributions that tackle any of these are welcome; see [../CONTRIBUTING.md](../CONTRIBUTING.md).
