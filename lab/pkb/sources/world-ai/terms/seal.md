---
title: "Seal"
tags: [world-ai, qukaizen]
aliases: [seal, Nucleus Seal, cryptographic seal]
---

A cryptographic signature certifying a model's provenance — what it was distilled from and that it is untampered.

A seal is a cryptographic signature (QuKaiZen uses Ed25519) bound to a finished model, certifying its provenance: which teacher and corpus it came from, which certification gates it passed, and that its weights have not changed since. Anyone can verify the seal offline, so an owned model carries proof of exactly what it is — the Nucleus Seal.

**Example:** Before trusting a distilled 3B model in production you verify its Ed25519 seal; if a single weight changed, verification fails.

## Related

- [[nucleus-seal]]
- [[ssdp]]
- [[ed25519]]

Source: QuKaiZen NUCLEUS_AGENT_PROTOCOL
