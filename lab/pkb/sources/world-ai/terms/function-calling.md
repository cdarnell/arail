---
title: "Function Calling"
tags: [world-ai, architecture]
aliases: [function-calling]
---

A structured protocol for a model to request a specific tool with typed arguments.

Function calling has the model emit a structured call — a name plus JSON arguments — that your code executes and returns, for the model to use. It's the reliable mechanism beneath most tool use.

**Example:** The model returns {name:'get_rate', args:{lane:'CHI-DAL'}}; your server runs it and feeds back the price.

## Related

- [[tool-use]]
- [[agent]]
- [[mcp]]

Source: QuKaiZen AI Dictionary
