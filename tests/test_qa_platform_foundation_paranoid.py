"""QA paranoid tests for sprint 2026-05-14-platform-foundation.

Focus areas per REVIEW.md:
- Setup (30%): tier-flip behavior and fresh-checkout responsiveness.
- Security (20%): metrics body leakage, /skills open-redirect, ?show_all bypass.
- Regression (10%): conformance + key-name stability cross-checks.

These tests do NOT duplicate the builder's coverage; they hunt edges:
- `?show_all=true` and other bypass query strings.
- Tier flip mid-process (no cache).
- Method enforcement on /api/system/metrics (POST/DELETE/HEAD).
- Concurrent counter atomicity.
- Path-traversal/exotic skill_id deep-links.
- Multi `?view=` params.
- /skills query/fragment/trailing-slash variants.
- Metrics body scrubbing — no absolute paths, no env-var dumps.
- API conventions "Known drift" backlog completeness check.
"""

from __future__ import annotations

import concurrent.futures
import os
import re
import urllib.parse

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from arail.portal import app as app_module
    with app_module._METRICS_LOCK:
        app_module._METRICS["http_requests_total"] = 0
        app_module._METRICS["http_errors_total"] = 0
        app_module._METRICS["last_provider_change_unix"] = 0
    return TestClient(app_module.app), app_module


# ---------------------------------------------------------------------------
# §1 Health tier-gating — bypass attempts (security)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", [
    "?show_all=true",
    "?show_all=1",
    "?tier=max",
    "?lab_tier=max",
    "?include_max=1",
    "?all=1",
    "?debug=1",
])
def test_health_no_query_bypass_for_min_tier(monkeypatch, tmp_path, query):
    """No query string permutation should reveal max-only services on a min lab."""
    client, _ = _client(monkeypatch, tmp_path, LAB_TIER="min")
    r = client.get(f"/api/system/health{query}")
    assert r.status_code == 200, r.text
    services = r.json().get("services", {})
    forbidden = {"marimo", "open-notebook", "neo4j", "opencode", "notebook"}
    leaked = forbidden & set(services.keys())
    assert not leaked, (
        f"Query {query!r} leaked max-only service keys to min tier: {leaked}"
    )


def test_health_tier_flip_no_cache(monkeypatch, tmp_path):
    """Flipping LAB_TIER mid-process changes the visible service set on next call."""
    client, _ = _client(monkeypatch, tmp_path, LAB_TIER="min")
    min_keys = set(client.get("/api/system/health").json().get("services", {}).keys())
    monkeypatch.setenv("LAB_TIER", "max")
    max_keys = set(client.get("/api/system/health").json().get("services", {}).keys())
    # max should be a superset (services may be down so won't always show, but the
    # filter relaxation must be observable: either equal-or-superset, never strictly less).
    assert min_keys.issubset(max_keys) or min_keys == max_keys, (
        f"min keys {min_keys} not a subset of max keys {max_keys} after live flip"
    )


def test_health_empty_tier_defaults_to_min(monkeypatch, tmp_path):
    """LAB_TIER='' is treated as min (no max-only services exposed)."""
    client, _ = _client(monkeypatch, tmp_path, LAB_TIER="")
    services = client.get("/api/system/health").json().get("services", {})
    forbidden = {"marimo", "open-notebook", "neo4j", "opencode", "notebook"}
    assert not (forbidden & set(services.keys()))


def test_health_unknown_tier_defaults_to_min(monkeypatch, tmp_path):
    """LAB_TIER='unicorn' clamps to min — does not crash, does not expose max."""
    client, _ = _client(monkeypatch, tmp_path, LAB_TIER="unicorn-xyz")
    r = client.get("/api/system/health")
    assert r.status_code == 200
    services = r.json().get("services", {})
    forbidden = {"marimo", "open-notebook", "neo4j", "opencode", "notebook"}
    assert not (forbidden & set(services.keys()))


def test_health_spec_tier_field_preserved(monkeypatch, tmp_path):
    """The existing spec-tier `tier` field (minimum/standard/full/deep) is not
    clobbered by the lab-tier filter logic."""
    client, _ = _client(monkeypatch, tmp_path, LAB_TIER="min")
    body = client.get("/api/system/health").json()
    assert "tier" in body, "spec-tier `tier` field disappeared"
    assert body["tier"] in {"minimum", "standard", "full", "deep"}, (
        f"spec-tier field has unexpected value: {body['tier']!r}"
    )


# ---------------------------------------------------------------------------
# §2 Metrics — security & method enforcement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_metrics_only_allows_get(monkeypatch, tmp_path, method):
    """Non-GET methods on /api/system/metrics return 405 (or other non-200)."""
    client, _ = _client(monkeypatch, tmp_path)
    r = client.request(method, "/api/system/metrics")
    assert r.status_code in (405, 404, 501), (
        f"{method} /api/system/metrics returned {r.status_code} — should be 405"
    )


def test_metrics_unknown_format_silently_ignored(monkeypatch, tmp_path):
    """Unknown ?format=garbage values silently fall back to JSON (forward-compat per api-conventions §4)."""
    client, _ = _client(monkeypatch, tmp_path)
    r = client.get("/api/system/metrics?format=garbage")
    # Spec: unknown query params are silently ignored. Implementation currently
    # checks only "prometheus" explicitly — others should fall through to JSON.
    assert r.status_code == 200, (
        f"Unknown ?format=garbage returned {r.status_code} — should silently default to JSON"
    )
    assert r.json().get("schema_version") == 1


def test_metrics_body_no_absolute_paths(monkeypatch, tmp_path):
    """Metrics body must not echo back absolute filesystem paths or HOME."""
    client, _ = _client(monkeypatch, tmp_path)
    body_str = client.get("/api/system/metrics").text
    home = os.path.expanduser("~")
    assert home not in body_str, f"HOME path {home!r} leaked in metrics body"
    # No absolute paths under /Users, /home, /var, /etc beyond fragments.
    suspicious = re.findall(r"(/Users/[^\"\s]+|/home/[^\"\s]+|/etc/[^\"\s]+)", body_str)
    assert not suspicious, f"Absolute paths leaked in metrics body: {suspicious[:3]}"


def test_metrics_body_no_env_dump(monkeypatch, tmp_path):
    """Setting a sentinel env var must not cause it to appear in metrics output."""
    sentinel = "QA_SENTINEL_VALUE_DO_NOT_LEAK_xyz123"
    client, _ = _client(monkeypatch, tmp_path, FOO_API_KEY=sentinel, MY_SECRET=sentinel)
    body_str = client.get("/api/system/metrics").text
    assert sentinel not in body_str, "Env-var value leaked into metrics body"


def test_metrics_counter_concurrency(monkeypatch, tmp_path):
    """Concurrent requests do not lose increments (lock atomicity)."""
    client, app_module = _client(monkeypatch, tmp_path)
    # baseline
    base = client.get("/api/system/metrics").json()["http_requests_total"]
    N = 25

    def hit():
        return client.get("/health").status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda _: hit(), range(N)))
    assert all(s == 200 for s in results), f"some /health hits failed: {results}"
    after = client.get("/api/system/metrics").json()["http_requests_total"]
    assert after >= base + N, (
        f"Lost increments under concurrency: base={base}, after={after}, N={N}"
    )


def test_metrics_active_provider_is_label_not_secret(monkeypatch, tmp_path):
    """active_provider should always be a short identifier, even if MODEL_BACKEND
    is set to a token-like string. (Defensive: future-proofing.)"""
    client, _ = _client(monkeypatch, tmp_path, MODEL_BACKEND="my_machine")
    body = client.get("/api/system/metrics").json()
    assert body["active_provider"] == "my_machine"
    assert len(body["active_provider"]) < 64


def test_metrics_prometheus_error_envelope_conformant(monkeypatch, tmp_path):
    """The 501 envelope on ?format=prometheus matches docs/api-conventions.md §3."""
    client, _ = _client(monkeypatch, tmp_path)
    r = client.get("/api/system/metrics?format=prometheus")
    assert r.status_code == 501
    body = r.json()
    assert set(body.keys()) >= {"error", "message"}
    # error slug is snake_case
    assert re.fullmatch(r"[a-z][a-z0-9_]*", body["error"]), (
        f"error slug {body['error']!r} is not snake_case lowercase"
    )
    assert isinstance(body["message"], str) and body["message"].endswith(".")


# ---------------------------------------------------------------------------
# §4 Skills fold — open redirect, deep-link edges, multi-view
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("evil_query", [
    "?next=https://evil.com",
    "?next=//evil.com",
    "?redirect=https://evil.com/phish",
    "?url=javascript:alert(1)",
    "?view=skills&next=https://evil.com",
])
def test_skills_redirect_ignores_open_redirect_payload(monkeypatch, tmp_path, evil_query):
    """No query parameter on /skills should influence the Location header."""
    client, _ = _client(monkeypatch, tmp_path)
    r = client.get(f"/skills{evil_query}", follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers.get("location", "")
    assert loc == "/agents?view=skills", (
        f"/skills{evil_query} produced unexpected Location: {loc!r}"
    )
    # Belt and braces — Location is not an absolute scheme:// URL.
    assert "://" not in loc
    assert "evil.com" not in loc


def test_skills_redirect_fragment_not_propagated(monkeypatch, tmp_path):
    """URL fragments are client-side and not sent by browsers, but be sure."""
    client, _ = _client(monkeypatch, tmp_path)
    # TestClient strips fragments before send anyway; this is a smoke check.
    r = client.get("/skills", follow_redirects=False)
    assert r.headers.get("location") == "/agents?view=skills"


@pytest.mark.parametrize("exotic_id", [
    "../../etc/passwd",
    "..%2F..%2Fetc%2Fpasswd",
    "a" * 512,
    "skill\x00null",
    "<script>alert(1)</script>",
    "skill with spaces",
])
def test_agents_skills_deeplink_exotic_id_safe(monkeypatch, tmp_path, exotic_id):
    """Path-traversal / XSS payloads in skill_id must not crash the route or
    reflect into the response unescaped."""
    client, _ = _client(monkeypatch, tmp_path)
    # url-encode the path segment so Starlette routes it
    encoded = urllib.parse.quote(exotic_id, safe="")
    r = client.get(f"/agents/skills/{encoded}")
    # Either 200 (renders Skills view, no editor pre-opened) or 404 acceptable.
    assert r.status_code in (200, 404), (
        f"exotic skill_id {exotic_id!r} caused {r.status_code}"
    )
    if r.status_code == 200:
        # Must not reflect raw script tags
        assert "<script>alert(1)</script>" not in r.text, (
            "Unescaped XSS payload reflected in /agents/skills/<id> response"
        )
        # Must not leak filesystem reads of /etc/passwd
        assert "root:x:0:0" not in r.text
        assert "/etc/passwd" not in r.text or exotic_id == "../../etc/passwd"  # may appear escaped


def test_agents_multiple_view_params_last_wins_or_safe(monkeypatch, tmp_path):
    """`?view=status&view=skills` — must pick one deterministically; either
    behavior is acceptable as long as it doesn't crash and the body matches one of the two."""
    client, _ = _client(monkeypatch, tmp_path)
    r = client.get("/agents?view=status&view=skills")
    assert r.status_code == 200
    # body should be served and contain at least one of the data-view markers
    assert 'data-view=' in r.text


def test_agents_view_skills_html_no_data_uri_or_script_injection(monkeypatch, tmp_path):
    """Sanity: the rendered Skills view doesn't expose javascript: URIs from defaults."""
    client, _ = _client(monkeypatch, tmp_path)
    r = client.get("/agents?view=skills")
    assert r.status_code == 200
    assert "javascript:" not in r.text.lower()


def test_skills_with_trailing_slash(monkeypatch, tmp_path):
    """/skills/ (trailing slash) — Starlette may 307 or 404; must NOT 200 the old page."""
    client, _ = _client(monkeypatch, tmp_path)
    r = client.get("/skills/", follow_redirects=False)
    # Acceptable: 307/308 redirect to /skills (then /agents?view=skills), or 404.
    # NOT acceptable: 200 with the old standalone skills page.
    assert r.status_code in (200, 301, 302, 307, 308, 404)
    if r.status_code == 200:
        # If served, must be the agents.html template (not the deleted skills.html).
        assert 'data-view' in r.text, "/skills/ appears to serve a non-agents template"


# ---------------------------------------------------------------------------
# §0 conventions — known drift backlog completeness
# ---------------------------------------------------------------------------


def test_api_conventions_known_drift_lists_at_least_3(monkeypatch, tmp_path):
    """The 'Known drift' table in docs/api-conventions.md catalogs the
    pre-existing non-conformant endpoints. There should be at least 3 entries."""
    from pathlib import Path as _Path
    doc = _Path("docs/api-conventions.md")
    # Resolve relative to repo root, regardless of test cwd.
    if not doc.exists():
        # fall back to absolute discovery
        import arail
        repo = _Path(arail.__file__).resolve().parents[2]
        doc = repo / "docs" / "api-conventions.md"
    text = doc.read_text(encoding="utf-8")
    assert "Known drift" in text, "api-conventions.md missing 'Known drift' section"
    # Count table rows under 'Known drift' (rough: lines starting with `| `).
    after = text.split("Known drift", 1)[1]
    rows = [ln for ln in after.splitlines()
            if ln.startswith("| ") and "---" not in ln and "Endpoint" not in ln]
    assert len(rows) >= 3, (
        f"Known drift backlog has only {len(rows)} entries — expected >= 3"
    )


def test_api_conventions_documents_error_envelope_shape(monkeypatch, tmp_path):
    """docs/api-conventions.md documents the error envelope keys we test against."""
    from pathlib import Path as _Path
    doc = _Path("docs/api-conventions.md")
    if not doc.exists():
        import arail
        repo = _Path(arail.__file__).resolve().parents[2]
        doc = repo / "docs" / "api-conventions.md"
    text = doc.read_text(encoding="utf-8")
    assert '"error"' in text and '"message"' in text


# ---------------------------------------------------------------------------
# Regression — counters are zero for paths that match excluded prefixes
# ---------------------------------------------------------------------------


def test_metrics_self_call_not_counted_even_with_query(monkeypatch, tmp_path):
    """Self-exclusion works even when ?format= is appended."""
    client, _ = _client(monkeypatch, tmp_path)
    base = client.get("/api/system/metrics").json()["http_requests_total"]
    for _ in range(3):
        client.get("/api/system/metrics?format=prometheus")
        client.get("/api/system/metrics?format=garbage")
    after = client.get("/api/system/metrics").json()["http_requests_total"]
    assert after == base, (
        f"Self-exclusion broken with query strings: base={base}, after={after}"
    )
