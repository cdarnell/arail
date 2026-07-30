"""QA round-3: fresh end-to-end re-verification of the ORIGINAL data-isolation
BLOCK (ARCHITECTURE.md §0.1 / §6) after 8 rounds of unrelated guardrail work.

Nothing under lab/pkb/ may ever contain a real balance, APR, or institution
name; both agents' state.json must contain zero numeric/institution content.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

_DISCLAIMER = "# Disclaimer\n\nThese agents are not licensed financial advisors.\n"

# Distinctive markers that must never appear under lab/pkb/.
BAL = "873241.57"
APR = "27.31"
INST = "ZzyzxMutualHoldings"
PROD = "QuuxPlatinumTransfer"
SRC = "https://zzyzx.example/quux"

_TERMS = {"version": 1, "terms": [{
    "slug": "penfed-credit-union", "term": "PenFed Credit Union",
    "category": "institutions", "institution_type": "credit-union",
    "short": "x", "definition": "x", "related": [],
    "source": "https://www.penfed.org/x",
    "verification_source": "https://mapping.ncua.gov/x",
    "verified_as_of": "2026-07-27",
}]}


class FakeHost:
    def __init__(self, pkb_root: Path, data_dir: Path):
        self._pkb_root, self._data_dir = pkb_root, data_dir
        self.events: List[Dict[str, Any]] = []

    def emit(self, source, message, level="info", data=None):
        self.events.append({"source": source, "message": message,
                            "level": level, "data": data})

    def get_pkb_root(self) -> Optional[Path]:
        return self._pkb_root

    def get_data_dir(self) -> Optional[Path]:
        return self._data_dir

    def llm_complete(self, prompt, max_tokens=120, temperature=0.4) -> str:
        return ""


@pytest.fixture()
def env(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    (bundle / "compliance").mkdir(parents=True)
    (bundle / "compliance" / "DISCLAIMER.md").write_text(_DISCLAIMER)
    (bundle / "terms.json").write_text(json.dumps(_TERMS))

    pkb = tmp_path / "pkb"
    (pkb / "agents").mkdir(parents=True)
    data = tmp_path / "data"
    data.mkdir()
    host = FakeHost(pkb, data)

    from arail.agents import _builtin_consolidation_analyzer as ca
    from arail.agents import _builtin_debt_advisor as da
    for mod in (ca, da):
        monkeypatch.setattr(mod, "_host", host)
        monkeypatch.setattr(mod, "find_mounted_bundle_dir", lambda: bundle)

    staged = data / "user-import" / "debt-finance"
    staged.mkdir(parents=True)
    (staged / "balances.json").write_text(json.dumps({
        "debts": [{"institution": INST, "balance": float(BAL),
                   "apr": float(APR), "min_payment": 100.0}],
        "candidate_scenarios": [{
            "institution": INST, "product": PROD, "rate": 9.99,
            "fee_pct": 3.0, "source": SRC, "as_of": "2026-07-01"}],
    }))
    return {"ca": ca, "da": da, "pkb": pkb, "data": data, "host": host,
            "bundle": bundle}


def _walk_pkb(pkb: Path):
    out = {}
    for p in pkb.rglob("*"):
        if p.is_file():
            try:
                out[str(p.relative_to(pkb))] = p.read_text(
                    encoding="utf-8", errors="replace")
            except OSError:
                pass
    return out


def test_no_user_figure_or_institution_reaches_the_pkb_tree(env):
    env["ca"].ConsolidationAnalyzerAgent().tick()
    env["da"].DebtAdvisorAgent().tick()

    files = _walk_pkb(env["pkb"])
    assert files, "expected at least state.json to be written under lab/pkb/"
    print("PKB files written:", sorted(files))

    for rel, text in files.items():
        for marker in (BAL, APR, INST, PROD, SRC, "873241", "27.31"):
            assert marker not in text, (
                f"user data {marker!r} leaked into lab/pkb/{rel}:\n{text}")


def test_state_json_for_both_agents_holds_only_a_hash_and_a_timestamp(env):
    env["ca"].ConsolidationAnalyzerAgent().tick()
    env["da"].DebtAdvisorAgent().tick()

    found = list(env["pkb"].rglob("state.json"))
    print("state.json files:", [str(p) for p in found])
    for p in found:
        data = json.loads(p.read_text())
        assert set(data) <= {"input_hash", "last_run_at", "terms_hash",
                             "approved_finding_count"}, \
            f"unexpected keys in {p}: {data}"
        for k, v in data.items():
            if k == "last_run_at":
                assert isinstance(v, float)
                continue
            # Every other value must be an opaque hex digest — never a raw
            # count, balance, APR, or name.
            assert isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}|", v), \
                f"{p}: {k}={v!r} is not an opaque hex digest"


def test_findings_land_outside_the_pkb_tree_and_do_contain_the_figures(env):
    """Positive control: the figures ARE written — to lab/data/, not lab/pkb/.
    Without this, the isolation test above could pass trivially."""
    env["ca"].ConsolidationAnalyzerAgent().tick()
    f = env["data"] / "user-import" / "debt-finance" / "findings" / \
        "consolidation_analyzer.md"
    assert f.exists(), "analyzer wrote no findings file at all"
    body = f.read_text()
    assert INST in body and PROD in body
    assert env["pkb"] not in f.parents


def test_activity_events_never_carry_a_figure_or_institution_name(env):
    env["ca"].ConsolidationAnalyzerAgent().tick()
    env["da"].DebtAdvisorAgent().tick()
    for ev in env["host"].events:
        blob = json.dumps(ev)
        print("EVENT:", blob)
        for marker in (BAL, APR, INST, PROD, SRC):
            assert marker not in blob, f"{marker!r} leaked into activity: {blob}"
