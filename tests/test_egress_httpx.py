"""httpx egress guard — the transport-level patch installed by install_guard().

Verifies the airgap decision tree applies to httpx sync + async clients,
including SDK-style clients constructed BEFORE the guard was installed
(class-level patching), and that _reset_for_tests restores the originals.

No test performs real network I/O: blocked requests raise before the
transport connects, and pass-through cases stub the original transport
method with a marker exception.
"""

from __future__ import annotations

import asyncio
import json

import pytest

httpx = pytest.importorskip("httpx")

import arail.egress as egress
from arail.airgap import EgressBlocked


class ReachedTransport(Exception):
    """Marker: the guard let the request through to the real transport."""


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("ARAIL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LAB_MODE", "airgapped")
    egress._reset_for_tests()
    yield
    egress._reset_for_tests()


def _stub_transports(monkeypatch):
    """Replace the real transport methods with markers BEFORE install,
    so a request that passes the guard raises ReachedTransport instead
    of touching the network."""
    def _sync(self, request):
        raise ReachedTransport(str(request.url))

    async def _async(self, request):
        raise ReachedTransport(str(request.url))

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _sync)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _async)


def test_airgapped_public_url_blocked_sync(tmp_path):
    egress.install_guard()
    with pytest.raises(EgressBlocked):
        httpx.Client().get("https://api.anthropic.com/v1/messages")
    lines = (tmp_path / "egress.jsonl").read_text().splitlines()
    rec = json.loads(lines[-1])
    assert rec["url_host"] == "api.anthropic.com"
    assert rec["reason"] == "airgapped"


def test_airgapped_public_url_blocked_async():
    egress.install_guard()

    async def _go():
        async with httpx.AsyncClient() as c:
            await c.get("https://example.com/")

    with pytest.raises(EgressBlocked):
        asyncio.run(_go())


def test_client_created_before_install_is_still_guarded():
    client = httpx.Client()  # constructed pre-install (SDK pattern)
    egress.install_guard()
    with pytest.raises(EgressBlocked):
        client.get("https://example.com/")


def test_localhost_passes_guard(monkeypatch):
    _stub_transports(monkeypatch)
    egress.install_guard()
    with pytest.raises(ReachedTransport):
        httpx.Client().get("http://127.0.0.1:11434/api/tags")


def test_hybrid_public_url_passes(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    _stub_transports(monkeypatch)
    egress.install_guard()
    with pytest.raises(ReachedTransport):
        httpx.Client().get("https://example.com/")


def test_allow_egress_context_passes_and_audits(monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    _stub_transports(monkeypatch)
    egress.install_guard()
    with egress.allow_egress("test httpx bypass"):
        with pytest.raises(ReachedTransport):
            httpx.Client().get("https://example.com/")
    rec = json.loads((tmp_path / "egress.jsonl").read_text().splitlines()[-1])
    assert rec["reason"] == "allow:test httpx bypass"


def test_reset_restores_originals():
    egress.install_guard()
    assert getattr(httpx.HTTPTransport.handle_request, "_arail_guarded", False)
    egress._reset_for_tests()
    assert not getattr(httpx.HTTPTransport.handle_request, "_arail_guarded", False)
    assert not getattr(
        httpx.AsyncHTTPTransport.handle_async_request, "_arail_guarded", False
    )
