"""Import smoke tests — every public module must load cleanly.

This is the lightest possible regression net: if these pass, you have not
broken the Python package layout, circular imports, or optional-dependency
guards. Run in CI on every push.
"""

from __future__ import annotations

import importlib

import pytest


CORE_MODULES = [
    "oglab",
    "oglab.config",
    "oglab.scheduler",
    "oglab.activity",
    "oglab.goals",
    "oglab.costs",
    "oglab.pkm",
    "oglab.agents.consent",
    "oglab.agents.curator",
    "oglab.agents.researcher",
    "oglab.router",
    "oglab.router.core",
    "oglab.router.backends",
    "oglab.skills.goal_parser",
    "oglab.skills.experiment_tracker",
    "oglab.plugins.manager",
    "oglab.portal.app",
]


@pytest.mark.parametrize("name", CORE_MODULES)
def test_module_imports_cleanly(name):
    importlib.import_module(name)


def test_portal_app_has_routes():
    from oglab.portal.app import app
    paths = {getattr(r, "path", None) for r in app.routes}
    # A handful of required endpoints that must exist for the dashboard to work.
    for expected in ("/", "/api/goal", "/api/jobs/state",
                     "/api/jobs/halt", "/api/jobs/resume",
                     "/api/research/status"):
        assert expected in paths, f"missing route: {expected}"


def test_backend_map_covers_expected_backends():
    from oglab.router.backends import BACKEND_MAP
    expected = {"mlx", "cuda", "cpu", "openai_compat",
                "huggingface", "openrouter", "claude", "airllm"}
    assert expected.issubset(BACKEND_MAP.keys()), \
        f"missing backends: {expected - set(BACKEND_MAP.keys())}"
