---
title: "FLOPs"
tags: [world-ai, performance]
aliases: [flops, floating-point operations]
---

Floating-point operations — the raw arithmetic count used to measure model and training cost.

FLOPs count the floating-point operations a computation requires; training cost is often quoted in total FLOPs and hardware in FLOP/s (per second). For a dense transformer, a forward pass is roughly 2 x parameters x tokens FLOPs, making it a handy back-of-envelope for cost.

**Example:** Training a model is budgeted in total FLOPs; a forward pass is about 2 x params x tokens.

## Related

- [[mfu]]
- [[scaling-laws]]
- [[parameter]]
- [[throughput]]

Source: authored
