"""Tests for the Debt Advisor / Consolidation Analyzer PKB shims and
loader._SHIPPED membership — closes the git-tracking gap ARCHITECTURE.md's
verification found (lab/pkb/agents/ is entirely git-ignored except sre/).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _shim_module(shim_path: Path, unique_name: str):
    spec = importlib.util.spec_from_file_location(unique_name, str(shim_path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(unique_name, None)
    return module


class TestLoaderShippedSet:
    def test_both_agents_are_shipped(self):
        from arail.agents.loader import _SHIPPED
        assert "debt_advisor" in _SHIPPED
        assert "consolidation_analyzer" in _SHIPPED


class TestDebtAdvisorShim:
    def test_agent_folder_created(self, tmp_path):
        from arail.agents.builtin_seed import ensure_debt_advisor_folder
        ensure_debt_advisor_folder(pkb_root=tmp_path)
        assert (tmp_path / "agents" / "debt_advisor" / "debt_advisor.py").exists()
        assert (tmp_path / "agents" / "debt_advisor" / "AGENT.md").exists()

    def test_shim_is_thin(self, tmp_path):
        from arail.agents.builtin_seed import ensure_debt_advisor_folder
        ensure_debt_advisor_folder(pkb_root=tmp_path)
        py = tmp_path / "agents" / "debt_advisor" / "debt_advisor.py"
        assert len(py.read_text().splitlines()) < 40

    def test_shim_singleton_identity(self, tmp_path):
        from arail.agents.builtin_seed import ensure_debt_advisor_folder
        ensure_debt_advisor_folder(pkb_root=tmp_path)
        py = tmp_path / "agents" / "debt_advisor" / "debt_advisor.py"
        module = _shim_module(py, "_test_debt_advisor_shim")
        from arail.agents._builtin_debt_advisor import debt_advisor as canonical
        assert module.debt_advisor is canonical

    def test_second_call_does_not_overwrite(self, tmp_path):
        from arail.agents.builtin_seed import ensure_debt_advisor_folder
        ensure_debt_advisor_folder(pkb_root=tmp_path)
        py = tmp_path / "agents" / "debt_advisor" / "debt_advisor.py"
        before = py.read_text()
        ensure_debt_advisor_folder(pkb_root=tmp_path)
        assert py.read_text() == before

    def test_forked_file_not_overwritten(self, tmp_path):
        from arail.agents.builtin_seed import ensure_debt_advisor_folder
        agent_dir = tmp_path / "agents" / "debt_advisor"
        agent_dir.mkdir(parents=True)
        forked = "# forked\ndebt_advisor = None\n"
        (agent_dir / "debt_advisor.py").write_text(forked)
        ensure_debt_advisor_folder(pkb_root=tmp_path)
        assert (agent_dir / "debt_advisor.py").read_text() == forked

    def test_loader_discovers_and_loads(self, tmp_path, monkeypatch):
        # _seed_if_shipped() calls ensure_debt_advisor_folder() with no
        # pkb_root argument (matching every other shipped agent), so the
        # fixture must patch the default resolver rather than pass
        # pkb_root= to load_one — otherwise the seed lands in the real
        # default lab/pkb while the loader looks under tmp_path.
        import arail.pkb
        monkeypatch.setattr(arail.pkb, "_pkb_root", lambda: tmp_path)
        from arail.agents import loader
        loader.clear_cache()
        instance = loader.load_one("debt_advisor")
        assert instance is not None
        from arail.agents._builtin_debt_advisor import debt_advisor as canonical
        assert instance is canonical


class TestConsolidationAnalyzerShim:
    def test_agent_folder_created(self, tmp_path):
        from arail.agents.builtin_seed import ensure_consolidation_analyzer_folder
        ensure_consolidation_analyzer_folder(pkb_root=tmp_path)
        d = tmp_path / "agents" / "consolidation_analyzer"
        assert (d / "consolidation_analyzer.py").exists()
        assert (d / "AGENT.md").exists()

    def test_shim_singleton_identity(self, tmp_path):
        from arail.agents.builtin_seed import ensure_consolidation_analyzer_folder
        ensure_consolidation_analyzer_folder(pkb_root=tmp_path)
        py = tmp_path / "agents" / "consolidation_analyzer" / "consolidation_analyzer.py"
        module = _shim_module(py, "_test_ca_shim")
        from arail.agents._builtin_consolidation_analyzer import (
            consolidation_analyzer as canonical,
        )
        assert module.consolidation_analyzer is canonical

    def test_loader_discovers_and_loads(self, tmp_path, monkeypatch):
        import arail.pkb
        monkeypatch.setattr(arail.pkb, "_pkb_root", lambda: tmp_path)
        from arail.agents import loader
        loader.clear_cache()
        instance = loader.load_one("consolidation_analyzer")
        assert instance is not None
        from arail.agents._builtin_consolidation_analyzer import (
            consolidation_analyzer as canonical,
        )
        assert instance is canonical


class TestAgentMdFrontmatter:
    """AGENT.md frontmatter matches the loader's standard contract — no new
    frontmatter key introduced (ARCHITECTURE.md §9.2)."""

    def test_debt_advisor_frontmatter_fields(self, tmp_path):
        from arail.agents.builtin_seed import ensure_debt_advisor_folder
        from arail.skills_loader import parse_frontmatter
        ensure_debt_advisor_folder(pkb_root=tmp_path)
        text = (tmp_path / "agents" / "debt_advisor" / "AGENT.md").read_text()
        fm = parse_frontmatter(text)
        assert fm["name"] == "Debt Advisor"
        assert fm["auto_start_env"] == "LAB_DEBT_ADVISOR"
        assert "debt-strategy-summary" in text
        assert "cite-approved-findings" in text

    def test_consolidation_analyzer_frontmatter_fields(self, tmp_path):
        from arail.agents.builtin_seed import ensure_consolidation_analyzer_folder
        from arail.skills_loader import parse_frontmatter
        ensure_consolidation_analyzer_folder(pkb_root=tmp_path)
        text = (tmp_path / "agents" / "consolidation_analyzer" / "AGENT.md").read_text()
        fm = parse_frontmatter(text)
        assert fm["name"] == "Consolidation Analyzer"
        assert fm["auto_start_env"] == "LAB_CONSOLIDATION_ANALYZER"
        assert "blended-apr-calc" in text
        assert "breakeven-calc" in text


class TestSkillsSeeded:
    def test_four_debt_finance_skills_materialize(self, tmp_path):
        from arail.skill_seed import ensure_starter_skills
        ensure_starter_skills(pkb_root=tmp_path)
        for skill_id in (
            "debt-strategy-summary", "cite-approved-findings",
            "blended-apr-calc", "breakeven-calc",
        ):
            assert (tmp_path / "skills" / skill_id / "SKILL.md").exists()
