---
title: open-notebook (compose overlay)
section: docs
tags: [compose, docker, add-on]
aliases: [open-notebook, open-notebook.yml]
source: compose/open-notebook.yml
generated: 2026-04-15T00:51:55Z
---

# open-notebook (compose overlay)

**Source:** `compose/open-notebook.yml`

─────────────────────────────────────────────────────────────────
Open Notebook — self-hosted NotebookLM alternative
https://github.com/lfnovo/open-notebook

Bring up:   docker compose -f compose/open-notebook.yml up -d
Tear down:  docker compose -f compose/open-notebook.yml down

UI:  http://127.0.0.1:${OPEN_NOTEBOOK_PORT:-8502}
API: http://127.0.0.1:${OPEN_NOTEBOOK_API_PORT:-5055}/docs

Bound to 127.0.0.1 on purpose — "open" means open-source, not
public. Change the bind prefix only behind an auth proxy.

Host LM Studio / Ollama are reachable at host.docker.internal.
Configure providers in the UI under Settings → API Keys after
first start-up; credentials are encrypted with the key below.
─────────────────────────────────────────────────────────────────

## Service

- **name:** `open-notebook-db`
- **image:** `surrealdb/surrealdb:v2`
- **ports:**
    - `./open-notebook/surreal:/mydata`

## How to start

```bash
docker compose -f compose/open-notebook.yml up -d
```
