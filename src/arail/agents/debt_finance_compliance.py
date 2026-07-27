"""Shared compliance module for the debt-finance World's two agents.

Per ``sprints/2026-07-26-world-of-debt-finance/ARCHITECTURE.md`` §7.1/§7.2,
both ``debt_advisor`` and ``consolidation_analyzer`` share exactly one
implementation of:

1. ``read_disclaimer()`` — reads the mounted World's ``compliance/
   DISCLAIMER.md`` fresh every call, no caching, so an edit takes effect on
   the very next tick.
2. ``check_guardrail()`` — a deterministic, code-level (not LLM-based)
   evaluative-language + institutional-character check that runs on every
   assembled output string before it's ever written to a findings file.

Neither function ever touches ``lab/pkb/`` for *content* it returns to the
caller — this module is arithmetic/string logic over the mounted World's
own sealed files and the caller-supplied text, nothing more.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# The single canonical phrase used as the disclaimer's precondition check.
# Kept as a short, fixed substring per ARCHITECTURE.md §7.1 — if this phrase
# is edited out of compliance/DISCLAIMER.md, both agents refuse to write.
CANONICAL_PHRASE = "not licensed financial advisors"

# Evaluative / imperative vocabulary the guardrail blocks. Documented as a
# defense-in-depth heuristic, not a safety classifier (ARCHITECTURE.md §7.2,
# §13.2) — it closes the "zero backstop" review finding, it does not claim
# to catch every adversarially-phrased attempt.
_EVALUATIVE_RE = re.compile(
    r"\b(best|guaranteed|top[- ]pick|top choice|lowest|you should|you must)\b",
    re.I,
)

# Institutional-character language that may only be paired with a vetted
# institution name (one present in the World's terms.json institutions set
# with its own verification source).
_INSTITUTIONAL_CHARACTER_RE = re.compile(
    r"\b(credit union|nonprofit|non-profit|member-owned)\b",
    re.I,
)


@dataclass
class GuardrailResult:
    ok: bool
    reason: str = ""


def find_mounted_bundle_dir() -> Optional[Path]:
    """Return the currently-mounted World's sealed bundle directory, if any.

    This is the bundle's *authoring* directory (``bundle_dir`` on the mount
    record) — not the staged, indexed copy under ``lab/pkb/sources/`` — so
    reads here never touch the PKB-indexed tree.
    """
    try:
        from arail import world_mount as wm
        record = wm.current_mount()
    except Exception:
        return None
    if record is None:
        return None
    return Path(record.bundle_dir)


def read_disclaimer(bundle_dir: Optional[Path] = None) -> Optional[str]:
    """Read compliance/DISCLAIMER.md fresh from the mounted World.

    Returns ``None`` (never raises) if the mounted World, or the file, or
    the canonical phrase within it, is missing. Callers use ``None`` as the
    precondition-failure signal — never cached across calls.
    """
    root = bundle_dir if bundle_dir is not None else find_mounted_bundle_dir()
    if root is None:
        return None
    path = root / "compliance" / "DISCLAIMER.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if CANONICAL_PHRASE not in text:
        return None
    return text


def check_guardrail(text: str, vetted_institutions: frozenset[str]) -> GuardrailResult:
    """Deterministic pre-write check on an assembled output string.

    ``vetted_institutions`` is the lowercase set of institution names that
    appear in the mounted World's ``terms.json`` institutions category with
    a verification source — the only names allowed to sit near
    institutional-character language.
    """
    if _EVALUATIVE_RE.search(text):
        return GuardrailResult(
            ok=False,
            reason="evaluative or imperative language detected",
        )

    for match in _INSTITUTIONAL_CHARACTER_RE.finditer(text):
        # Look at a window of text around the match for a vetted name.
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 80)
        window = text[start:end].lower()
        if not any(name in window for name in vetted_institutions):
            return GuardrailResult(
                ok=False,
                reason=(
                    "institutional-character language "
                    f"({match.group(0)!r}) not paired with a vetted "
                    "institution name"
                ),
            )

    return GuardrailResult(ok=True)
