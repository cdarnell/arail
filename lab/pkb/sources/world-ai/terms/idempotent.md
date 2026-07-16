---
title: "Idempotent"
tags: [world-ai, architecture]
aliases: [idempotent, idempotency]
---

An operation that produces the same result whether applied once or many times.

An idempotent operation can be repeated safely: applying it again on an already-correct system changes nothing. It is the property that makes reconciliation loops and declarative pipelines robust — you can re-run them after a crash or partial failure without compounding side effects or corrupting state.

**Example:** 'Ensure this file contains line X' is idempotent — running it twice leaves one line X, not two.

## Related

- [[reconcile]]
- [[desired-state]]
- [[drift]]
- [[determinism]]

Source: authored
