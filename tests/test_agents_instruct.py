"""'Instruct' actually reaches the agent (as its active redirect) — no more
queued:True no-op."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    import arail.agent_redirects as redirects
    monkeypatch.setattr(redirects, "_redirect_file",
                        lambda: tmp_path / "agent_redirects.json")
    import arail.portal.app as app_mod
    with TestClient(app_mod.app) as c:
        yield c


def test_instruct_applies_redirect(client):
    r = client.post("/api/agents/instruct",
                    json={"agent": "researcher",
                          "instruction": "focus on evaluation methodology"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["applied"] == "redirect"
    assert "queued" not in body

    from arail.agent_redirects import get_agent_redirect
    rec = get_agent_redirect("researcher")
    assert rec and rec["instruction"] == "focus on evaluation methodology"


def test_instruct_requires_instruction(client):
    r = client.post("/api/agents/instruct", json={"agent": "researcher",
                                                  "instruction": ""})
    assert "error" in r.json()
