---
title: "Process Reward Model"
tags: [world-ai, rl-alignment]
aliases: [process-reward-model, PRM, step reward model]
---

A reward model that scores each step of a reasoning chain, not just the final answer.

A process reward model (PRM) evaluates the intermediate steps of a solution, rewarding correct reasoning along the way, in contrast to an outcome reward model that judges only the end result. Step-level signal improves reasoning training and verification.

**Example:** A PRM flags the exact line where a math proof goes wrong, rather than only marking the answer wrong.

## Related

- [[reward-model]]
- [[verifier]]
- [[reasoning]]
- [[chain-of-thought]]
- [[grpo]]

Source: authored
