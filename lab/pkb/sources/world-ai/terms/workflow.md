---
title: "Workflow"
tags: [world-ai, architecture]
aliases: [workflow]
---

A declared sequence of steps an agent or pipeline executes.

A workflow encodes the steps — download, analyze, decide, process — as configuration rather than ad-hoc code, so it's inspectable, versionable, and reproducible. PaperAgents declares them in TOML.

**Example:** [[workflow]]: download loads → analyze margin → decide → process.

## Related

- [[automation]]
- [[orchestration]]
- [[agentic]]

Source: QuKaiZen AI Dictionary
