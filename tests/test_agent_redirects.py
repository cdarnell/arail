from __future__ import annotations

from pathlib import Path

from arail import agent_redirects


def test_set_and_clear_agent_redirect(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(agent_redirects, "DATA_DIR", tmp_path)

    redirect = agent_redirects.set_agent_redirect(
        "researcher",
        "Stop fetching and define the eval.",
        preset="measurement",
        label="Tighten Eval",
    )

    assert redirect["agent_id"] == "researcher"
    assert redirect["preset"] == "measurement"
    assert agent_redirects.get_agent_redirect("researcher") is not None

    removed = agent_redirects.clear_agent_redirect("researcher")
    assert removed is not None
    assert agent_redirects.get_agent_redirect("researcher") is None


def test_redirect_profile_marks_measurement_and_autoresearch():
    profile = agent_redirects.redirect_profile({
        "preset": "autoresearch",
        "instruction": "Stop fetching and figure out how to measure this so it can go into AutoResearch.",
    })

    assert profile["skip_fetch"] is True
    assert profile["focus_measurement"] is True
    assert profile["prefer_autoresearch"] is True