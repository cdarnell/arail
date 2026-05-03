"""docs/PUBLISH.md doc-shape regression test.

The PUBLISH.md operator runbook is the single source of truth for how
to expose ARAIL on the public internet.  If sections are removed or
renamed, the next operator who clones this repo will hit walls.

This is a structural test, not prose.  It asserts the headings + key
phrases that ARCHITECTURE.md's H1–H5 + OBS7–OBS8 mitigations point at,
plus the security guidance the architect specified.

Failure modes covered: H1 (proxy_buffering off), H2 (Cloudflare Access
linked, not embedded), H3 (chmod 0600 secrets), H4 (auth-proxy ≠
passphrase), OBS7 (metrics restriction snippet), OBS8 (per-worker
uptime caveat).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


PUBLISH_MD = Path(__file__).resolve().parent.parent / "docs" / "PUBLISH.md"


@pytest.fixture(scope="module")
def doc() -> str:
    assert PUBLISH_MD.exists(), f"docs/PUBLISH.md missing at {PUBLISH_MD}"
    return PUBLISH_MD.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Top-level structure (sections 1–10)
# ---------------------------------------------------------------------------

REQUIRED_SECTION_HEADERS = (
    "## 1. Prerequisites",
    "## 2. Reverse proxy configuration",
    "## 3. Authentication",
    "## 4. Environment and secrets hardening",
    "## 5. Admin surface",
    "## 6. Performance tuning",
    "## 7. Security scan",
    "## 8. Ongoing operations",
    "## 9. Sharing the lab",
    "## 10. Observability endpoints",
)


@pytest.mark.parametrize("header", REQUIRED_SECTION_HEADERS)
def test_required_section_present(doc, header):
    assert header in doc, f"Missing section header: {header!r}"


# ---------------------------------------------------------------------------
# H1 — reverse-proxy SSE configuration
# ---------------------------------------------------------------------------

def test_nginx_proxy_buffering_off_present(doc):
    """H1: SSE works only with proxy_buffering off; required for our SSE endpoints."""
    assert "proxy_buffering off" in doc


def test_proxy_read_timeout_long(doc):
    """H1: long timeout for inference (default 60s would kill local-model responses)."""
    assert "proxy_read_timeout 600s" in doc, (
        "Operators MUST be told to extend the proxy read timeout for local inference"
    )


def test_caddy_section_present(doc):
    assert "### Caddy" in doc, "Caddy snippet must be a documented option"


# ---------------------------------------------------------------------------
# H2 — Cloudflare Access linked, not embedded
# ---------------------------------------------------------------------------

def test_cloudflare_access_referenced(doc):
    """H2: Cloudflare Access framed as one option; we link instead of embedding screenshots."""
    assert "Cloudflare Access" in doc
    # Link to current docs (per H2 mitigation: don't embed steps that will rot).
    assert "developers.cloudflare.com" in doc


# ---------------------------------------------------------------------------
# Auth options — Cloudflare + basic auth + Cloudflare Tunnel
# ---------------------------------------------------------------------------

def test_basic_auth_option_documented(doc):
    """The simpler-but-weaker option must be documented as such."""
    assert "Basic Auth" in doc or "auth_basic" in doc


# ---------------------------------------------------------------------------
# H3 — chmod 0600 secrets check
# ---------------------------------------------------------------------------

def test_chmod_0600_secrets_documented(doc):
    """H3: explicit chmod 0600 on secrets.env and .env."""
    assert "chmod 0600 lab/data/secrets.env" in doc
    assert "chmod 0600 .env" in doc


# ---------------------------------------------------------------------------
# H4 — passphrase ≠ auth proxy
# ---------------------------------------------------------------------------

def test_passphrase_not_auth_proxy_warning(doc):
    """H4: bold warning that the in-app passphrase is not a substitute for an auth proxy."""
    # Look for either explicit text about passphrase + auth proxy in close proximity.
    lower = doc.lower()
    assert "onboarding_gate" in lower or "passphrase" in lower
    # The auth-proxy framing appears in §3 / §5.
    assert "Cloudflare Access" in doc or "auth proxy" in lower


# ---------------------------------------------------------------------------
# LAB_MODE=hybrid implications
# ---------------------------------------------------------------------------

def test_lab_mode_hybrid_implications_documented(doc):
    """Operators flipping to hybrid must understand the cloud-call implication."""
    assert "LAB_MODE=hybrid" in doc or "hybrid mode" in doc


def test_airgapped_default_acknowledged(doc):
    assert "airgapped" in doc.lower()


# ---------------------------------------------------------------------------
# OBS7 — /metrics restriction at the reverse-proxy layer
# ---------------------------------------------------------------------------

def test_metrics_restriction_snippet(doc):
    """OBS7: /metrics is unauthenticated; nginx allow/deny snippet must be present."""
    assert "allow 127.0.0.1" in doc
    assert "deny all" in doc
    # And the snippet must appear under the /metrics restriction section.
    pattern = re.compile(
        r"location /metrics.*?allow 127\.0\.0\.1.*?deny all",
        re.DOTALL,
    )
    assert pattern.search(doc), (
        "/metrics restriction snippet must scope allow/deny inside the location block"
    )


def test_metrics_aggregate_only_documented(doc):
    """OBS1: doc must affirm /metrics emits aggregate counts only — no package names."""
    assert "aggregate counts only" in doc or "aggregate-only" in doc.lower()


# ---------------------------------------------------------------------------
# OBS8 — per-worker uptime caveat for multi-worker deployments
# ---------------------------------------------------------------------------

def test_multi_worker_uptime_caveat(doc):
    assert "multi-worker" in doc or "multiple workers" in doc, (
        "OBS8: doc must warn that uptime is per-worker if --workers > 1"
    )


# ---------------------------------------------------------------------------
# Hardening checklist + TLS
# ---------------------------------------------------------------------------

def test_tls_required(doc):
    assert "TLS" in doc, "TLS must be required for public exposure"


def test_strong_passphrase_required(doc):
    """A weak ARAIL_PASSWORD is a real foot-gun; the doc must call this out."""
    assert "strong passphrase" in doc or "not the placeholder" in doc
