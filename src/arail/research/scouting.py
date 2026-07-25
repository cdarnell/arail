"""Layer C — optional, hybrid-only, consent-gated scouting.

Two "agents on the lookout" checks the Video Games World declares as desired
(``scout.driver-watch``, ``scout.release-watch``): notice a new GPU driver
worth reviewing, or a newly released game worth staging into the knowledge
base. Both are OFF by default and stay inert until every one of these is true:

  1. ``LAB_MODE=hybrid`` — airgapped hard-blocks via ``egress.allow_egress``,
     which raises immediately on entry in airgapped mode. There is no bypass.
  2. A specific ``ConsentStore`` request has been approved by the user —
     the same durable, auditable record the World Forge's fetch consent uses.
  3. A fetcher is configured — this module never constructs a URL or knows
     what one looks like. It takes a zero-argument ``Callable[[], Any]`` the
     caller closes over; whatever the caller decides to check (a specific
     GPU family, a specific game) is bound in that closure and never touches
     this module. This is structural, not a promise: scouting.py has no way
     to put hardware, game, or driver identifiers into an outbound URL
     because it never builds one.

A successful fetch produces a *finding* — a plain, reviewable dict — never an
installed driver and never an auto-approved knowledge-base entry. Staging a
finding into the PKB for human review through the Compiled-KB gate is the
caller's responsibility; this module's job ends at "here's what was found,
gated and audited."

No production fetcher ships here. `capabilities.json` declares
``scout.driver-watch``/``scout.release-watch`` as desired; until a real vendor
integration is wired in as a fetcher, they resolve `declared_unavailable` —
the honest state, not a placeholder pretending to work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from arail.airgap import EgressBlocked
from arail.egress import allow_egress

# States, in order of how far a check got before stopping:
#   inert_airgapped   — LAB_MODE isn't hybrid; nothing was attempted
#   consent_required  — hybrid, but this consent_id isn't approved yet
#   cannot_run        — hybrid + consented, but no fetcher configured or it failed
#   finding           — fetched successfully; a reviewable, NOT-auto-approved finding
_STATES = ("inert_airgapped", "consent_required", "cannot_run", "finding")


@dataclass
class ScoutContext:
    consent_id: str
    reason: str
    fetcher: Optional[Callable[[], Any]] = None


@dataclass
class ScoutResult:
    kind: str                              # "driver-watch" | "release-watch"
    state: str                             # one of _STATES
    message: str
    finding: Optional[dict] = None         # only set when state == "finding"


def _gate(kind: str, ctx: ScoutContext) -> Optional[ScoutResult]:
    """Consent check only — the airgap gate is enforced by allow_egress
    itself at call time, not duplicated here."""
    from arail.agents.consent import ConsentStore
    if not ConsentStore().is_approved(ctx.consent_id):
        return ScoutResult(
            kind=kind, state="consent_required",
            message=f"{kind} needs an approved consent ({ctx.consent_id}) "
                    "before it will contact the network")
    return None


def _run(kind: str, ctx: ScoutContext, summarize: Callable[[Any], dict]) -> ScoutResult:
    gated = _gate(kind, ctx)
    if gated is not None:
        return gated
    if ctx.fetcher is None:
        return ScoutResult(kind=kind, state="cannot_run",
                           message=f"no fetcher configured for {kind}")
    try:
        with allow_egress(ctx.reason):
            data = ctx.fetcher()
    except EgressBlocked:
        return ScoutResult(
            kind=kind, state="inert_airgapped",
            message=f"{kind} only runs in hybrid mode — the lab is airgapped")
    except Exception as e:
        return ScoutResult(kind=kind, state="cannot_run",
                           message=f"{kind} fetch failed: {type(e).__name__}")
    finding = summarize(data)
    finding["requires_review"] = True
    finding["auto_approved"] = False
    return ScoutResult(kind=kind, state="finding",
                       message=f"{kind} found something worth a human look",
                       finding=finding)


def check_driver_watch(ctx: ScoutContext) -> ScoutResult:
    """Look for a new GPU driver release worth reviewing. Never installs
    anything — the finding is a reviewable note, not an action."""
    return _run("driver-watch", ctx, lambda data: {"driver_data": data})


def check_release_watch(ctx: ScoutContext) -> ScoutResult:
    """Look for a newly released game worth staging into the knowledge base
    for human review. Never auto-approves — see compiled_kb's gate."""
    return _run("release-watch", ctx, lambda data: {"release_data": data})
