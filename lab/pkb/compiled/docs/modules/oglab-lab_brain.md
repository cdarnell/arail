---
title: lab_brain module
section: docs
tags: [python, module]
aliases: [lab_brain, lab_brain.py]
source: src/oglab/lab_brain.py
generated: 2026-04-22T01:03:30Z
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

Used as a fallback for backends that only accept plain text.

Args:
    user_message: The user's current input.
    conversation: Prior turns as
        ``[{"role": "user"|"assistant", "content": "..."}]``.

### `retrieve_chat_context(user_message)`

Best-effort PKB retrieval for chat.

The built-in PKB search is lexical, so we query both the full user
message and a small set of extracted keywords, then merge and score
the hits. Failures are swallowed so chat keeps working even if the
PKB is empty or temporarily unavailable.

### `build_chat_messages(user_message, conversation)`

Build chat-style messages for chat-capable models.

### `render_chat_transcript(messages)`

Render chat messages into the plain-text transcript fallback.
