"""Debt Advisor — reads the mounted debt-finance World and narrates it.

    An agent is a loop that notices things and speaks up.

Debt Advisor never reads or writes anything under ``lab/pkb/agents/``. Its
only output is ``lab/data/user-import/debt-finance/findings/debt_advisor.md``
(never ``decisions.md``, never anywhere under ``lab/pkb/`` — see
``sprints/2026-07-26-world-of-debt-finance/ARCHITECTURE.md`` §0.1/§6).

The mental model, mirroring ``_builtin_buddy.py``'s shape:

    1. Host      — the only seam to the outside world (DebtAdvisorHost)
    2. Facts     — deterministic extraction from the mounted World's terms.json
    3. Guardrail — arail.agents.debt_finance_compliance.check_guardrail
    4. Loop      — the heartbeat (DebtAdvisorAgent._run)
    5. Memory    — state.json (hash + timestamp + count ONLY, never a figure)

Numeric/institutional integrity (ARCHITECTURE.md §7.5): every institution
name and source URL in the output is inserted verbatim from a term's
structured field. The model, when consulted at all, narrates the
surrounding prose — it never supplies the fact itself. v1 keeps this
property trivially airtight by not attempting to extract a rate from an
approved scouting finding's raw excerpt at all (scouting findings are
unstructured fetched text, not a structured rate record — see BUILD_LOG.md
Phase C for why): Debt Advisor cites an approved finding only by its World/
watch/feed/date metadata, never a number pulled out of its excerpt.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from arail.agents.debt_finance_compliance import (
    check_guardrail,
    find_mounted_bundle_dir,
    is_verification_fresh,
    read_disclaimer,
)

WORLD_SLUG = "debt-finance"
AGENT_ID = "debt_advisor"


# ══════════════════════════════════════════════════════════════════════
#  0. HOST — the only seam between Debt Advisor and its environment
# ══════════════════════════════════════════════════════════════════════

@runtime_checkable
class DebtAdvisorHost(Protocol):
    def emit(self, source: str, message: str, level: str = "info",
              data: Optional[Dict[str, Any]] = None) -> None: ...

    def get_pkb_root(self) -> Optional[Path]: ...

    def get_data_dir(self) -> Optional[Path]: ...

    def llm_complete(self, prompt: str, max_tokens: int = 120,
                      temperature: float = 0.4) -> str: ...


class ArailHost:
    def emit(self, source: str, message: str, level: str = "info",
              data: Optional[Dict[str, Any]] = None) -> None:
        from arail.activity import activity_log
        activity_log.emit(source, message, level, data)

    def get_pkb_root(self) -> Optional[Path]:
        try:
            from arail.pkb import _pkb_root
            return _pkb_root()
        except Exception:
            return None

    def get_data_dir(self) -> Optional[Path]:
        try:
            from arail.config import DATA_DIR
            return Path(DATA_DIR)
        except Exception:
            return None

    def llm_complete(self, prompt: str, max_tokens: int = 120,
                      temperature: float = 0.4) -> str:
        try:
            from arail.agents import deep_policy
            text = deep_policy.complete_preferring_deep(
                prompt, foreground=False,
                max_tokens=max_tokens, temperature=temperature,
            )
            return text or ""
        except Exception:
            return ""


_host: DebtAdvisorHost = ArailHost()


def _state_file() -> Path:
    pkb = _host.get_pkb_root()
    if pkb is None:
        return Path.home() / ".debt_advisor" / "state.json"
    return pkb / "agents" / AGENT_ID / "state.json"


def _findings_file() -> Path:
    data_dir = _host.get_data_dir()
    root = data_dir if data_dir is not None else Path("lab/data")
    return root / "user-import" / WORLD_SLUG / "findings" / "debt_advisor.md"


# ══════════════════════════════════════════════════════════════════════
#  2. FACTS — deterministic extraction from the mounted World
# ══════════════════════════════════════════════════════════════════════

@dataclass
class VettedInstitution:
    name: str
    institution_type: str
    verification_source: str
    verified_as_of: str


def _load_terms(bundle_dir: Path) -> List[Dict[str, Any]]:
    try:
        doc = json.loads((bundle_dir / "terms.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(doc, dict):
        return list(doc.get("terms") or [])
    if isinstance(doc, list):
        return doc
    return []


def _vetted_institutions(terms: List[Dict[str, Any]]) -> List[VettedInstitution]:
    """Specific, named, verified institutions Debt Advisor may pair with
    "credit union"/"nonprofit" language (ARCHITECTURE.md §3.3/§4.3).

    ``category == "institutions"`` alone is not enough: that category also
    holds generic glossary/concept terms (e.g. "Credit Union", "Credit
    Counseling Agency") that explain what a kind of institution IS, not a
    claim about any specific real-world entity. Only entries that carry an
    ``institution_type`` field are actual named, verified institutions —
    that field is the distinguishing marker terms.json's authoring
    convention requires before a term counts as "vetted" for guardrail or
    substitution purposes (see terms.json's PenFed Credit Union / GreenPath
    Financial Wellness entries for the shape).

    A fourth condition, ``verified_as_of``, is also required: a valid ISO
    date within the staleness threshold (``is_verification_fresh``). A
    sealed bundle cannot notice when a real institution's charter or
    membership status lapses, so an institution missing this field, or
    whose verification has gone stale, is simply not vetted — the
    mechanism degrades closed rather than asserting an unqualified fact
    forever.
    """
    out = []
    for t in terms:
        institution_type = t.get("institution_type")
        verified_as_of = str(t.get("verified_as_of") or "")
        if (t.get("category") == "institutions" and institution_type
                and t.get("verification_source")
                and is_verification_fresh(verified_as_of)):
            out.append(VettedInstitution(
                name=str(t.get("term") or t.get("slug") or ""),
                institution_type=str(institution_type),
                verification_source=str(t.get("verification_source")),
                verified_as_of=verified_as_of,
            ))
    return out


def _terms_content_hash(bundle_dir: Path) -> str:
    try:
        raw = (bundle_dir / "terms.json").read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(raw).hexdigest()


def _approved_finding_count(pkb_root: Optional[Path]) -> int:
    """Count of approved scout findings for this World — used only for the
    no-op fingerprint, never for content. See _write_findings for how an
    approved finding is cited (metadata only, never a parsed figure)."""
    if pkb_root is None:
        return 0
    try:
        from arail import compiled_kb
        approved = compiled_kb.approved_paths(pkb_root)
    except Exception:
        return 0
    prefix = f"sources/scout/{WORLD_SLUG}-"
    return sum(1 for p in approved if p.startswith(prefix))


def _approved_findings(pkb_root: Optional[Path]) -> List[Dict[str, str]]:
    """Metadata (World/watch/feed/date) for each approved finding — never
    the excerpt content, and never a number parsed out of it."""
    if pkb_root is None:
        return []
    try:
        from arail import compiled_kb
        approved = compiled_kb.approved_paths(pkb_root)
    except Exception:
        return []
    out: List[Dict[str, str]] = []
    prefix = f"sources/scout/{WORLD_SLUG}-"
    for rel in sorted(approved):
        if not rel.startswith(prefix):
            continue
        path = pkb_root / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        meta: Dict[str, str] = {"path": rel}
        for line in text.splitlines():
            for key in ("Watch", "Feed", "Checked"):
                if line.startswith(f"- {key}:"):
                    meta[key.lower()] = line.split(":", 1)[1].strip()
        out.append(meta)
    return out


# ══════════════════════════════════════════════════════════════════════
#  3. WRITE PATH — guardrail, disclaimer, findings file
# ══════════════════════════════════════════════════════════════════════

_DIGIT_RE = re.compile(r"\d")


def _framing_prose(vetted: List[VettedInstitution],
                    findings: List[Dict[str, str]]) -> str:
    """Optional model-generated framing sentence around the code-inserted
    facts below. Falls back to a fixed, deterministic sentence if the model
    is unavailable — the model is never the source of a fact, only of the
    surrounding tone, so this fallback changes nothing material.

    Also rejects a model sentence containing a digit or a vetted
    institution's name — the prompt asks the model not to emit either, but
    nothing enforced that until now (REVIEW.md [ASK]); this is the last
    live path by which a model-generated number or name could reach a
    findings file."""
    prompt = (
        "Write one short, plain, non-evaluative sentence introducing an "
        "educational summary of debt-payoff and consolidation terminology. "
        "Do not name any institution, rate, or number. Do not say 'best' "
        "or give advice."
    )
    text = _host.llm_complete(prompt, max_tokens=60).strip()
    lowered = text.lower()
    if (not text or check_guardrail(text, frozenset()).ok is False
            or _DIGIT_RE.search(text)
            or any(v.name.lower() in lowered for v in vetted)):
        return "Educational summary of this World's debt-finance terms and any approved findings."
    return text


def _build_output(bundle_dir: Path, terms: List[Dict[str, Any]],
                   findings: List[Dict[str, str]]) -> str:
    vetted = _vetted_institutions(terms)
    vetted_names = frozenset(v.name.lower() for v in vetted)

    lines: List[str] = []
    lines.append("# Debt Advisor — Findings\n")
    lines.append(_framing_prose(vetted, findings) + "\n")

    lines.append("## Institutions whose character claims this World verified\n")
    # Code-inserted, never model-generated (REVIEW.md addendum, condition
    # (a)): a short named-institution list under a "vetted institutions"
    # heading reads as a shortlist regardless of surrounding prose. This
    # roster exists to demonstrate what verifying an institutional-
    # character claim looks like, not to recommend or exhaustively list
    # institutions.
    lines.append(
        "_This list is not exhaustive and is not a recommendation. It "
        "exists to show what verification of an institutional-character "
        "claim looks like, against a source other than the institution's "
        "own marketing._\n"
    )
    if vetted:
        for v in vetted:
            # Every name, character label, verification-source URL, and
            # verified-as-of date below is inserted verbatim from the
            # term's own structured fields — never a hardcoded string,
            # never generated by the model. Each institution's actual
            # institution_type is what gets printed, so a credit-counseling
            # agency is never mislabeled as a credit union (BLOCK-2). The
            # verified-as-of date is rendered next to the citation so
            # staleness is visible on the document's face, not just
            # internal bookkeeping (REVIEW.md addendum, condition (b)).
            character = v.institution_type.replace("-", " ")
            lines.append(
                f"- **{v.name}** ({character}, verification source: "
                f"{v.verification_source}, verified as of "
                f"{v.verified_as_of})"
            )
    else:
        lines.append("- No vetted institutions in the mounted World's terms.")
    lines.append("")

    lines.append("## Approved scouting findings (public sources only)\n")
    if findings:
        for f in findings:
            # ``feed`` and ``path`` are the externally-authored (RSS
            # source's own title / mounted-World-relative path) text this
            # agent quotes back verbatim — not this agent's own
            # characterization of anything. Marked "(quoted verbatim)" for
            # the same reason a vetted institution's name is marked above:
            # a reader must be able to tell this is a third party's own
            # wording, not Debt Advisor's. Also passed to ``check_guardrail``
            # as ``quoted_spans`` below (REVIEW.md re-review addendum 3,
            # BLOCK-6), so a feed title like "Best Balance Transfer Cards -
            # Bankrate" cannot suppress the whole document.
            lines.append(
                f"- Found via {f.get('feed', '?')} (quoted verbatim), "
                f"checked {f.get('checked', '?')} — see "
                f"`{f.get('path', '?')}` (quoted verbatim) for the "
                "reviewed excerpt. No institutional-character label is "
                "attached unless the source is also a vetted institution "
                "above."
            )
    else:
        lines.append("- No approved scouting findings yet.")
    lines.append("")

    quoted_spans = frozenset(
        str(v) for f in findings for v in (f.get("feed"), f.get("path")) if v
    )

    body = "\n".join(lines)
    # Debt Advisor's content is entirely World-sourced — the operator-names
    # exemption never applies here (REVIEW.md addendum, question 2, item 3).
    guard = check_guardrail(
        body, vetted_names, operator_names=frozenset(), quoted_spans=quoted_spans
    )
    if not guard.ok:
        raise _GuardrailBlocked(guard.reason)
    return body


class _GuardrailBlocked(Exception):
    pass


def _write_findings(text: str, disclaimer: str) -> None:
    path = _findings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n\n---\n\n" + disclaimer, encoding="utf-8")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass


# ══════════════════════════════════════════════════════════════════════
#  4/5. LOOP + MEMORY
# ══════════════════════════════════════════════════════════════════════

class DebtAdvisorAgent:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._status = "idle"
        self._last_terms_hash = ""
        self._last_finding_count = -1
        self._last_run_at: float = 0.0

    @property
    def status(self) -> str:
        return self._status

    def _load_state(self) -> None:
        path = _state_file()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
        except Exception:
            return
        # state.json may only ever hold a hash, a timestamp, and a count —
        # never a raw balance/APR/institution name (ARCHITECTURE.md §7 new
        # constraint; enforced by construction, this is all we ever store).
        self._last_terms_hash = str(data.get("terms_hash") or "")
        self._last_finding_count = int(data.get("approved_finding_count", -1))
        self._last_run_at = float(data.get("last_run_at") or 0.0)

    def _save_state(self) -> None:
        path = _state_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "terms_hash": self._last_terms_hash,
                "approved_finding_count": self._last_finding_count,
                "last_run_at": self._last_run_at,
            }, indent=2))
        except OSError:
            pass

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._load_state()
        self._status = "running"
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._status = "idle"

    async def _run(self) -> None:
        interval = max(60, int(os.getenv("LAB_DEBT_ADVISOR_INTERVAL_SEC", "86400")))
        try:
            while True:
                await asyncio.sleep(interval)
                self.tick()
        except asyncio.CancelledError:
            return

    def tick(self) -> None:
        """One tick: no-op if nothing changed, else compute + guardrail +
        disclaimer + write. Never crashes; always logs a path-only pointer
        or a non-identifying warning, never a figure."""
        bundle_dir = find_mounted_bundle_dir()
        if bundle_dir is None:
            return  # No World mounted — nothing to do, not an error.

        terms = _load_terms(bundle_dir)
        terms_hash = _terms_content_hash(bundle_dir)
        pkb_root = _host.get_pkb_root()
        finding_count = _approved_finding_count(pkb_root)

        if terms_hash == self._last_terms_hash and finding_count == self._last_finding_count:
            return  # True no-op: no LLM call, no write, no activity event.

        disclaimer = read_disclaimer(bundle_dir)
        if disclaimer is None:
            _host.emit(
                AGENT_ID,
                "Debt Advisor: compliance/DISCLAIMER.md missing or altered — "
                "refusing to write findings until restored.",
                "warn",
            )
            return

        findings = _approved_findings(pkb_root)
        try:
            body = _build_output(bundle_dir, terms, findings)
        except _GuardrailBlocked as exc:
            reason = exc.args[0] if exc.args else ""
            # REVIEW.md addendum 2 [ASK-B]: name the reason rather than a
            # bare "see logs" pointer. Unlike Consolidation Analyzer, this
            # path is entirely World content (terms.json / scouting
            # findings) — nothing the operator typed can fix it, so point at
            # the mounted World instead.
            _host.emit(
                AGENT_ID,
                "Debt Advisor: generated output failed the language-safety "
                f"check ({reason}) and was not written. This indicates the "
                "mounted World's terms.json or an approved scouting finding "
                "names an institution with institutional-character language "
                "that isn't in this World's vetted set — check the World's "
                "content, not your own data.",
                "warn",
                data={"reason": reason},
            )
            return

        _write_findings(body, disclaimer)
        self._last_terms_hash = terms_hash
        self._last_finding_count = finding_count
        self._last_run_at = time.time()
        self._save_state()

        _host.emit(
            AGENT_ID,
            "Debt Advisor produced a new finding — see "
            f"{_findings_file()}",
            "info",
        )


debt_advisor = DebtAdvisorAgent()
