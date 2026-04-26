"""Backcompat import surface for Buddy.

``from arail.agents.buddy import buddy`` is the canonical way to
reach the lab's personality agent. Internally this delegates to the
generic agent loader so Buddy and every future agent share one code
path.

Call sites that pre-date the loader import Buddy directly. Everything
that uses the loader (``load_all()`` / ``load_one("buddy")``) goes
through the same cache, so both paths resolve to the same instance —
no double BuddyAgent ticking in parallel.
"""

from __future__ import annotations

from arail.agents.loader import load_one

# Resolve at import time so existing call sites get a real BuddyAgent,
# not a lazy proxy. The loader handles seeding, dynamic import from
# the PKB copy, and fallback to the builtin — all the work that used
# to live inline in this shim.
buddy = load_one("buddy")

# If the loader genuinely can't resolve Buddy (loader failure + no
# builtin), fall back once more to a fresh builtin instance so
# ``buddy`` is never None. Any runtime crash is preferable to a
# NoneType attribute error on startup.
if buddy is None:  # pragma: no cover — extreme fallback
    from arail.agents._builtin_buddy import buddy as _fallback_buddy
    buddy = _fallback_buddy
