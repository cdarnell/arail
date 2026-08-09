"""QA (2026-08-08-arail2-tier1-integration): ``X-Retrieval-Reason`` is a
header built from an exception message, and part of that message is
supplied by the embedding provider.

``embed._post`` puts up to 400 bytes of the provider's HTTP error body
into ``EmbeddingError``'s message; ``_semantic_search`` stores that string
verbatim via ``set_degraded("provider", str(e))``; ``api_pkb_search``
reflects it into a response header. So the header value is
provider-controlled data on a security-relevant surface (response-header
injection / response splitting), and the provider is whatever
``MODEL_API_BASE`` points at — which in ``hybrid`` mode may be off-box.

These tests pin that the framework refuses to emit a header carrying CR/LF
rather than splitting the response, and that the value stays bounded.
"""
from __future__ import annotations

import asyncio

import pytest

from arail.portal import app as portal_app


def _run(coro):
    return asyncio.run(coro)


HOSTILE_REASONS = [
    ("crlf", "boom\r\nX-Injected: yes\r\n\r\n<html>owned</html>"),
    ("lf", "boom\nSet-Cookie: session=stolen"),
    ("cr", "boom\rLocation: http://evil.example"),
    ("nul", "boom\x00hidden"),
    ("non-latin1", "boom — the provider said ¡nope! \U0001f4a5"),
]


@pytest.mark.parametrize("label,reason", HOSTILE_REASONS,
                         ids=[lbl for lbl, _ in HOSTILE_REASONS])
def test_a_hostile_provider_message_cannot_split_the_response(
        monkeypatch, label, reason):
    """Response splitting itself is blocked one layer down: both uvicorn
    transports (``h11_impl`` and ``httptools_impl``) reject a header value
    containing CR/LF before it reaches the wire. Verified directly against
    ``h11.Connection.send`` and ``uvicorn...httptools_impl.HEADER_VALUE_RE``.

    So this test is about the layer that *should* have caught it: the app
    still constructs such a header, which turns a degraded-but-usable
    search into a serialization error (a self-inflicted 500 on
    ``/api/pkb/search``, remotely triggerable in ``LAB_MODE=hybrid`` where
    the provider is off-box). Sanitising at the point of construction is
    the fix — see TEST_REPORT.md QA-4.
    """
    if label in {"crlf", "lf", "cr", "nul"}:
        pytest.xfail("QA-4: the reason string is not sanitised before it "
                     "becomes a header value")
    monkeypatch.setattr(portal_app, "pkb_search", lambda q: [])
    monkeypatch.setattr("arail.pkb.retrieval_status", lambda: (False, reason))

    result = _run(portal_app.api_pkb_search(q="hello"))

    value = result.headers.get("X-Retrieval-Reason", "")
    for forbidden in ("\r", "\n", "\x00"):
        assert forbidden not in value, (
            f"{forbidden!r} survived into the response header — "
            f"a provider-controlled string must not be able to add headers")
    assert "X-Injected" not in dict(result.headers)
    assert "Set-Cookie" not in dict(result.headers)


REAL_DEGRADED_REASONS = [
    ("dimension",
     "pkb_pages index was built with a different embedding dimension than "
     "the current spec declares — run `./arailctl pkb reembed` to upgrade. "
     "Existing rows are untouched."),
    ("provenance-missing",
     "pkb_pages index has no provenance record — treated as a legacy index. "
     "Run `./arailctl pkb reembed` to upgrade."),
    ("empty",
     "pkb_pages index does not exist yet for this World — run "
     "`./arailctl pkb reembed` (or start the portal) to build it."),
    ("empty-search",
     "KB index is empty for this world — run `./arailctl pkb reembed`"),
]


@pytest.mark.parametrize("label,reason", REAL_DEGRADED_REASONS,
                         ids=[lbl for lbl, _ in REAL_DEGRADED_REASONS])
def test_the_real_degraded_messages_can_actually_be_served(monkeypatch, label, reason):
    """QA-5 — the shipping defect.

    Every degraded reason ``pkb_index`` produces contains an EM DASH
    (U+2014). Starlette encodes response header values as latin-1, so
    building the ``X-Retrieval-Reason`` header from one raises
    ``UnicodeEncodeError`` and ``GET /api/pkb/search`` returns 500 instead
    of degraded-but-usable keyword results.

    That is the state of four of the operator's five real Worlds plus the
    root lab (legacy 128-dim, no sidecar), and of every clean machine that
    has not yet pulled ``nomic-embed-text``. Reproduced end to end against
    a scratch copy of the ``qukaizen`` World.

    ``tests/test_pkb_search_api_status.py`` misses it because its fixture
    reason is a hand-written ASCII string rather than one the product
    actually emits — which is why this test parametrises over the real
    message text.
    """
    monkeypatch.setattr(portal_app, "pkb_search",
                        lambda q: [{"path": "a.md", "source": "keyword"}])
    monkeypatch.setattr("arail.pkb.retrieval_status", lambda: (False, reason))

    result = _run(portal_app.api_pkb_search(q="hello"))
    assert result.headers["X-Retrieval-Status"] == "degraded"
    assert result.headers["X-Retrieval-Reason"]


def test_reason_header_is_length_bounded(monkeypatch):
    """A 400-byte provider body plus prose must not become an unbounded
    header; some proxies drop or error on large header sets."""
    monkeypatch.setattr(portal_app, "pkb_search", lambda q: [])
    monkeypatch.setattr("arail.pkb.retrieval_status", lambda: (False, "x" * 5000))

    result = _run(portal_app.api_pkb_search(q="hello"))
    assert len(result.headers["X-Retrieval-Reason"]) <= 200


def test_healthy_search_keeps_the_bare_list_contract(monkeypatch):
    """Regression: dashboard.html / agents.html / docs_hub.html all do
    ``r.json().forEach(...)``. A degraded lab must not change the body
    shape, only add headers."""
    import json

    payload = [{"path": "a.md", "name": "a.md", "match_count": 1,
                "snippets": [], "source": "semantic"}]
    monkeypatch.setattr(portal_app, "pkb_search", lambda q: payload)

    monkeypatch.setattr("arail.pkb.retrieval_status", lambda: (True, ""))
    assert _run(portal_app.api_pkb_search(q="a")) == payload

    monkeypatch.setattr("arail.pkb.retrieval_status", lambda: (False, "degraded"))
    degraded = _run(portal_app.api_pkb_search(q="a"))
    assert json.loads(bytes(degraded.body)) == payload, \
        "the JSON body must stay a bare list in both states"
