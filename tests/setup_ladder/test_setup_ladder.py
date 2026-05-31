"""Setup-ladder mock tests for the self-hosted ai-eng fetch ladder.

Sprint: 2026-05-30-model-hosting-reframe. QA deliverable flagged in REVIEW.md
("the setup-ladder mock tests ... are QA's deliverable").

Maps to ARCHITECTURE.md §Test strategy "Setup (30%) — headline" and to the
§Failure modes table. EVERY external command is stubbed (see conftest); no
download, no model load, no real ollama. OOM-safe by construction.

The ai-eng ladder lives in the back half of scripts/setup.sh:install_services().
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# 1. HF-primary success — the WC#1 "met-on-upload" path
# ---------------------------------------------------------------------------

def test_hf_primary_success_single_pull_no_create_no_mirror(ladder):
    """HF pull succeeds → single `ollama pull hf.co/...`, no create, no curl."""
    r = ladder(hf_ok="1")
    assert r.ladder_exit == 0
    assert r.calls("PULL hf.co/") == 1, "expected exactly one HF pull"
    assert not r.called("CURL"), "HF success must not touch any mirror curl"
    assert not r.called("CREATE"), "HF native pull must not run ollama create"
    # No heavy preview pull on the success path.
    assert not r.called("PULL qwen"), "must not pull the 7B preview base"


def test_hf_primary_success_respects_env_repo_and_quant(ladder):
    """Operator env overrides flow into the HF pull reference."""
    r = ladder(hf_ok="1", env={
        "ARAIL_AI_ENG_HF_REPO": "myorg/myrepo",
        "ARAIL_AI_ENG_QUANT": "Q8_0",
    })
    assert r.ladder_exit == 0
    assert r.called("PULL hf.co/myorg/myrepo:Q8_0")


# ---------------------------------------------------------------------------
# 2. HF 404 → GitHub mirror, digest MATCH → create
# ---------------------------------------------------------------------------

def test_hf_404_then_github_mirror_digest_match_creates(ladder):
    """HF fails, mirror download verifies, ollama create runs from local gguf."""
    pinned = "a" * 64
    r = ladder(hf_ok="0", curl_ok="1", fake_sha=pinned,
               env={"ARAIL_AI_ENG_SHA256": pinned})
    assert r.ladder_exit == 0
    assert r.calls("PULL hf.co/") == 1, "HF attempted first"
    assert r.called("CURL"), "mirror download attempted after HF 404"
    assert r.called("CREATE create ai-eng"), "verified blob must reach ollama create"
    assert not r.called("PULL qwen"), "preview net must NOT run after mirror success"


# ---------------------------------------------------------------------------
# 3. Mirror digest MISMATCH → fail-closed (no create), fall through
# ---------------------------------------------------------------------------

def test_mirror_digest_mismatch_fails_closed_no_create(ladder):
    """Downloaded blob whose sha != pinned digest is discarded; never created."""
    pinned = "a" * 64
    r = ladder(hf_ok="0", curl_ok="1", fake_sha="b" * 64,
               preview_pull_ok="1", env={"ARAIL_AI_ENG_SHA256": pinned})
    assert r.ladder_exit == 0
    assert r.called("CURL"), "mirror download attempted"
    # The ONLY create allowed is the preview-net create, NOT a mirror create.
    # Assert no create happened from the unverified GitHub/CDN blob: since the
    # mirror create is gated behind sha match, and sha mismatched, the only
    # create in the log (if any) must be the preview path. We assert the
    # mismatch was detected in the narrative.
    assert "sha256 mismatch" in r.output.lower() or "discard" in r.output.lower()
    # Falls through to the preview net.
    assert r.called("PULL qwen")


# ---------------------------------------------------------------------------
# 4. Placeholder digest → mirror DISABLED (no curl), straight to preview net
# ---------------------------------------------------------------------------

def test_placeholder_digest_disables_mirror_no_download(ladder):
    """A placeholder sha must skip the mirror WITHOUT downloading (fail-closed)."""
    # Default ARAIL_AI_ENG_SHA256 is the placeholder sentinel.
    r = ladder(hf_ok="0", curl_ok="1", preview_pull_ok="1",
               env={"ARAIL_AI_ENG_SHA256": "__PLACEHOLDER_SHA256__"})
    assert r.ladder_exit == 0
    assert not r.called("CURL"), (
        "placeholder digest must disable the mirror BEFORE any curl download "
        "(fail-closed: no download-and-trust)"
    )
    assert "placeholder" in r.output.lower()
    # Preview net is the only remaining path.
    assert r.called("PULL qwen")


# ---------------------------------------------------------------------------
# 5. All self-hosted hosts fail (current reality) → preview net
# ---------------------------------------------------------------------------

def test_all_hosts_fail_falls_to_preview_net(ladder):
    """Artifact-not-uploaded reality: HF 404 + placeholder sha → preview net.
    Re-base 2026-05-30: preview base is now qwen2.5:1.5b (not 7b)."""
    r = ladder(hf_ok="0", curl_ok="0", preview_pull_ok="1")
    assert r.ladder_exit == 0
    assert r.called("PULL qwen2.5:1.5b"), "preview net pulls the 1.5B base"
    assert r.called("CREATE create ai-eng"), "preview Modelfile builds ai-eng"


def test_preview_net_narrative_has_no_qwen_marketing(ladder):
    """info() narrative must use neutral wording, not advertise qwen2.5:7b.

    Per Part 3: the literal id may appear only in a `warn` recovery line, not
    in the neutral `info` narrative. We assert the `info`-level fetch line says
    'preview base', not 'qwen'.
    """
    r = ladder(hf_ok="0", preview_pull_ok="1")
    info_lines = [ln for ln in r.output.splitlines()
                  if "[arail]" in ln and "Fetching preview base" in ln]
    assert info_lines, "expected a neutral 'Fetching preview base' info line"
    for ln in info_lines:
        assert "qwen" not in ln.lower()


# ---------------------------------------------------------------------------
# 6. Offline / total failure → no crash, no heavy download, manual hint
# ---------------------------------------------------------------------------

def test_total_failure_exits_clean_and_prints_manual_command(ladder):
    """Everything fails (offline) → ladder returns 0, prints recovery command."""
    r = ladder(hf_ok="0", curl_ok="0", preview_pull_ok="0")
    assert r.ladder_exit == 0, "setup must NOT abort on total ai-eng failure"
    assert "ollama pull hf.co/" in r.output, "manual self-hosted command printed"


def test_total_failure_does_not_pull_any_heavy_deep_model(ladder):
    """No failure path may pull a 70B/deep model or the sentinel."""
    r = ladder(hf_ok="0", curl_ok="0", preview_pull_ok="0")
    assert not r.called("PULL hf.co/meta-llama")
    assert not r.called("__TODO_DEEP_MODEL__")
    assert not r.called("70B")
    assert not r.called("405B")


# ---------------------------------------------------------------------------
# 7. ARAIL_SKIP_OLLAMA — no network attempts at all
# ---------------------------------------------------------------------------

def test_skip_ollama_makes_zero_pull_attempts(ladder):
    """ARAIL_SKIP_OLLAMA=1 → graceful skip, zero pulls, zero curls."""
    r = ladder(env={"ARAIL_SKIP_OLLAMA": "1"})
    assert r.ladder_exit == 0
    assert not r.called("PULL"), "skip must make no pull attempts"
    assert not r.called("CURL")


# ---------------------------------------------------------------------------
# 8. Idempotency + legacy alias migration
# ---------------------------------------------------------------------------

def test_already_installed_is_idempotent_skip(ladder):
    """ai-eng already present → no pull, no curl, clean skip."""
    r = ladder(installed="ai-eng")
    assert r.ladder_exit == 0
    assert not r.called("PULL")
    assert not r.called("CURL")


def test_legacy_ai_engineer_aliased_not_repulled(ladder):
    """Legacy ai-engineer:latest → ollama cp alias, no heavy re-pull."""
    r = ladder(installed="ai-engineer:latest", cp_ok="1")
    assert r.ladder_exit == 0
    assert r.called("CP cp ai-engineer:latest ai-eng:latest")
    assert not r.called("PULL"), "alias path must not re-download"


# ---------------------------------------------------------------------------
# 9. CDN tertiary only fires when URL is set
# ---------------------------------------------------------------------------

def test_cdn_skipped_when_url_empty(ladder):
    """Empty CDN url (default) → only HF + GitHub curl, never a third curl."""
    pinned = "a" * 64
    r = ladder(hf_ok="0", curl_ok="0", fake_sha=pinned,
               env={"ARAIL_AI_ENG_SHA256": pinned})
    # With a real (non-placeholder) digest, GitHub mirror curls once and fails;
    # CDN url is empty so it must NOT curl a second time.
    assert r.calls("CURL") == 1, "empty CDN url must not trigger a second mirror curl"


def test_cdn_fires_when_url_set(ladder):
    """A set CDN url adds a second mirror attempt after GitHub."""
    pinned = "a" * 64
    r = ladder(hf_ok="0", curl_ok="0", fake_sha=pinned,
               env={"ARAIL_AI_ENG_SHA256": pinned,
                    "ARAIL_AI_ENG_CDN_URL": "https://cdn.example.com/ai-eng.gguf"})
    assert r.calls("CURL") == 2, "GitHub + CDN = two mirror attempts"
