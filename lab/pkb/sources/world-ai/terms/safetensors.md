---
title: "SafeTensors"
tags: [world-ai, formats-runtime]
aliases: [safetensors]
---

A safe, fast, zero-copy tensor file format — the modern replacement for pickle-based checkpoints.

SafeTensors stores weights in a simple, memory-mappable layout with no arbitrary code execution (unlike Python pickle, which can run malicious code on load). It loads fast via zero-copy and is now the default for sharing weights on the Hub.

**Example:** model.safetensors loads almost instantly via mmap and cannot execute hidden code, unlike a .bin/.pt pickle.

## Related

- [[gguf]]
- [[checkpoint]]

Source: authored
