---
title: lab_brain module
section: docs
tags: [python, module]
aliases: [lab_brain, lab_brain.py]
source: src/oglab/lab_brain.py
generated: 2026-04-15T17:33:38Z
---

# lab_brain module

**Source:** `src/oglab/lab_brain.py`

OGLab lab_brain — system prompt builder for lab-aware LLM calls.

Every LLM call the lab makes — chat, researcher, curator — should start
from a system prompt that tells the model **what OGLab is, what it can
do, and what state it's in right now**. Without this, the model is a
generic assistant that doesn't know its own environment. With this,
it can answer questions like:

    "How do I run a new experiment?"     → knows about ./oglab CLI
    "Where does the agent write reports?" → knows lab/pkb/agents/
    "Is the heavy window active?"         → checks the scheduler
    "How do I halt the researcher?"       → knows the Halt button

The prompt is composed from three layers:

1. **Identity** — brand + intent. Who is the lab? Who is it for?
2. **Capabilities** — a compact reference card of the lab's features
   (router, scheduler, PKB, wiki, curator, researcher, CLI, portal).
3. **Current state** — live snapshot: current goal, backend, window,
   halt flag, recent agent activity.

All three layers are optional so callers can keep the token budget
small when they need to (`build_system_prompt(include_state=False)`).

## Functions

### `build_system_prompt()`

Compose the full lab-aware system prompt.

Args:
    include_capabilities: Include the static capabilities reference
        (~600 tokens). Turn off if you're in a tight budget.
    include_state: Include the live state snapshot (~150 tokens).
        Turn off when calling from contexts that don't need it.
    extra_context: Extra guidance appended at the end — useful for
        per-call instructions like "respond in 2 sentences" or
        "output valid JSON only".

### `build_chat_prompt(user_message, conversation)`

Format a full chat request as a single prompt string.

The router's `complete()` takes a single prompt rather than OpenAI
chat-completions messages, so we render the conversation into
plain text with `User:` / `Assistant:` prefixes and append the
new user message.

Args:
    user_message: The user's current input.
    conversation: Prior turns as
        ``[{"role": "user"|"assistant", "content": "..."}]``.
