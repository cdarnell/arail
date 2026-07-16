---
title: "Reconciliation"
tags: [world-ai, architecture]
aliases: [reconcile, desired-state reconciliation]
---

Continuously closing the gap between the team you declared and the team that's running.

Borrowed from infrastructure (Kubernetes-style control loops), reconciliation compares desired state to observed state and converges them; a watcher fixes drift forever after. PaperAgents applies it to agent teams.

**Example:** Declare four agents; the watcher notices one died and restarts it to match the manifest.

## Related

- [[desired-state]]
- [[drift]]
- [[watcher]]

Source: QuKaiZen AI Dictionary
