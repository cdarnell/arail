"""Consolidation Analyzer — pure arithmetic over the operator's own balances.

    An agent is a loop that notices things and speaks up.

Reads ``lab/data/user-import/debt-finance/balances.json`` (never
``lab/pkb/``) and computes, deterministically in code: blended APR, monthly
interest cost, and break-even timelines for candidate balance-transfer /
consolidation-loan scenarios. Every number in the output is inserted
verbatim from a code computation over the operator's own staged input — the
model narrates around the numbers, it never retypes or estimates them
(ARCHITECTURE.md §5.2/§7.5).

    1. Host      — the only seam to the outside world
    2. Arithmetic — blended_apr / monthly_interest_cost / breakeven_months
       (pure functions, independently unit-testable, no I/O)
    3. Input     — balances.json schema + the three specified parse-failure
       behaviors (§6.1: absent -> no-op; valid -> normal tick; malformed ->
       one non-specific warning, zero content echo, no crash)
    4. Guardrail + disclaimer + write — same shared module as Debt Advisor
    5. Loop      — the heartbeat
    6. Memory    — state.json (hash + timestamp + count ONLY)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
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
AGENT_ID = "consolidation_analyzer"


# ══════════════════════════════════════════════════════════════════════
#  1. HOST
# ══════════════════════════════════════════════════════════════════════

@runtime_checkable
class ConsolidationAnalyzerHost(Protocol):
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


_host: ConsolidationAnalyzerHost = ArailHost()


def _state_file() -> Path:
    pkb = _host.get_pkb_root()
    if pkb is None:
        return Path.home() / ".consolidation_analyzer" / "state.json"
    return pkb / "agents" / AGENT_ID / "state.json"


def _import_dir() -> Path:
    data_dir = _host.get_data_dir()
    root = data_dir if data_dir is not None else Path("lab/data")
    return root / "user-import" / WORLD_SLUG


def _balances_file() -> Path:
    return _import_dir() / "balances.json"


def _findings_file() -> Path:
    return _import_dir() / "findings" / "consolidation_analyzer.md"


# ══════════════════════════════════════════════════════════════════════
#  2. ARITHMETIC — pure, independently unit-testable, zero I/O
# ══════════════════════════════════════════════════════════════════════

def blended_apr(debts: List[Dict[str, Any]]) -> Optional[float]:
    """Balance-weighted average APR across debts. None if total balance is 0."""
    total_balance = sum(float(d.get("balance", 0.0)) for d in debts)
    if total_balance <= 0:
        return None
    weighted = sum(float(d.get("balance", 0.0)) * float(d.get("apr", 0.0))
                   for d in debts)
    return weighted / total_balance


def monthly_interest_cost(balance: float, apr: float) -> float:
    """Simple monthly interest on a balance at a given annual APR (percent)."""
    return balance * (apr / 100.0) / 12.0


def breakeven_months(fee_amount: float, monthly_savings: float) -> Optional[int]:
    """Months of savings needed to offset a one-time fee.

    None if there is no positive monthly saving (the scenario never breaks
    even) or the fee is non-positive (breaks even immediately, reported as 0).
    """
    if fee_amount <= 0:
        return 0
    if monthly_savings <= 0:
        return None
    return math.ceil(fee_amount / monthly_savings)


@dataclass
class ScenarioResult:
    institution: str
    product: str
    rate: float
    fee_pct: float
    source: str
    as_of: str
    fee_amount: float
    new_monthly_interest: float
    monthly_savings: float
    breakeven: Optional[int]


def _compute_scenarios(debts: List[Dict[str, Any]],
                        scenarios: List[Dict[str, Any]]) -> List[ScenarioResult]:
    total_balance = sum(float(d.get("balance", 0.0)) for d in debts)
    current_monthly = sum(
        monthly_interest_cost(float(d.get("balance", 0.0)), float(d.get("apr", 0.0)))
        for d in debts
    )
    out: List[ScenarioResult] = []
    for s in scenarios:
        rate = float(s.get("rate", 0.0))
        fee_pct = float(s.get("fee_pct", 0.0))
        fee_amount = total_balance * (fee_pct / 100.0)
        new_monthly = monthly_interest_cost(total_balance, rate)
        savings = current_monthly - new_monthly
        out.append(ScenarioResult(
            institution=str(s.get("institution", "")),
            product=str(s.get("product", "")),
            rate=rate,
            fee_pct=fee_pct,
            source=str(s.get("source", "")),
            as_of=str(s.get("as_of", "")),
            fee_amount=fee_amount,
            new_monthly_interest=new_monthly,
            monthly_savings=savings,
            breakeven=breakeven_months(fee_amount, savings),
        ))
    return out


# ══════════════════════════════════════════════════════════════════════
#  3. INPUT — schema + parse-failure behavior (ARCHITECTURE.md §6.1)
# ══════════════════════════════════════════════════════════════════════

class _MalformedInput(Exception):
    pass


def _load_balances() -> Optional[Dict[str, Any]]:
    """Returns None if the file is absent (a normal no-op, not an error).
    Raises _MalformedInput if present but unparsable / schema-invalid —
    callers must not echo any content from the exception."""
    path = _balances_file()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _MalformedInput() from exc
    if not isinstance(data, dict):
        raise _MalformedInput()
    debts = data.get("debts")
    if debts is not None and not isinstance(debts, list):
        raise _MalformedInput()
    scenarios = data.get("candidate_scenarios")
    if scenarios is not None and not isinstance(scenarios, list):
        raise _MalformedInput()
    for d in (debts or []):
        if not isinstance(d, dict):
            raise _MalformedInput()
    for s in (scenarios or []):
        if not isinstance(s, dict):
            raise _MalformedInput()
    return data


def _content_hash() -> str:
    path = _balances_file()
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(raw).hexdigest()


# ══════════════════════════════════════════════════════════════════════
#  4. WRITE PATH
# ══════════════════════════════════════════════════════════════════════

_DIGIT_RE = re.compile(r"\d")


def _framing_prose() -> str:
    """See ``_builtin_debt_advisor._framing_prose`` — same digit-rejection
    fix for the same [ASK] (REVIEW.md): a model-generated sentence
    containing a digit is rejected in favor of the deterministic fallback,
    since the prompt asking the model not to emit a number was previously
    unenforced."""
    prompt = (
        "Write one short, plain, non-evaluative sentence introducing a "
        "computed debt-consolidation comparison. Do not name any "
        "institution, rate, or number. Do not say 'best' or give advice."
    )
    text = _host.llm_complete(prompt, max_tokens=60).strip()
    if not text or not check_guardrail(text, frozenset()).ok or _DIGIT_RE.search(text):
        return "Computed comparison of your staged balances against staged candidate scenarios."
    return text


def _operator_institution_names(debts: List[Dict[str, Any]]) -> frozenset[str]:
    """Institution names sourced ONLY from the operator's own parsed
    ``balances.json`` ``debts`` — their existing card/loan issuers, never
    from scouting findings, never from the World's terms, and never from
    ``candidate_scenarios`` (REVIEW.md addendum, question 2).

    A candidate scenario's institution is always a claim about who is
    *offering* a comparison product; it must still be vetted or blocked
    like any other institutional-character claim. This set exists purely
    so the analyzer can recognize when a scenario's institution happens to
    match one of the operator's own existing debts — i.e. the operator is
    comparing an offer from their own current issuer — and, only then, mark
    that echo as a quotation of the operator's own data rather than an
    agent-verified claim. An unvetted institution that does NOT appear in
    the operator's own debts gets no exemption at all.
    """
    return frozenset(
        str(d.get("institution") or "").lower()
        for d in debts
        if d.get("institution")
    )


def _build_output(debts: List[Dict[str, Any]], scenarios: List[Dict[str, Any]],
                   vetted_names: frozenset[str],
                   operator_names: frozenset[str]) -> str:
    apr = blended_apr(debts)
    results = _compute_scenarios(debts, scenarios)

    lines: List[str] = ["# Consolidation Analyzer — Findings\n", _framing_prose() + "\n"]

    lines.append("## Current position\n")
    lines.append(f"- Debts entered: {len(debts)}")
    if apr is not None:
        # apr is a code-computed float — inserted verbatim, never retyped.
        lines.append(f"- Current blended APR: {apr:.2f}%")
    else:
        lines.append("- Current blended APR: not computable (zero total balance)")
    lines.append("")

    lines.append("## Candidate scenarios\n")
    if results:
        for r in results:
            breakeven_text = (
                f"{r.breakeven} months" if r.breakeven is not None
                else "does not break even at this rate/fee"
            )
            # "(as you entered it)" is code-inserted, never model-inserted,
            # and appears ONLY when this scenario's institution matches one
            # of the operator's own existing debts (operator_names) — i.e.
            # the operator is comparing an offer from their own current
            # issuer, and the product is quoting their own data back to
            # them rather than asserting anything new. A scenario naming
            # some other, unvetted institution gets no marker and is still
            # subject to the ordinary guardrail check below (REVIEW.md
            # addendum, question 2, items 2/5/6).
            marker = (
                " (as you entered it)"
                if r.institution.lower() in operator_names else ""
            )
            lines.append(
                f"- **{r.institution}**{marker} — {r.product}, "
                f"rate {r.rate:.2f}%, "
                f"fee {r.fee_pct:.2f}% (${r.fee_amount:.2f}), "
                f"monthly savings ${r.monthly_savings:.2f}, "
                f"breakeven {breakeven_text}. "
                f"Source: {r.source}, as of {r.as_of}."
            )
    else:
        lines.append("- No candidate scenarios staged.")
    lines.append("")

    body = "\n".join(lines)
    guard = check_guardrail(body, vetted_names, operator_names=operator_names)
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


def _vetted_institution_names(bundle_dir: Path) -> frozenset[str]:
    """Specific, named, verified institutions — see
    ``_builtin_debt_advisor._vetted_institutions`` for why ``category ==
    "institutions"`` alone is not enough: that category also holds generic
    glossary/concept terms. Only entries carrying an ``institution_type``
    field (and a third-party ``verification_source``) count as vetted.

    Also requires a fresh ``verified_as_of`` date (``is_verification_fresh``)
    — an institution missing this field, or whose verification has gone
    stale, degrades out of the vetted set rather than being trusted
    forever. See ``_builtin_debt_advisor._vetted_institutions`` for the
    identical rule."""
    try:
        doc = json.loads((bundle_dir / "terms.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    terms = doc.get("terms") if isinstance(doc, dict) else doc
    names = set()
    for t in terms or []:
        if (t.get("category") == "institutions" and t.get("institution_type")
                and t.get("verification_source")
                and is_verification_fresh(str(t.get("verified_as_of") or ""))):
            names.add(str(t.get("term") or t.get("slug") or "").lower())
    return frozenset(names)


# ══════════════════════════════════════════════════════════════════════
#  5/6. LOOP + MEMORY
# ══════════════════════════════════════════════════════════════════════

class ConsolidationAnalyzerAgent:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._status = "idle"
        self._last_input_hash = ""
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
        # never a raw balance/APR/institution name.
        self._last_input_hash = str(data.get("input_hash") or "")
        self._last_run_at = float(data.get("last_run_at") or 0.0)

    def _save_state(self) -> None:
        path = _state_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "input_hash": self._last_input_hash,
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
        interval = max(60, int(os.getenv("LAB_CONSOLIDATION_ANALYZER_INTERVAL_SEC", "86400")))
        try:
            while True:
                await asyncio.sleep(interval)
                self.tick()
        except asyncio.CancelledError:
            return

    def tick(self) -> None:
        current_hash = _content_hash()
        if not current_hash:
            return  # File absent — normal no-op, not an error.

        try:
            data = _load_balances()
        except _MalformedInput:
            _host.emit(
                AGENT_ID,
                "Consolidation Analyzer: could not read "
                f"{_balances_file()} — check its format.",
                "warn",
            )
            return
        if data is None:
            return

        if current_hash == self._last_input_hash:
            return  # True no-op.

        bundle_dir = find_mounted_bundle_dir()
        disclaimer = read_disclaimer(bundle_dir) if bundle_dir else None
        if disclaimer is None:
            _host.emit(
                AGENT_ID,
                "Consolidation Analyzer: compliance/DISCLAIMER.md missing "
                "or altered — refusing to write findings until restored.",
                "warn",
            )
            return

        debts = data.get("debts") or []
        scenarios = data.get("candidate_scenarios") or []
        vetted = _vetted_institution_names(bundle_dir) if bundle_dir else frozenset()
        operator_names = _operator_institution_names(debts)

        try:
            body = _build_output(debts, scenarios, vetted, operator_names)
        except _GuardrailBlocked as exc:
            _host.emit(
                AGENT_ID,
                "Consolidation Analyzer: generated output failed the "
                "language-safety check and was not written — see logs.",
                "warn",
                data={"reason": exc.args[0] if exc.args else ""},
            )
            return

        _write_findings(body, disclaimer)
        self._last_input_hash = current_hash
        self._last_run_at = time.time()
        self._save_state()

        _host.emit(
            AGENT_ID,
            "Consolidation Analyzer produced a new finding — see "
            f"{_findings_file()}",
            "info",
        )


consolidation_analyzer = ConsolidationAnalyzerAgent()
