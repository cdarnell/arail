---
title: "Structured Output"
tags: [world-ai, inference]
aliases: [structured-output]
---

Forcing a model's response into a machine-parseable shape like JSON conforming to a schema.

Structured output makes a model return data in a defined format (typically JSON matching a schema) instead of free text, so programs can consume it reliably. It is usually enforced via constrained decoding and underpins tool use and agent pipelines.

**Example:** Requesting structured output with a schema yields {"name":...,"age":...} every time, never prose.

## Related

- [[constrained-decoding]]
- [[function-calling]]
- [[tool-use]]
- [[system-prompt]]

Source: authored
