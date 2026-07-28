"""Shared compliance module for the debt-finance World's two agents.

Per ``sprints/2026-07-26-world-of-debt-finance/ARCHITECTURE.md`` §7.1/§7.2/
§13.11 (now implemented, not just recorded — see that section's history and
BUILD_LOG.md's "Structural refactor: segment-based provenance" entry), both
``debt_advisor`` and ``consolidation_analyzer`` share exactly one
implementation of:

1. ``read_disclaimer()`` — reads the mounted World's ``compliance/
   DISCLAIMER.md`` fresh every call, no caching, so an edit takes effect on
   the very next tick.
2. ``check_guardrail()`` — a deterministic, code-level (not LLM-based)
   evaluative-language + institutional-character check that runs on every
   assembled output before it's ever written to a findings file.

Neither function ever touches ``lab/pkb/`` for *content* it returns to the
caller — this module is arithmetic/string logic over the mounted World's
own sealed files and the caller-supplied segments, nothing more.

## Segment-based provenance (structural refactor)

``check_guardrail`` used to take a single flat *string* plus three optional
sets (``operator_names``, ``vetted_institutions``, ``quoted_spans``) and try
to *reconstruct*, after the fact, which parts of that string were
agent-generated versus quoted verbatim from a trusted source — by masking
substrings, matching names with fuzzy containment rules, and reasoning about
character-offset proximity windows. Ten findings across seven review rounds
(see TEST_REPORT.md) all trace to that same shape of bug: a matcher
approximating a provenance question from flat text will always have another
escape one level deeper, because the flat string has already thrown the
provenance information away.

The fix: both agents now assemble their output as an ordered list of
``Segment(text, provenance)`` pieces, where ``provenance`` is fixed at
construction time — the caller *knows*, when it writes
``Segment.world(v.name)``, that ``v.name`` came from the sealed World's
vetted terms, not from the model. ``check_guardrail`` never re-derives this;
it only ever asks "what provenance tag did the caller attach to this text",
which cannot be spoofed by clever phrasing, casing, whitespace, or a
transform applied between a field and its rendered form — every one of
which was a distinct historical finding here.

- ``Provenance.AGENT`` — model-generated or hardcoded-by-this-codebase
  prose (headings, connective text, framing sentences).
- ``Provenance.WORLD`` — World-sealed content: a vetted institution's name,
  ``institution_type``, ``verification_source``, ``verified_as_of``, or a
  scouting finding's ``feed``/``path``.
- ``Provenance.OPERATOR`` — parsed verbatim from the operator's own
  ``balances.json`` (``institution``, ``product``, ``source``, ``as_of``
  from both ``debts`` and ``candidate_scenarios``).

The evaluative/imperative-language check runs ONLY over the concatenation
of ``AGENT`` segments — a ``WORLD`` or ``OPERATOR`` segment can never be
evaluative-checked at all, regardless of what words it happens to contain,
because it is never the agent's own words by construction.

The institutional-character check still runs over the full, in-order
concatenation of every segment (it legitimately needs the whole rendered
line — an agent could in principle pair a real vetted name with an
unvetted one in its own connective prose) but answers "is the name this
trigger is pairing with actually trusted" by looking at the *provenance* of
the text immediately surrounding the trigger's own segment — the trigger's
own segment, or either of its immediate neighbours — rather than by
re-finding a name via regex/substring matching against a set of allowed
strings. A candidate name that lives only inside an ``AGENT`` segment can
never be treated as vetted or operator-stated, because there is no
provenance-tagged escape hatch for it — it fails closed by construction,
not by omission of yet another special case.
"""

from __future__ import annotations

import datetime as _dt
import enum
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

# The single canonical phrase used as the disclaimer's precondition check.
# Kept as a short, fixed substring per ARCHITECTURE.md §7.1 — if this phrase
# is edited out of compliance/DISCLAIMER.md, both agents refuse to write.
CANONICAL_PHRASE = "not licensed financial advisors"

# Evaluative / imperative vocabulary the guardrail blocks. Documented as a
# defense-in-depth heuristic, not a safety classifier (ARCHITECTURE.md §7.2,
# §13.2) — it closes the "zero backstop" review finding, it does not claim
# to catch every adversarially-phrased attempt. This check now only ever
# runs over AGENT-provenance text (see module docstring), so a genuinely
# quoted WORLD/OPERATOR string can never trip it no matter what words it
# contains — the historical "quoted URL contains 'best'" defect class is
# gone by construction, not by a masking countermeasure.
_EVALUATIVE_RE = re.compile(
    r"\b(best|guaranteed|top[- ]pick|top choice|lowest|you should|you must|"
    r"recommend(?:ed|ation|s)?|advice|advis(?:e[sd]?|able)|optimal|cheapest|"
    r"smartest|better off|no[- ]brainer)\b",
    re.I,
)

# Reason strings returned by ``check_guardrail``. Exposed as constants (not
# just inline literals) so callers can branch a user-facing failure message
# on *which* branch fired without re-deriving the guardrail's own regex
# match text. ``REASON_INSTITUTIONAL_PREFIX`` is a prefix, not an exact
# string, because that branch's message interpolates the matched phrase.
REASON_EVALUATIVE = "evaluative or imperative language detected"
REASON_INSTITUTIONAL_PREFIX = "institutional-character language ("

# Institutional-character language that may only be paired with a name whose
# provenance is WORLD (a vetted institution) or OPERATOR (the operator's own
# stated name) — never a name that exists only inside AGENT-provenance text.
_INSTITUTIONAL_CHARACTER_RE = re.compile(
    r"\b(credit union|nonprofit|non-profit|member-owned)\b",
    re.I,
)

# A sealed named-institution's verification is only trusted for this many
# days past its `verified_as_of` date before the mechanism degrades closed
# (excluded from the vetted set, not silently trusted forever). A year
# matches the operator's own annual re-check commitment.
_VERIFICATION_STALENESS_DAYS = 365


class Provenance(enum.Enum):
    """Where a piece of assembled output text actually came from.

    Fixed at the point each agent's ``_build_output`` constructs a
    ``Segment`` — never re-derived from the text itself. See the module
    docstring for what each value means and why this replaces the old
    flat-string masking/matching machinery.
    """

    AGENT = "agent"
    WORLD = "world"
    OPERATOR = "operator"


@dataclass(frozen=True)
class Segment:
    """One piece of assembled output text, tagged with where it came from.

    Both agents' ``_build_output`` build their entire rendered document as
    an ordered list of these — never a flat f-string — so
    ``check_guardrail`` can answer every provenance question by construction
    instead of by re-deriving it from string content.
    """

    text: str
    provenance: Provenance

    @classmethod
    def agent(cls, text: str) -> "Segment":
        """Model-generated or hardcoded-by-this-codebase prose."""
        return cls(text, Provenance.AGENT)

    @classmethod
    def world(cls, text: str) -> "Segment":
        """World-sealed content (a vetted institution's structured fields,
        or a scouting finding's feed/path metadata)."""
        return cls(text, Provenance.WORLD)

    @classmethod
    def operator(cls, text: str) -> "Segment":
        """Parsed verbatim from the operator's own ``balances.json``."""
        return cls(text, Provenance.OPERATOR)


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


def check_guardrail(segments: Sequence[Segment]) -> GuardrailResult:
    """Deterministic pre-write check on an assembled, segment-tagged output.

    ``segments`` is the ordered list of ``Segment`` pieces that, concatenated
    in order, form the exact text that would be written to the findings
    file. Provenance is answered by construction — see the module
    docstring — never by re-deriving it from the text.

    **Evaluative/imperative language check:** runs only over the
    concatenation of ``AGENT``-provenance segments (joined with a single
    space, so two adjacent AGENT segments can never fuse into a word neither
    of them contains on their own). A ``WORLD`` or ``OPERATOR`` segment is
    never evaluative-checked, no matter what words it contains — this is
    what makes a citation URL or a real institution's own marketed name
    (both historical false-block findings) impossible to reintroduce: they
    are simply never candidates for this check at all.

    **Institutional-character check:** runs over the full, in-order
    concatenation of every segment (this branch legitimately needs the
    whole rendered line, per ARCHITECTURE.md §13.11's design intent — an
    agent could in principle pair a real vetted name with an unvetted one in
    its own connective prose). For each occurrence of an institutional-
    character trigger phrase (found within one segment's own text — by
    construction, this codebase never splits a literal trigger phrase
    across a segment boundary), the claim is legitimate only if the
    trigger's own segment, or either of its immediate neighbouring
    segments, carries ``WORLD`` or ``OPERATOR`` provenance. A name that
    exists only inside ``AGENT``-provenance text — invented or altered by
    the model — can never satisfy this, because there is no string it could
    be altered *to* that would change its segment's provenance tag.
    """
    agent_text = " ".join(
        s.text for s in segments if s.provenance is Provenance.AGENT
    )
    if _EVALUATIVE_RE.search(agent_text):
        return GuardrailResult(ok=False, reason=REASON_EVALUATIVE)

    for idx, seg in enumerate(segments):
        for match in _INSTITUTIONAL_CHARACTER_RE.finditer(seg.text):
            neighbours = [seg.provenance]
            if idx > 0:
                neighbours.append(segments[idx - 1].provenance)
            if idx + 1 < len(segments):
                neighbours.append(segments[idx + 1].provenance)
            if any(p is not Provenance.AGENT for p in neighbours):
                continue
            return GuardrailResult(
                ok=False,
                reason=(
                    f"{REASON_INSTITUTIONAL_PREFIX}{match.group(0)!r}) "
                    "not paired with a vetted, specifically-named "
                    "institution near that claim"
                ),
            )

    return GuardrailResult(ok=True)
