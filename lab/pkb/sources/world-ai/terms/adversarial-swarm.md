---
title: "Adversarial Swarm"
tags: [world-ai, qukaizen]
aliases: [adversarial-swarm, swarm]
---

A loop of agents (interrogate, challenge, evaluate, correct) that hardens a model until it stops breaking.

The Adversarial Swarm Reactor pits Interrogator, Adversary, Evaluator, and Corrector agents (plus data-collection agents) against the student in cycles, systematically hunting and eliminating hallucination pathways. The model graduates not by passing a fixed test but when the swarm can no longer break it.

**Example:** The swarm keeps inventing harder kernel-bug traps until the student answers them all, then it graduates.

## Related

- [[convergence-graduation]]
- [[super-skill]]
- [[nucleus-seal]]

Source: QuKaiZen NUCLEUS_AGENT_PROTOCOL
