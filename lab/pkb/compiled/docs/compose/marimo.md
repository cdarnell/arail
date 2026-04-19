---
title: marimo (compose overlay)
section: docs
tags: [compose, docker, add-on]
aliases: [marimo, marimo.yml]
source: compose/marimo.yml
generated: 2026-04-18T17:11:40Z
---

# marimo (compose overlay)

**Source:** `compose/marimo.yml`

─────────────────────────────────────────────────────────────────
Marimo — reactive, AI-native Python notebooks
https://marimo.io

Bring up:   docker compose -f compose/marimo.yml up -d
Tear down:  docker compose -f compose/marimo.yml down

UI: http://127.0.0.1:${MARIMO_PORT:-2718}

Notebooks live on the host at lab/notebooks/ — edit from Marimo
or your IDE, they're plain .py files. Bound to 127.0.0.1 because
a notebook server with kernel access is effectively a shell.

Host LM Studio / Ollama are reachable at host.docker.internal.
─────────────────────────────────────────────────────────────────

## Service

- **name:** `marimo`
- **image:** `python:3.11-slim`
- **ports:**
    - `127.0.0.1:${MARIMO_PORT:-2718}:2718`
    - `host.docker.internal:host-gateway`
    - `OGLAB_PASSWORD=${OGLAB_PASSWORD:-oglab}`
    - `../lab/notebooks:/notebooks`
    - `marimo-pip-cache:/root/.cache/pip`

## How to start

```bash
docker compose -f compose/marimo.yml up -d
```
