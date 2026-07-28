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
    r"\b(best|guaranteed|top[- ]pick|top choice|lowest|you should|you must|"
    r"recommend(?:ed|ation|s)?|advice|advis(?:e[sd]?|able)|optimal|cheapest|"
    r"smartest|better off|no[- ]brainer)\b",
    re.I,
)

# Reason strings returned by ``check_guardrail``. Exposed as constants (not
# just inline literals) so callers can branch a user-facing failure message
# on *which* branch fired without re-deriving the guardrail's own regex
# match text (REVIEW.md re-review addendum 3, item 3 — the ASK-B message was
# misdirecting operators at ``institution`` fields for evaluative-branch
# blocks). ``REASON_INSTITUTIONAL_PREFIX`` is a prefix, not an exact string,
# because that branch's message interpolates the matched phrase.
REASON_EVALUATIVE = "evaluative or imperative language detected"
REASON_INSTITUTIONAL_PREFIX = "institutional-character language ("

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

# Minimum length, in characters, a ``quoted_spans`` entry must have before
# it is eligible for masking ahead of the evaluative-language check. A
# global ``text.replace(span, ...)`` over a short, common substring (the
# review's own example: an operator-typed ``as_of='st'``) blanks that
# substring everywhere it occurs in the assembled body — including inside
# an unrelated word like "best" — which would silently defang the
# evaluative check for content that has nothing to do with the short value
# (REVIEW.md re-review addendum 4, ASK-C). Offset-based masking (blanking
# only the exact byte range where a span was interpolated into the
# template) would close this precisely, but the body is assembled by
# ordinary string formatting with no tracked insertion offsets, so instead
# any span shorter than this floor is simply never masked and falls back to
# being fully evaluative-checked. That degrades *closed* — a short
# operator-typed date fragment can, in principle, cause a false block — which
# the review explicitly judged a far smaller cost than a global word-level
# bypass. Chosen length covers realistic short trigger substrings ("best",
# "top") plus one character of margin; genuine quoted spans (URLs,
# institution names, feed titles) are always well above this floor.
_MIN_QUOTED_SPAN_LEN = 5

# A candidate proper-noun institution name: a run of one or more
# capitalized-initial words (allowing internal connectors like "&"/"of").
# Used to find "the entity this sentence is actually naming" near an
# institutional-character trigger phrase, rather than treating "any vetted
# name is a substring somewhere in this window" as sufficient — the latter
# is what let a vetted *concept* term's own name ("Credit Union") silently
# vet the trigger phrase itself.
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][\w&'.-]*(?:\s+[A-Z][\w&'.-]*)*\b")

# Minimum length, after whitespace-collapse and casefold, an allowed name
# (an ``operator_names`` or ``vetted_institutions`` entry) must have before
# it is eligible to pair-match an institutional-character claim at all.
# QA (TEST_REPORT.md F2) found ``_names_match`` was unanchored substring
# containment with no floor: a 1-char operator-typed institution name (or a
# whitespace-only one) is a substring of nearly every capitalized proper
# noun, so it "vetted" institutions the operator never named and the World
# never verified. This is the same defect class ``_MIN_QUOTED_SPAN_LEN``
# closes on the evaluative branch, applied here to the branch it was never
# applied to. Chosen length is short enough to admit real short lender
# names ("SoFi", "USAA", "PNC") while excluding single characters and
# whitespace.
_MIN_ALLOWED_NAME_LEN = 3


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
    """True only if the candidate text contains the vetted institution's
    *full* name as a whole-word-bounded, whitespace/case-normalized phrase.

    Deliberately one-directional: checking "is the candidate a substring of
    the vetted name" too would let a bare capitalized trigger word (e.g. a
    capitalized "Credit Union" written as part of the evaluative phrase
    itself) match any vetted institution whose name happens to contain that
    word (e.g. "PenFed Credit Union") — reintroducing the exact tautology
    this function exists to close. Requiring the *full* vetted name inside
    the candidate means a fictional or unvetted institution's name is never
    close enough by accident.

    TEST_REPORT.md F2/F3: two further hardenings over the original bare
    ``vetted_lower in candidate_lower`` substring check:

    1. A length floor (``_MIN_ALLOWED_NAME_LEN``) — a 1-char or
       whitespace-only allowed name is never eligible to match anything, no
       matter how it got into ``operator_names``/``vetted_institutions``.
    2. Word-boundary anchoring instead of bare containment — "ally" must
       not match inside "alliance"; only a whole-word (or whole-phrase)
       occurrence counts.

    Whitespace is collapsed and casing is folded (``str.casefold()``, not
    ``.lower()``, so non-ASCII initials normalize consistently) on the
    vetted side before matching, so a hand-typed trailing space or an
    accented initial letter doesn't cause a spurious non-match.
    """
    vetted_norm = " ".join(vetted_lower.split()).casefold()
    if len(vetted_norm) < _MIN_ALLOWED_NAME_LEN:
        return False
    candidate_norm = candidate_lower.casefold()
    return re.search(rf"\b{re.escape(vetted_norm)}\b", candidate_norm) is not None


def check_guardrail(
    text: str,
    vetted_institutions: frozenset[str],
    operator_names: frozenset[str] = frozenset(),
    quoted_spans: frozenset[str] = frozenset(),
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

    ``quoted_spans`` is the evaluative branch's analogue of
    ``operator_names``: a set of exact, literal, code-inserted substrings
    of ``text`` that are *quoted back verbatim* from a source other than
    the calling agent's own generated prose (REVIEW.md re-review addendum
    3, BLOCK-6) — e.g. a citation URL an operator pasted into
    ``candidate_scenarios.source``, or a scouted RSS feed's own title. The
    ``_EVALUATIVE_RE`` check is run against a *masked* copy of ``text``
    with every ``quoted_spans`` occurrence blanked out first, so a
    "best-balance-transfer-cards"-shaped URL or feed title can never
    suppress a whole document — while any evaluative word the agent's own
    prose contributes (which is never a member of ``quoted_spans``) is
    still caught. This is deliberately scoped to exact literal spans, not
    a vocabulary exemption: widening the word list itself would let the
    model's own generated prose say "best" freely too, which is the
    defect this parameter exists to avoid reintroducing. Callers must pass
    an empty frozenset here for any text whose evaluative-sounding words
    are not a literal, code-inserted echo of a non-agent source (in
    particular, ``_framing_prose``'s standalone self-check always passes
    an empty set here — model-generated prose gets no exemption of any
    kind, on either branch).

    Spans shorter than ``_MIN_QUOTED_SPAN_LEN`` are never masked, even if
    present in this set: masking is a global substring replace over the
    whole assembled body (there is no tracked insertion offset), so a
    short, common quoted value would otherwise blank itself out of
    unrelated words too (e.g. ``as_of='st'`` matching inside "be**st**") and
    silently defang the evaluative check for content that has nothing to
    do with it. Short spans instead fall back to being fully
    evaluative-checked, which degrades closed rather than open.

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
    # Longest-first: a shorter quoted span that happens to be a substring of
    # a longer one (e.g. "balance-transfer" inside a
    # ".../best-balance-transfer-cards" URL) must not be masked first —
    # doing so would corrupt the longer span's text so the longer
    # ``.replace()`` no longer finds an exact match, leaving the
    # surrounding "best"/"-cards" fragments of the URL unmasked and the
    # evaluative check still tripped on them.
    masked_for_evaluative = text
    for span in sorted(
        (s for s in quoted_spans if s and len(s) >= _MIN_QUOTED_SPAN_LEN),
        key=len, reverse=True,
    ):
        masked_for_evaluative = masked_for_evaluative.replace(span, " " * len(span))
    if _EVALUATIVE_RE.search(masked_for_evaluative):
        return GuardrailResult(
            ok=False,
            reason=REASON_EVALUATIVE,
        )

    allowed_names = vetted_institutions | operator_names

    # NOTE: the institutional-character check below always runs against the
    # original, unmasked ``text`` — ``quoted_spans`` only ever narrows the
    # evaluative-language check above. A quoted span containing
    # institutional-character language is not exempted by this parameter;
    # that provenance question is what ``operator_names``/
    # ``vetted_institutions`` already answer for this branch.
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
            # TEST_REPORT.md F3: ``_PROPER_NOUN_RE`` requires an ASCII
            # capital initial, but the trigger regex above (and this
            # module's whole matching design) is case-insensitive. An
            # operator who types their own institution name in lowercase,
            # or whose name starts with a non-ASCII letter (e.g. "Éole"),
            # never produces a capitalized candidate at all — so the exact,
            # documented-as-case-insensitive exemption path can never fire
            # for them. Fall back to matching an allowed name directly
            # against the raw window text (case-folded, word-boundary
            # anchored via ``_names_match``) so the candidate-name
            # extraction step is consistent with the rest of the
            # guardrail's case-insensitive design, rather than a second,
            # stricter gate in front of it.
            if not matched:
                # Guard against reintroducing BLOCK-1's tautology: an
                # allowed name whose normalized form is *identical* to the
                # trigger phrase's own matched text (e.g. a vetted set
                # naively containing the bare generic term "credit union"
                # itself) must never satisfy this fallback — that would let
                # the trigger phrase vet itself, telling us nothing about
                # any actual institution's identity. A genuine institution
                # name that happens to *contain* the trigger phrase as part
                # of a longer name (e.g. "Navy Federal Credit Union") is
                # unaffected: it is not identical to the bare trigger text,
                # only a superset of it.
                match_norm = " ".join(match.group(0).split()).casefold()
                matched = any(
                    _names_match(window, allowed)
                    for allowed in allowed_names
                    if " ".join(allowed.split()).casefold() != match_norm
                )
            if not matched:
                return GuardrailResult(
                    ok=False,
                    reason=(
                        f"{REASON_INSTITUTIONAL_PREFIX}{match.group(0)!r}) "
                        "not paired with a vetted, specifically-named "
                        "institution near that claim"
                    ),
                )

    return GuardrailResult(ok=True)
