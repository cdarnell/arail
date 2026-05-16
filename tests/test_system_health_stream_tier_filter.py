"""Tests for /api/system/health/stream tier-filtering (sprint 2026-05-15-health-stream-tier-filter).

Covers:
- min-tier stream hides max-only check names (Marimo, Open Notebook, Neo4j Bolt)
- max-tier stream includes max-only check names
- done.total matches number of emitted check events for each tier
- snapshot and stream service-id sets align on min tier
- security: query-param bypass attempt ignored
- latency: filtered min-tier stream completes in < 2 s with mocked ports
- registry integrity: every non-None service_id in checks_all is a known registry key
"""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ONLY_STREAM_NAMES = {"Marimo", "Open Notebook", "Neo4j Bolt"}

# Names that must appear on every tier (a representative stable subset).
ALWAYS_ON_STREAM_NAMES = {
    "Portal HTTP",
    "Terminal (ttyd)",
    "Ollama API",
    "Lance vector DB",
    "RAM available",
    "Disk free",
    "Agents loadable",
    "PKB structure",
    ".env validation",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_sse(text: str) -> list[dict]:
    """Parse an SSE body into a list of JSON event dicts."""
    events = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            payload = line[6:].strip()
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
    return events


def _make_stream_client(monkeypatch, tmp_path, lab_tier: str) -> TestClient:
    """Return a TestClient with all port probes mocked False."""
    monkeypatch.setenv("LAB_TIER", lab_tier)
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    with patch("arail.portal.app._port_open", new=AsyncMock(return_value=False)), \
         patch("arail.portal.app._container_running", return_value=False), \
         patch("arail.portal.app._docker_available", return_value=False):
        from arail.portal.app import app
        return TestClient(app)


def _stream_events(client: TestClient) -> list[dict]:
    """GET /api/system/health/stream and return parsed event list."""
    r = client.get("/api/system/health/stream")
    assert r.status_code == 200, r.text
    return _parse_sse(r.text)


def _check_events(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("event") == "check"]


def _done_event(events: list[dict]) -> dict:
    done = [e for e in events if e.get("event") == "done"]
    assert len(done) == 1, f"Expected exactly 1 done event, got {len(done)}"
    return done[0]


# ---------------------------------------------------------------------------
# Test 1 — min tier hides max-only check names
# ---------------------------------------------------------------------------

def test_stream_min_tier_hides_max_only_check_names(monkeypatch, tmp_path):
    """LAB_TIER=min: Marimo, Open Notebook, Neo4j Bolt must not appear in stream."""
    client = _make_stream_client(monkeypatch, tmp_path, "min")
    events = _stream_events(client)
    names = {e["name"] for e in _check_events(events)}

    for name in MAX_ONLY_STREAM_NAMES:
        assert name not in names, (
            f"max-only check '{name}' leaked into min-tier stream"
        )

    # Representative always-on checks must be present.
    for name in ALWAYS_ON_STREAM_NAMES:
        assert name in names, (
            f"always-on check '{name}' missing from min-tier stream"
        )


# ---------------------------------------------------------------------------
# Test 2 — max tier includes max-only check names
# ---------------------------------------------------------------------------

def test_stream_max_tier_includes_max_only_check_names(monkeypatch, tmp_path):
    """LAB_TIER=max: Marimo, Open Notebook, Neo4j Bolt must appear in stream."""
    client = _make_stream_client(monkeypatch, tmp_path, "max")
    events = _stream_events(client)
    names = {e["name"] for e in _check_events(events)}

    for name in MAX_ONLY_STREAM_NAMES:
        assert name in names, (
            f"max-only check '{name}' missing from max-tier stream"
        )


# ---------------------------------------------------------------------------
# Test 3 — done.total matches emitted check count for both tiers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tier", ["min", "max"])
def test_stream_done_total_matches_check_count(monkeypatch, tmp_path, tier):
    """done.total must equal the number of check events actually emitted."""
    client = _make_stream_client(monkeypatch, tmp_path, tier)
    events = _stream_events(client)
    check_count = len(_check_events(events))
    done = _done_event(events)
    assert done["total"] == check_count, (
        f"LAB_TIER={tier}: done.total={done['total']} but {check_count} check events emitted"
    )


# ---------------------------------------------------------------------------
# Test 4 — stream and snapshot service-id sets align on min tier
# ---------------------------------------------------------------------------

def test_stream_and_snapshot_services_keysets_align_min(monkeypatch, tmp_path):
    """min-tier: max-only service ids absent from BOTH stream check names and snapshot services."""
    # Map from stream display name to _OPTIONAL_SERVICES key (max-only subset only).
    MAX_ONLY_NAME_TO_ID = {
        "Marimo": "marimo",
        "Open Notebook": "open-notebook",
        "Neo4j Bolt": "neo4j",
        # Notebook (Jupyter) is also max-only per registry.
        "Notebook (Jupyter)": "notebook",
    }

    client = _make_stream_client(monkeypatch, tmp_path, "min")

    # Stream check names.
    stream_events = _stream_events(client)
    stream_names = {e["name"] for e in _check_events(stream_events)}

    # Snapshot services dict.
    r = client.get("/api/system/health")
    assert r.status_code == 200, r.text
    snapshot_services = r.json().get("services", {})

    for display_name, svc_id in MAX_ONLY_NAME_TO_ID.items():
        assert display_name not in stream_names, (
            f"min-tier stream exposes max-only check '{display_name}'"
        )
        assert svc_id not in snapshot_services, (
            f"min-tier snapshot exposes max-only service '{svc_id}'"
        )


# ---------------------------------------------------------------------------
# Test 5 — registry integrity: every non-None service_id is a known registry key
# ---------------------------------------------------------------------------

def test_stream_check_service_ids_are_known(monkeypatch, tmp_path):
    """Every non-None service_id in the stream list must be a key in _OPTIONAL_SERVICES.

    Strategy: call the stream on both tiers, compute the difference of name sets
    (names present on max but absent on min). Every name in that difference must
    map to a known _OPTIONAL_SERVICES key.
    """
    from arail.portal.app import _OPTIONAL_SERVICES

    NAME_TO_SERVICE_ID = {
        "Terminal (ttyd)":    "ttyd",
        "Notebook (Jupyter)": "notebook",
        "Ollama API":         "ollama",
        "Lance vector DB":    "lance-memory",
        "Marimo":             "marimo",
        "Open Notebook":      "open-notebook",
        "Neo4j Bolt":         "neo4j",
    }

    min_client = _make_stream_client(monkeypatch, tmp_path, "min")
    min_names = {e["name"] for e in _check_events(_stream_events(min_client))}

    max_client = _make_stream_client(monkeypatch, tmp_path, "max")
    max_names = {e["name"] for e in _check_events(_stream_events(max_client))}

    # Names that appear on max but not on min must have a known registry mapping.
    tier_gated_names = max_names - min_names
    for name in tier_gated_names:
        svc_id = NAME_TO_SERVICE_ID.get(name)
        assert svc_id is not None, (
            f"Check '{name}' is tier-gated (absent from min stream) "
            f"but has no entry in NAME_TO_SERVICE_ID — update the test map"
        )
        assert svc_id in _OPTIONAL_SERVICES, (
            f"Check '{name}' maps to service_id '{svc_id}' "
            f"which is not in _OPTIONAL_SERVICES — typo in checks_all?"
        )


# ---------------------------------------------------------------------------
# Test 7 — security: query-param bypass attempt ignored
# ---------------------------------------------------------------------------

def test_stream_tier_bypass_query_param_ignored(monkeypatch, tmp_path):
    """LAB_TIER=min with crafted query params must not unlock max-only stream checks."""
    client = _make_stream_client(monkeypatch, tmp_path, "min")
    r = client.get("/api/system/health/stream?show_all=true&tier=max")
    assert r.status_code == 200, r.text
    names = {e["name"] for e in _check_events(_parse_sse(r.text))}
    for name in MAX_ONLY_STREAM_NAMES:
        assert name not in names, (
            f"Tier-bypass: max-only check '{name}' visible under min tier via query params"
        )


# ---------------------------------------------------------------------------
# Test 8 — setup/latency: filtered min-tier stream completes under 2 s
# ---------------------------------------------------------------------------

def test_stream_endpoint_latency_under_two_seconds_min_tier(monkeypatch, tmp_path):
    """Min-tier stream with mocked ports must complete in under 2 seconds.

    The stream has N checks × 40 ms asyncio.sleep pacing. Min tier
    drops 3 entries from the default 17-entry list, giving 14 checks
    (some entries like Notebook are also max-only; actual count may vary).
    14 checks × 40 ms = 560 ms base; 2 s ceiling gives ample headroom for
    CI variance while catching accidental synchronous sleep regressions.
    """
    client = _make_stream_client(monkeypatch, tmp_path, "min")
    t0 = time.perf_counter()
    r = client.get("/api/system/health/stream")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200, r.text
    assert elapsed < 2.0, (
        f"Min-tier stream took {elapsed:.2f}s — exceeds 2 s ceiling "
        f"(expected ≤ 14 checks × 40 ms ≈ 560 ms base)"
    )
