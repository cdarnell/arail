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

# Splits assembled output into sentence-ish chunks so the institutional-
# character check reasons about "the sentence that made the claim", not an
# arbitrary character window that can accidentally straddle an unrelated
# vetted name written elsewhere in the same output.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# A candidate proper-noun institution name: a run of one or more
# capitalized-initial words (allowing internal connectors like "&"/"of").
# Used to find "the entity this sentence is actually naming" near an
# institutional-character trigger phrase, rather than treating "any vetted
# name is a substring somewhere in this window" as sufficient — the latter
# is what let a vetted *concept* term's own name ("Credit Union") silently
# vet the trigger phrase itself.
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][\w&'.-]*(?:\s+[A-Z][\w&'.-]*)*\b")


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


def _candidate_names(sentence: str) -> list[str]:
    """Capitalized-word-run substrings of ``sentence`` — candidate proper
    nouns that could be the institution the sentence is actually naming."""
    return [m.group(0) for m in _PROPER_NOUN_RE.finditer(sentence)]


def _names_match(candidate_lower: str, vetted_lower: str) -> bool:
    """True only if the candidate proper noun contains the vetted
    institution's *full* name as a substring.

    Deliberately one-directional: checking "is the candidate a substring of
    the vetted name" too would let a bare capitalized trigger word (e.g. a
    capitalized "Credit Union" written as part of the evaluative phrase
    itself) match any vetted institution whose name happens to contain that
    word (e.g. "PenFed Credit Union") — reintroducing the exact tautology
    this function exists to close. Requiring the *full* vetted name inside
    the candidate means a fictional or unvetted institution's name is never
    close enough by accident.
    """
    return vetted_lower in candidate_lower


def check_guardrail(text: str, vetted_institutions: frozenset[str]) -> GuardrailResult:
    """Deterministic pre-write check on an assembled output string.

    ``vetted_institutions`` is the lowercase set of specific, named,
    verified institutions' names — never a generic glossary/concept term
    (see ``terms.json``'s ``institutions`` category, where only entries
    carrying an ``institution_type`` field are named institutions). The
    only names allowed to sit near institutional-character language.

    Institutional-character language is checked sentence by sentence: for
    each sentence containing a trigger phrase, this extracts the candidate
    proper-noun institution name(s) actually present in *that* sentence and
    requires one of them to match a vetted name. This is deliberately
    stricter than "a vetted name appears anywhere in an 80-char window"
    (the tautology BLOCK-1 found: a vetted *concept* term whose name IS the
    trigger phrase itself would satisfy that check for any institution,
    vetted or not).
    """
    if _EVALUATIVE_RE.search(text):
        return GuardrailResult(
            ok=False,
            reason="evaluative or imperative language detected",
        )

    for sentence in _SENTENCE_SPLIT_RE.split(text):
        match = _INSTITUTIONAL_CHARACTER_RE.search(sentence)
        if match is None:
            continue
        candidates_lower = [c.lower() for c in _candidate_names(sentence)]
        matched = any(
            _names_match(candidate, vetted)
            for candidate in candidates_lower
            for vetted in vetted_institutions
        )
        if not matched:
            return GuardrailResult(
                ok=False,
                reason=(
                    "institutional-character language "
                    f"({match.group(0)!r}) not paired with a vetted, "
                    "specifically-named institution in the same sentence"
                ),
            )

    return GuardrailResult(ok=True)
