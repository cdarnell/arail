# THE NUCLEUS — School of Over Engineering AI

THE NUCLEUS is the living product: an over-engineered, highly deliberate lab that treats your Goal as the single source of truth. It runs continuously, refining itself and the tools around it so you don't have to—until you ask it to stop.

## Core principles

- Define a measurable Goal. THE NUCLEUS treats that Goal as the ground truth and instruments experiments automatically.
- Autoresearcher: unless paused, the autoresearch loop continuously researches metrics derived from the Goal and reports or acts on findings.
- Over‑engineer by default: choose the most performant tool or prove why a lighter-weight approach is acceptable.

## Out of the box flow

1. The user runs `bootstrap-nucleus.sh` and answers a few prompts to declare their Goal, environment preferences, and desired mode of operation.
2. The bootstrap sets `global.goal` and can initialize a fresh environment from scratch (redefinable anytime).
3. A background Auto-Discovery Probe starts automatically: it probes local networks, available APIs, and on-host services to enumerate integration opportunities (devices, consoles, agent endpoints).
4. The Autoresearcher begins fetching measurable signals tied to the Goal (latency, accuracy, recall, business KPIs, or custom metrics) and runs experiments until stopped.

## Modes

- Single‑function mode: run THE NUCLEUS as a one-purpose appliance (e.g., only AutoResearcher, or only a Knowledge Ingestion/Library).
- Full Lab mode: enables discovery, multi-agent workflows, transient workers, and the full SRE/observability stack.

## Learning Center & Network Discovery

The Learning Center is where agents surface findings and opportunities. One agent may discover a networked device (for example, a smart TV or console), detect an accessible API, and suggest actions like "I can power the TV on this unit—permit?" Discovery is always surfaced for user approval and scoped by policy.

## Safety & Control

- Autoresearcher and discovery agents act only within the policies you set; they surface proposals and can execute only with explicit consent or pre-configured approvals.
- You can pause or reset the Goal at any time via the bootstrap or the UI; THE NUCLEUS will recalibrate and continue from the new directive.

## Why "Over Engineering"?

Because performance, observability, and reproducibility matter. THE NUCLEUS favors robust, well-instrumented, and measurable implementations. If a simpler approach meets the requirements, documentation must explain the trade-offs.

---

Everything in this repository is pluggable and replaceable—THE NUCLEUS is opinionated about measurement and instrumentation, but flexible about implementation. If you want to dial the thermostat down from "over-engineered" to "just-right," edit your bootstrap configuration and reprovision.