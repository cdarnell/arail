# Learning: Anthropic prompt caching on ARAIL's flat backend interface

**Date:** 2026-05-22
**Sprint:** arail-aerollm-72b-lift (prompt-caching)
**Context:** Adding `cache_control` to the `claude` backend only — caching is an Anthropic-only feature, so it never touches local inference or airgapped mode.

## The action-shaped takeaways

### 1. When adding a Claude-only capability, don't widen the shared backend contract — make it optional and Claude-consumed
All 10 backends share `complete(prompt: str, ...)`. Threading a full structured
`messages` list down (the obvious way to cache) would have broken the uniform
text-in/text-out seam. Instead we added **optional keyword-only** `system` /
`messages` params: non-Claude backends prepend `system` to the flat prompt
(`f"{system}\n\n{prompt}"`, byte-identical to before) and ignore `messages`;
only `ClaudeBackend` builds a native cached request. The deep-tier and
runtime-override chat paths call `backend.complete()` **directly, bypassing the
router**, so the param had to live on the backend method, not just the router.

### 2. The silent cache-killer was a timestamp in the *middle* of the system prompt
`build_system_prompt` interpolated `datetime.now()` into the state block, which
sat between the capabilities reference and the rest. Because caching is a
**byte-prefix match**, that per-second timestamp invalidated everything after it
on every request. Fix: split into a frozen prefix (identity + capabilities +
how-to-answer) and a volatile remainder (state + KB), and move the volatile part
into the final chat turn — *after* the breakpoint. When you add caching to any
prompt, **grep the prefix for `datetime.now()`, `uuid`, unsorted `json.dumps`,
per-user IDs** first.

### 3. The model sets the cache floor — modernizing the model can *disable* caching
We modernized the default `claude-sonnet-4-20250514` (retires 2026-06-15) →
`claude-sonnet-4-6`. But Sonnet 4.6's minimum cacheable prefix is **2048 tokens**
(vs. 1024 for the old Sonnet 4), and ARAIL's frozen chat prefix is only ~1.2K.
So the single-shot chat system block **won't cache on its own** — chat caching
now comes from multi-turn growth (system + history crosses 2048 ~turn 3) and
from the Researcher (intent context + skills). Opus would push the floor to 4096
and shrink the payoff further. **Always check the target model's floor against
your actual prefix size before claiming a caching win.** We made the breakpoint
threshold-aware: below the floor we send a plain prefix instead of a useless
marker.

### 4. Latent bug found in passing: Claude 4+ rejects `temperature` AND `top_p` together
The old `ClaudeBackend` sent `temperature` always and `top_p` when a preset set
it — a 400 on every Claude 4+ model the moment a user picked a Factual/Code
preset. Fixed to send at most one (prefer an explicit `top_p`, else
`temperature`). Migrating a model is a good moment to re-read the API's breaking
changes for the whole call, not just the model string.

## What to watch for

- Keep the frozen prefix **byte-stable**. There's a regression test
  (`tests/test_lab_brain.py`) asserting `build_system_prompt_parts` returns an
  identical frozen prefix across calls with different state/time. If it goes red,
  someone leaked volatile data into the cacheable prefix.
- Cache savings are only **visible** via `cache_read_tokens` /
  `cache_creation_tokens` in the cost summary. If they're zero on repeated Claude
  calls, diff the rendered prefix bytes between two requests to find the
  invalidator.
