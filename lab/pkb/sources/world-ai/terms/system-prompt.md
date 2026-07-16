---
title: "System Prompt"
tags: [world-ai, inference]
aliases: [system-prompt, system message]
---

A high-priority instruction block that sets a model's role, rules, and behavior before the user's turn.

The system prompt is a special leading message that establishes the assistant's persona, constraints, tools, and policies for the whole conversation. Models are trained to weight it above ordinary user turns, making it the primary lever for steering behavior without fine-tuning — and a key surface for both control and prompt-injection risk.

**Example:** A system prompt of 'You are a terse SQL assistant; never explain unless asked' shapes every later reply.

## Related

- [[prompt]]
- [[prompt-caching]]
- [[alignment]]
- [[tool-use]]

Source: authored
