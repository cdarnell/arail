---
title: consent module
section: docs
tags: [python, module]
aliases: [consent, consent.py]
source: src/oglab/agents/consent.py
generated: 2026-04-15T11:48:11Z
---

# consent module

**Source:** `src/oglab/agents/consent.py`

Agent consent / network allowlist system.

Agents have ZERO network access by default.  When an agent wants to
fetch something from the internet it must:

1. Submit a ``ConsentRequest`` (url + reason).
2. Wait for the user to approve or deny via the portal UI.
3. If approved, the fetch proceeds and the response is cached locally.
4. If the user checks "remember domain", that domain is added to the
   persistent allowlist so future requests skip the prompt.

## Classes

### `ConsentStore`

Manages pending requests and the domain allowlist.

**Methods:**

- `__init__(self, data_dir)`
- `list_allowed(self)`
- `is_allowed(self, url)`
- `add_domain(self, url)`
- `remove_domain(self, domain)`
- `request_access(self, url, reason, agent)`
    - Agent calls this to ask for network access.
- `list_pending(self)`
- `approve(self, request_id)`
- `deny(self, request_id)`
