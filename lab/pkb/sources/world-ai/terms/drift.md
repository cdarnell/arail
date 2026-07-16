---
title: "Drift"
tags: [world-ai, architecture]
aliases: [drift, configuration drift]
---

When the real state of a system diverges from its declared desired state over time.

Drift is the gap that opens when a running system changes out from under its specification — manual edits, partial failures, or external mutation leave reality and the declared desired state out of sync. Reconciliation loops detect drift and converge the system back to desired state; documentation-as-code treats drift in docs the same way.

**Example:** Someone hand-edits a deployed config; the next reconcile pass detects the drift and restores the declared version.

## Related

- [[desired-state]]
- [[reconcile]]
- [[idempotent]]
- [[watcher]]

Source: authored
