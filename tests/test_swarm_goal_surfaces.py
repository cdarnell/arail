from __future__ import annotations

from fastapi.testclient import TestClient


def test_dashboard_renders_swarm_preview_surface():
    import arail.portal.app as app_mod

    client = TestClient(app_mod.app)
    r = client.get('/')

    assert r.status_code == 200
    assert 'Draft Swarm Plan' in r.text
    assert 'Preview Before Launch' in r.text
    assert 'Approve &amp; Run' in r.text


def test_research_page_renders_swarm_review_surface():
    import arail.portal.app as app_mod

    client = TestClient(app_mod.app)
    r = client.get('/research')

    assert r.status_code == 200
    assert 'Swarm Draft Ready' in r.text
    assert 'Review the worker lanes before launch' in r.text
    assert 'Draft Swarm Plan' in r.text