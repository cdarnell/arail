---
title: backends module
section: docs
tags: [python, module]
aliases: [backends, backends.py]
source: src/oglab/router/backends.py
generated: 2026-04-19T13:28:23Z
---

# backends module

**Source:** `src/oglab/router/backends.py`

Backend implementations for every supported accelerator / cloud service.

## Classes

### `ModelResponse`

### `BaseBackend`

**Methods:**

- `complete(self, prompt, max_tokens, temperature, top_p)`
    - Run one completion.
- `health_check(self)`

### `MLXBackend`

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature, top_p)`
- `health_check(self)`

### `CUDABackend`

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature, top_p)`
- `health_check(self)`

### `CPUBackend`

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature, top_p)`
- `health_check(self)`

### `HuggingFaceBackend`

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature, top_p)`
- `health_check(self)`

### `OpenRouterBackend`

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature, top_p)`
- `health_check(self)`

### `ClaudeBackend`

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature, top_p)`
- `health_check(self)`

### `OpenAICompatBackend`

Talks to any server that exposes the OpenAI /v1/chat/completions
endpoint on localhost.  Works with LM Studio, Ollama, DeployLM, etc.

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature, top_p)`
- `health_check(self)`

### `AeroLLMBackend`

Run massive models (100B-405B) from disk via AeroLLM.

Default: Qwen3-235B-A22B — a 235B MoE model (22B active per token).
Multi-threaded layer streaming with prefetch: overlaps disk I/O and
compute so concurrent prompts share layer passes instead of
serializing on bandwidth. Developed at github.com/cdarnell/aerollm.

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature, top_p)`
- `health_check(self)`
