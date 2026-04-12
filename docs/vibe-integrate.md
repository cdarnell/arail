# OGLab — Vibe Integration Plan

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
Step 4: Experiments run (simulated until real integrations)
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

## What's Next

- [ ] Real data collection via approved URLs (Curator fetch)
- [ ] Experiment templates per domain (agriculture, ML, web dev, etc.)
- [ ] Goal history with comparison across runs
- [ ] Plugin marketplace (curated list of community plugins)
- [ ] Multi-agent collaboration (specialist agents per domain)
