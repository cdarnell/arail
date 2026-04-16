---
title: backends module
section: docs
tags: [python, module]
aliases: [backends, backends.py]
source: src/oglab/router/backends.py
generated: 2026-04-16T11:07:31Z
---

# backends module

**Source:** `src/oglab/router/backends.py`

Backend implementations for every supported accelerator / cloud service.

## Classes

### `ModelResponse`

### `BaseBackend`

**Methods:**

- `complete(self, prompt, max_tokens, temperature)`
- `health_check(self)`

### `MLXBackend`

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature)`
- `health_check(self)`

### `CUDABackend`

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature)`
- `health_check(self)`

### `CPUBackend`

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature)`
- `health_check(self)`

### `HuggingFaceBackend`

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature)`
- `health_check(self)`

### `OpenRouterBackend`

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature)`
- `health_check(self)`

### `ClaudeBackend`

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature)`
- `health_check(self)`

### `OpenAICompatBackend`

Talks to any server that exposes the OpenAI /v1/chat/completions
endpoint on localhost.  Works with LM Studio, Ollama, DeployLM, etc.

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature)`
- `health_check(self)`

### `AirLLMBackend`

Run massive models (100B-405B) from disk via AirLLM.

Default: Qwen3-235B-A22B — a 235B MoE model (22B active per token).
Layer-by-layer inference: only one transformer layer is loaded into
memory at a time.  Slow (seconds-per-token) but lets you run models
that would normally need 48+ GB VRAM on a 4 GB machine.

**Methods:**

- `__init__(self)`
- `complete(self, prompt, max_tokens, temperature)`
- `health_check(self)`
