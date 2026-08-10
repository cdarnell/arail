"""The class check: "declared and not instantiated" as a standing assertion,
not a fourth incident.

Three instances of the same defect class shipped in two releases (QA-6: the
Compiled-KB gate shipped on with nothing ever approved; defect A: the
relational store shipped with nothing ever creating it; defect B: the
vector-backend-absent branch shipped silent). Two of the three passed
``doctor``. This module is the structural answer:

    A mechanism may be off (not declared) or on-and-working. "On, and
    nothing has ever performed the step that makes it real" is a *third*
    state, and it is always reported — never silent.

Every declared mechanism registers its own instantiation predicate here.
``./arailctl doctor`` evaluates every one and reports a finding for any
mechanism that is declared but not instantiated, tier "required" (exit 3)
or "info". ``./arailctl status`` summarizes the same table under
``arail.provisioning/v1``.

Anti-goal: this is not a health monitor. Every predicate here is a
file-stat, an import check, or a read-only ``PRAGMA`` — no embeds, no HTTP,
no index builds, ever.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List


@dataclass(frozen=True)
class Assertion:
    key: str
    tier: str          # "required" | "info"
    declared: bool
    instantiated: bool
    detail: str
    action: str

    @property
    def finding(self) -> bool:
        """declared and not instantiated => a finding, never silence."""
        return self.declared and not self.instantiated


AssertionFn = Callable[..., Assertion]

_REGISTRY: dict = {}


def register(key: str, fn: AssertionFn) -> None:
    """Add a mechanism's instantiation predicate to the registry. Adding a
    mechanism to ARAIL 2.1 without registering an assertion here should
    feel like an omission — this registry is the checklist."""
    _REGISTRY[key] = fn


def registered_keys() -> List[str]:
    return sorted(_REGISTRY)


def _reset_for_tests() -> None:
    """Test-only: clear the registry so a test can register a synthetic
    mechanism without leaking into other tests."""
    _REGISTRY.clear()


# ── Built-in assertions ──────────────────────────────────────────────────

def check_relational_store(*, repo_root, data_dir, spec_dir=None) -> Assertion:
    """defect A: spec/schema/* declares the store; ensure_db(apply=False)
    tells us whether it has ever actually been created.

    REVIEW.md ASK-1: ``spec_dir`` resolves from the package location
    (``arail.dbspec.ensure.DEFAULT_SPEC_DIR``), never from ``repo_root``/
    CWD, for the same reason ``ensure_db`` itself does — a caller with the
    wrong working directory must not get a silent, non-degrading
    "unavailable" on a perfectly healthy database. ``repo_root`` is still
    used for ``data_dir``-adjacent checks (``check_instance_registry``)
    where CWD-independence isn't needed the same way."""
    from arail.dbspec.ensure import ensure_db, DEFAULT_SPEC_DIR
    spec_dir = Path(spec_dir) if spec_dir is not None else DEFAULT_SPEC_DIR
    declared = (spec_dir / "schema" / "migrations").is_dir()
    if not declared:
        return Assertion("relational_store", "required", False, False,
                         "no spec/schema/migrations/ in this checkout", "")
    report = ensure_db(data_dir, apply=False, spec_dir=spec_dir)
    instantiated = report.state == "ok"
    return Assertion(
        "relational_store", "required", declared, instantiated,
        detail=(f"{report.state}: {report.detail}" if report.detail
                else report.state),
        action=report.action or "./arailctl install",
    )


def check_vector_backend(**_kw) -> Assertion:
    """defect B: LanceDB is a hard dep in both tiers (declared); is it
    importable in THIS interpreter (instantiated)?"""
    from arail.vector_index import available
    ok = available()
    return Assertion(
        "vector_backend", "required", True, ok,
        detail="" if ok else "LanceDB is not importable in this interpreter",
        action="" if ok else "./arailctl install",
    )


def check_kb_gate(**_kw) -> Assertion:
    """QA-6: the Compiled-KB gate is declared on; is anything approved (or
    is there an explicit empty decision on record)?"""
    try:
        from arail import compiled_kb
    except Exception as exc:  # noqa: BLE001
        return Assertion("kb_gate", "info", True, False, f"unavailable: {exc}",
                         "./arailctl pkb approve")
    try:
        gate_on = bool(getattr(compiled_kb, "gate_enabled", lambda: True)())
    except Exception:  # noqa: BLE001
        gate_on = True
    if not gate_on:
        return Assertion("kb_gate", "info", False, False, "gate not declared on", "")
    try:
        approved = compiled_kb.approved_paths()
    except Exception as exc:  # noqa: BLE001
        return Assertion("kb_gate", "required", True, False, str(exc),
                         "./arailctl pkb approve")
    instantiated = len(approved) > 0
    return Assertion(
        "kb_gate", "required", True, instantiated,
        detail="" if instantiated else "gate is on but nothing has ever been approved",
        action="" if instantiated else "./arailctl pkb approve, or approve on /dac",
    )


def check_embedding_provenance(**_kw) -> Assertion:
    """existing C4: spec declares a model+dim; does the sidecar agree?"""
    try:
        from arail import pkb_index
    except Exception as exc:  # noqa: BLE001
        return Assertion("embedding_provenance", "info", True, False,
                         f"unavailable: {exc}", "")
    codes = pkb_index.degraded_codes()
    bad = set(codes) & {"dimension", "provenance"}
    return Assertion(
        "embedding_provenance", "required", True, not bad,
        detail="; ".join(codes.get(c, c) for c in bad) if bad else "",
        action="./arailctl pkb reembed" if bad else "",
    )


def check_instance_registry(*, repo_root, **_kw) -> Assertion:
    """the 2-of-6 miss: every on-disk instance dir should have a registry
    record (a purely informational finding — an unregistered instance
    still works, it just wasn't reached by any --all-instances walk)."""
    from arail.data_dirs import resolve_data_dirs
    rows = resolve_data_dirs(repo_root)
    ondisk_only = [r for r in rows if r.origin == "ondisk"]
    return Assertion(
        "instance_registry", "info", True, not ondisk_only,
        detail=("" if not ondisk_only else
                f"{len(ondisk_only)} instance(s) on disk with no registry "
                f"record: {', '.join(r.slug for r in ondisk_only)}"),
        action="" if not ondisk_only else "re-register via ./arailctl install",
    )


register("relational_store", check_relational_store)
register("vector_backend", check_vector_backend)
register("kb_gate", check_kb_gate)
register("embedding_provenance", check_embedding_provenance)
register("instance_registry", check_instance_registry)


def evaluate_all(**kwargs) -> List[Assertion]:
    """Run every registered assertion. A single mechanism's check failing
    with an exception becomes an info-tier finding naming the exception,
    never a crash of the whole checkup."""
    out = []
    for key in registered_keys():
        fn = _REGISTRY[key]
        try:
            out.append(fn(**kwargs))
        except Exception as exc:  # noqa: BLE001
            out.append(Assertion(key, "info", True, False,
                                 f"check raised {type(exc).__name__}: {exc}", ""))
    return out


def to_json(assertions: List[Assertion]) -> dict:
    return {
        "schema": "arail.provisioning/v1",
        "assertions": [
            {
                "key": a.key, "tier": a.tier, "declared": a.declared,
                "instantiated": a.instantiated, "finding": a.finding,
                "detail": a.detail, "action": a.action,
            }
            for a in assertions
        ],
    }
