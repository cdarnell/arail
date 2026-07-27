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

import datetime as _dt
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
#
# Also splits on newlines (BLOCK-4): a rendered list item (e.g. Debt
# Advisor's vetted-institution line, which ends in `)` with no terminal
# punctuation) is a unit of assertion on its own line, and must never merge
# with the following line into one "sentence" — that merge is exactly what
# let an unvetted institution on one line ride along on a vetted name on the
# line above it.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

# A sealed named-institution's verification is only trusted for this many
# days past its `verified_as_of` date before the mechanism degrades closed
# (excluded from the vetted set, not silently trusted forever). A year
# matches the operator's own annual re-check commitment.
_VERIFICATION_STALENESS_DAYS = 365

# How far, in characters, to either side of a trigger-phrase occurrence to
# look for the proper-noun name it's actually naming. Local to the
# occurrence, not the whole chunk — see check_guardrail's docstring for why
# a chunk-wide candidate list reintroduces a positional tautology.
_PROXIMITY_WINDOW_CHARS = 40

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


def is_verification_fresh(verified_as_of: str, today: Optional[_dt.date] = None) -> bool:
    """True only if ``verified_as_of`` is a parseable ISO date within
    ``_VERIFICATION_STALENESS_DAYS`` of ``today``.

    Missing or unparseable dates are treated as not fresh — an institution
    without a valid ``verified_as_of`` never enters the vetted set at all.
    This makes staleness degrade closed (excluded, so any character claim
    about the institution gets blocked) rather than silently asserting a
    possibly-stale fact forever.
    """
    if not verified_as_of:
        return False
    try:
        parsed = _dt.date.fromisoformat(str(verified_as_of))
    except (ValueError, TypeError):
        return False
    now = today if today is not None else _dt.date.today()
    return (now - parsed).days <= _VERIFICATION_STALENESS_DAYS


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


def check_guardrail(
    text: str,
    vetted_institutions: frozenset[str],
    operator_names: frozenset[str] = frozenset(),
) -> GuardrailResult:
    """Deterministic pre-write check on an assembled output string.

    ``vetted_institutions`` is the lowercase set of specific, named,
    verified institutions' names — never a generic glossary/concept term
    (see ``terms.json``'s ``institutions`` category, where only entries
    carrying an ``institution_type`` field are named institutions). The
    only World-sourced names allowed to sit near institutional-character
    language.

    ``operator_names`` is a distinct, narrower exemption: names sourced
    *only* from the operator's own parsed ``balances.json`` — the product
    quoting the user back to themselves, not asserting anything about a
    third party. Matched with the identical strict rule as
    ``vetted_institutions``, never looser. Callers must pass an empty
    frozenset here for any text that is not a literal, code-inserted echo
    of the operator's own data (World-sourced text and all
    model-generated/framing prose get no exemption of any kind).

    Institutional-character language is checked chunk by chunk, where a
    chunk is a sentence *or* a newline-delimited line (BLOCK-4: a rendered
    list item without terminal punctuation is a unit of assertion on its
    own and must never merge with an adjacent line). Within a chunk, every
    occurrence of a trigger phrase is checked independently (``finditer``,
    not ``search`` — a single chunk naming both a vetted and an unvetted
    institution must still block on the unvetted one): for each occurrence,
    candidate proper-noun names are drawn only from a local window around
    *that* occurrence (``_PROXIMITY_WINDOW_CHARS`` on each side, clipped to
    the chunk), not from the whole chunk — otherwise a vetted name written
    anywhere in a chunk that also names an unvetted institution would
    satisfy every trigger in that chunk regardless of which claim it is
    actually attached to (the same tautology class as BLOCK-1, one level
    down). One of the local candidates must match a vetted or operator
    name. This is deliberately stricter than "a vetted name appears
    anywhere in an 80-char window" as a *chunk-wide* rule (the tautology
    BLOCK-1 found: a vetted *concept* term whose name IS the trigger phrase
    itself would satisfy that check for any institution, vetted or not).
    """
    if _EVALUATIVE_RE.search(text):
        return GuardrailResult(
            ok=False,
            reason="evaluative or imperative language detected",
        )

    allowed_names = vetted_institutions | operator_names

    for chunk in _SENTENCE_SPLIT_RE.split(text):
        for match in _INSTITUTIONAL_CHARACTER_RE.finditer(chunk):
            window_start = max(0, match.start() - _PROXIMITY_WINDOW_CHARS)
            window_end = min(len(chunk), match.end() + _PROXIMITY_WINDOW_CHARS)
            window = chunk[window_start:window_end]
            candidates_lower = [c.lower() for c in _candidate_names(window)]
            matched = any(
                _names_match(candidate, allowed)
                for candidate in candidates_lower
                for allowed in allowed_names
            )
            if not matched:
                return GuardrailResult(
                    ok=False,
                    reason=(
                        "institutional-character language "
                        f"({match.group(0)!r}) not paired with a vetted, "
                        "specifically-named institution near that claim"
                    ),
                )

    return GuardrailResult(ok=True)
