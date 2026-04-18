"""Backcompat import surface for Pip.

Historical — ``from oglab.agents.pip import pip`` has worked since
Step 1. It still does, but the implementation now delegates to the
generic agent loader so Pip and every future agent share one code
path.

Call sites that pre-date the loader import Pip directly. Everything
Step 4+ uses the loader (``load_all()`` / ``load_one("pip")``)
explicitly. Both paths resolve to the same cached instance — no
double PipAgent ticking in parallel.
"""

from __future__ import annotations

from oglab.agents.loader import load_one

# Resolve at import time so existing call sites get a real PipAgent,
# not a lazy proxy. The loader handles seeding, dynamic import from
# the PKB copy, and fallback to the builtin — all the work that used
# to live inline in this shim.
pip = load_one("pip")

# If the loader genuinely can't resolve Pip (loader failure + no
# builtin), fall back once more to a fresh builtin instance so
# ``pip`` is never None. Any runtime crash is preferable to a
# NoneType attribute error on startup.
if pip is None:  # pragma: no cover — extreme fallback
    from oglab.agents._builtin_pip import pip as _fallback_pip
    pip = _fallback_pip
