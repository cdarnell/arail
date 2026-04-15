---
title: curator module
section: docs
tags: [python, module]
aliases: [curator, curator.py]
source: src/oglab/agents/curator.py
generated: 2026-04-15T00:51:55Z
---

# curator module

**Source:** `src/oglab/agents/curator.py`

Curator agent — finds and caches high-quality resources for a goal.

This agent:
1. Takes a parsed goal
2. Generates search queries using the local LLM
3. Requests network consent for each URL via the ConsentStore
4. Fetches approved URLs and caches content locally
5. Summarises findings using the local LLM

## Classes

### `CuratorAgent`

Finds and caches resources relevant to a user's goal.

**Methods:**

- `__init__(self, consent)`
- `propose_sources(self, parsed_goal)`
    - Given a parsed goal, return a list of proposed source fetches.
- `submit_proposals(self, proposals)`
    - Submit each proposal to the consent store.  Returns the
- `fetch_approved(self, request_id, url)`
    - Fetch a URL that has been approved.  Caches the result.
