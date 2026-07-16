---
title: "AeroLLM"
tags: [world-ai, qukaizen]
aliases: [aerollm, AeroLLM]
---

QuKaiZen's inference engine that streams frontier models off disk so they run without full GPU residency.

AeroLLM is the inference layer that makes disk-streamed teachers practical — layer streaming plus speculative decoding to claw back speed. It is how QuKaiZen serves 400B+ teachers on workstations that lack the VRAM to hold them.

**Example:** Point the teacher backend at AeroLLM to stream a 405B teacher on a single box instead of an 8x H100 node.

## Related

- [[layer-streaming]]
- [[speculative-decoding]]
- [[super-skill]]
- [[vllm]]

Source: QuKaiZen NUCLEUS_AGENT_PROTOCOL
