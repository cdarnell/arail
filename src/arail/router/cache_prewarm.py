"""Pre-warm the Anthropic prompt cache so the first demo request reads cache
instead of paying the cold prefix cost.

Only does anything when **all** of the following hold; otherwise it returns a
``status: "skipped"`` summary and never touches the network:

  * ``LAB_MODE=hybrid`` (the airgapped default refuses by construction).
  * ``ANTHROPIC_API_KEY`` is set.
  * The installed ``anthropic`` SDK supports header-free block-level
    ``cache_control`` GA (>= 0.34.0 — see ``_anthropic_supports_cache`` in
    :mod:`arail.router.backends`).

Prompts are resolved with this priority:

  1. The ``prompts`` argument.
  2. The JSON file at ``lab/data/prewarm_prompts.json`` (a ``list[str]``).
  3. A built-in default list (so the lab is snappy out of the box).

The cache entry that actually matters for chat snappiness is the **system
block** (cached prefix = ``tools + system``). Any chat turn — preset or not —
that sends the same frozen system reads it. The per-prompt user message is
incidental for system caching; we mostly send it so a curious operator can
list real demo prompts in the JSON file and see them in the activity log.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional


_log = logging.getLogger("arail.router.cache_prewarm")


_DEFAULT_PROMPTS: list[str] = [
    "What is this lab and what can it do?",
    "How do I kick off a research run?",
    "Walk me through the five surfaces.",
]


def _load_prompts(provided: Optional[list[str]] = None) -> list[str]:
    """Resolve the prompt list from arg > config file > built-in defaults."""
    if provided:
        cleaned = [p for p in provided if isinstance(p, str) and p.strip()]
        if cleaned:
            return cleaned
    cfg = Path("lab/data/prewarm_prompts.json")
    if cfg.is_file():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            if isinstance(data, list):
                cleaned = [p for p in data if isinstance(p, str) and p.strip()]
                if cleaned:
                    return cleaned
        except Exception as e:                                    # noqa: BLE001
            _log.warning("failed to read prewarm_prompts.json: %s", e)
    return list(_DEFAULT_PROMPTS)


def prewarm_claude_cache(prompts: Optional[list[str]] = None) -> dict[str, Any]:
    """Pre-write the Anthropic prompt cache for the demo's frozen system prefix.

    Returns a summary dict — never raises. Status values:
      * ``"ok"`` — at least one prompt warmed; ``cache_creation_tokens > 0``
        means the API actually wrote a cache entry.
      * ``"skipped"`` — preconditions not met (airgapped, no key, old SDK,
        or no Claude backend). The ``reason`` field explains.
      * ``"error"`` — the backend or SDK raised at construction time.

    Per-prompt failures are recorded in ``details`` rather than aborting.
    """
    from arail.airgap import is_airgapped
    if is_airgapped():
        return {"status": "skipped", "reason": "airgapped"}
    if not os.getenv("ANTHROPIC_API_KEY"):
        return {"status": "skipped", "reason": "no ANTHROPIC_API_KEY"}

    try:
        from arail.router.backends import ClaudeBackend
        backend = ClaudeBackend()
    except Exception as e:                                        # noqa: BLE001
        return {"status": "error", "reason": f"{type(e).__name__}: {e}"}

    if not getattr(backend, "_supports_cache", False):
        return {"status": "skipped", "reason": "anthropic SDK below 0.34.0"}

    # Build the same frozen system prefix the chat path will send at demo time.
    # include_state=False / extra_context=None — the volatile remainder is
    # added by the chat path on real turns and stays out of the cached prefix.
    from arail.lab_brain import build_system_prompt_parts
    frozen, _ = build_system_prompt_parts(
        include_state=False, extra_context=None)

    prompts_list = _load_prompts(prompts)
    total_creation = 0
    total_read = 0
    details: list[dict[str, Any]] = []

    for prompt in prompts_list:
        try:
            resp = backend.complete(
                prompt,
                max_tokens=1,    # canonical pre-warm value; safe across SDKs
                temperature=0.7,
                system=frozen,
                messages=[{"role": "user", "content": prompt}],
            )
            total_creation += resp.cache_creation_input_tokens
            total_read += resp.cache_read_input_tokens
            details.append({
                "prompt": prompt[:80],
                "cache_creation": resp.cache_creation_input_tokens,
                "cache_read": resp.cache_read_input_tokens,
            })
        except Exception as e:                                    # noqa: BLE001
            details.append({"prompt": prompt[:80],
                            "error": f"{type(e).__name__}: {e}"})

    return {
        "status": "ok",
        "prompts": len(prompts_list),
        "cache_creation_tokens": total_creation,
        "cache_read_tokens": total_read,
        "details": details,
    }
