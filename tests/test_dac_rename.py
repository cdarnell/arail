"""Knowledge → DaC rename guarantees.

- /knowledge 307s to /dac and preserves ?file= deep-links
- the nav renders DaC immediately after Dashboard, before Chat
- the dac surface key is tier-gated in for both tiers
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient


def _get_client(monkeypatch, tmp_path, lab_tier: str = "min") -> TestClient:
    monkeypatch.setenv("LAB_TIER", lab_tier)
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    import arail.portal.app as _app_mod
    return TestClient(_app_mod.app)


def test_knowledge_redirects_to_dac(monkeypatch, tmp_path):
    client = _get_client(monkeypatch, tmp_path)
    r = client.get("/knowledge", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/dac"


def test_knowledge_redirect_preserves_query(monkeypatch, tmp_path):
    """?file= deep-links are everywhere (dashboard, agents, activity log) —
    the legacy route must carry them across."""
    client = _get_client(monkeypatch, tmp_path)
    r = client.get(
        "/knowledge?file=research/program.md", follow_redirects=False
    )
    assert r.status_code == 307
    assert r.headers["location"] == "/dac?file=research%2Fprogram.md"


def test_nav_order_dashboard_dac_chat(monkeypatch, tmp_path):
    """DaC sits at position 2: right after Dashboard, before Chat."""
    client = _get_client(monkeypatch, tmp_path)
    html = client.get("/dac").text
    dash = html.find('href="/"')
    dac = html.find('href="/dac"')
    chat = html.find('href="/chat"')
    assert -1 not in (dash, dac, chat), "nav links missing"
    assert dash < dac < chat, (
        f"Nav order wrong: expected Dashboard < DaC < Chat, "
        f"got offsets {dash}, {dac}, {chat}."
    )
    # The tab is labeled DaC and marks itself active on /dac.
    assert re.search(r'href="/dac"[^>]*class="active"[^>]*>DaC</a>', html) or (
        'class="active"' in html and ">DaC</a>" in html
    )


def test_dac_in_both_tier_surfaces():
    from arail.portal.app import _TIER_SURFACES

    for tier, surfaces in _TIER_SURFACES.items():
        assert "dac" in surfaces, f"dac surface missing from tier {tier!r}"
        assert "knowledge" not in surfaces, (
            f"stale knowledge surface key still in tier {tier!r}"
        )
