---
title: "Watcher"
tags: [world-ai, architecture]
aliases: [watcher]
---

A process that observes for changes and triggers reconciliation when state moves.

A watcher monitors a source — files, a repo, an event stream — and fires the reconcile loop whenever it detects a change, so the system converges toward desired state without manual prompting. It is the trigger half of a declarative control loop: watch, then reconcile.

**Example:** A watcher on the docs repo re-runs the build-and-publish pipeline the moment a markdown file changes.

## Related

- [[reconcile]]
- [[drift]]
- [[desired-state]]
- [[automation]]

Source: authored
