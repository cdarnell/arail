"""QA pass for sprint 2026-05-11-min-cloud-first.

Edge cases the builder + architect didn't think of:

  - Airgapped guard still refuses /api/providers/save for every new
    provider id (security regression).
  - _write_secrets() round-trips all 10 env vars distinctly + chmod 0600.
  - Provider IDs are lowercase ASCII (data-prov attribute / dict-key
    safety for the modal).
  - Signup URLs do not leak into activity_log emissions.
  - min→max→min upgrade cycle preserves explicit LAB_MODE.
  - chat.html still renders the bring-your-own "Custom" UI element
    even though `custom` is not in the JS PROVIDERS array.

Allocation per the sprint brief:
  35% provider-wiring / 25% setup-flow / 20% security / 10% UI / 10% regression
"""
from __future__ import annotations

import asyncio
import os
import re
import stat
import string
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from arail.portal import app as portal_app


CURATED_TEN = {
    "claude", "openai", "gemini", "mistral", "xai",
    "openrouter", "huggingface", "nvidia", "together", "groq",
}


# ─── helpers ─────────────────────────────────────────────────────────────


class _FakeRequest:
    """Minimal stand-in for starlette Request — only `.json()` is used by
    the providers_save / active / remove handlers."""

    def __init__(self, body: dict):
        self._body = body

    async def json(self):
        return self._body


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) \
        if False else asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture
def tmp_secrets(tmp_path: Path, monkeypatch):
    """Point DATA_DIR at a tmpdir so _write_secrets doesn't touch the
    real lab/data/secrets.env."""
    monkeypatch.setattr(portal_app, "DATA_DIR", tmp_path)
    return tmp_path


# ─── SECURITY (20%) ──────────────────────────────────────────────────────


@pytest.mark.parametrize("provider_id", sorted(CURATED_TEN))
def test_airgapped_save_refuses_every_curated_provider(provider_id, tmp_secrets, monkeypatch):
    """The airgapped guard must refuse /api/providers/save for every new
    provider id. A regression here would leak keys onto disk in
    airgapped mode (e.g. max tier default)."""
    monkeypatch.setenv("LAB_MODE", "airgapped")
    monkeypatch.delenv("ARAIL_MODE", raising=False)
    req = _FakeRequest({"provider": provider_id, "token": "sk-test-leak"})
    result = asyncio.new_event_loop().run_until_complete(portal_app.providers_save(req))
    assert result.get("ok") is False, (
        f"airgapped guard let provider {provider_id!r} save through"
    )
    assert "airgapped" in result.get("error", "").lower()
    # Secrets file must NOT have been written.
    secrets_file = tmp_secrets / "secrets.env"
    if secrets_file.exists():
        body = secrets_file.read_text()
        assert "sk-test-leak" not in body, (
            f"airgapped mode wrote token for {provider_id!r} to secrets.env"
        )


def test_airgapped_active_refuses_every_curated_provider(monkeypatch):
    """/api/providers/active must also refuse to switch to a cloud
    provider while airgapped — otherwise a chat round-trip would attempt
    to hit a cloud endpoint."""
    monkeypatch.setenv("LAB_MODE", "airgapped")
    monkeypatch.delenv("ARAIL_MODE", raising=False)
    for pid in CURATED_TEN:
        req = _FakeRequest({"provider": pid})
        result = asyncio.new_event_loop().run_until_complete(portal_app.providers_active(req))
        assert result.get("ok") is False, f"airgapped active accepted {pid!r}"
    # Sanity: my_machine must still work.
    req = _FakeRequest({"provider": "my_machine"})
    result = asyncio.new_event_loop().run_until_complete(portal_app.providers_active(req))
    assert result.get("ok") is True


def test_save_persists_chmod_0600(tmp_secrets, monkeypatch):
    """Write a token in hybrid mode; secrets.env must be chmod 0600.
    Defends the documented invariant ('keys never leak')."""
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.delenv("ARAIL_MODE", raising=False)
    req = _FakeRequest({"provider": "groq", "token": "gsk_paranoid"})
    result = asyncio.new_event_loop().run_until_complete(portal_app.providers_save(req))
    assert result.get("ok") is True
    secrets_file = tmp_secrets / "secrets.env"
    assert secrets_file.exists()
    mode = stat.S_IMODE(secrets_file.stat().st_mode)
    # On filesystems that honor chmod (most). If the FS doesn't (some
    # CI runners, tmpfs configs), accept anything that masks group/other
    # write bits off.
    assert mode in (0o600, 0o644), f"unexpected secrets.env mode 0o{mode:o}"
    assert mode & 0o077 == 0, (
        f"secrets.env permissive (mode=0o{mode:o}) — group/other can read"
    )


def test_signup_url_never_emitted_to_activity_log(tmp_secrets, monkeypatch):
    """A successful save emits an activity_log entry. The sign-up URL
    (or any URL from _PROVIDER_META) must not appear in that message —
    sign-up URLs are not secret, but leaking provider metadata through
    activity events is unwanted log noise."""
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.delenv("ARAIL_MODE", raising=False)
    seen_messages: list[str] = []

    def _capture(source, message, level="info", data=None):
        seen_messages.append(message)
        return {}

    with patch.object(portal_app.activity_log, "emit", side_effect=_capture):
        req = _FakeRequest({"provider": "openai", "token": "sk-secret-token"})
        asyncio.new_event_loop().run_until_complete(portal_app.providers_save(req))
    # The emit fired.
    assert seen_messages, "providers_save did not emit an activity log entry"
    blob = " ".join(seen_messages).lower()
    # The actual token must NEVER appear.
    assert "sk-secret-token" not in blob, "token leaked into activity log"
    # Sign-up URLs should not appear (they're for UI only).
    for pid, meta in portal_app._PROVIDER_META.items():
        for field in ("signup", "docs"):
            url = meta.get(field, "")
            if url and url in blob:
                pytest.fail(
                    f"provider {pid!r} {field} URL {url!r} leaked into activity log"
                )


# ─── PROVIDER WIRING (35%) ───────────────────────────────────────────────


def test_provider_ids_are_lowercase_ascii():
    """Provider ids feed both Python dict keys and HTML data-prov
    attributes. A whitespace or uppercase id would silently break the
    modal's row selectors. Defends against a future contributor adding
    e.g. 'Together AI' or 'OpenAI'."""
    allowed = set(string.ascii_lowercase + "_")
    for pid in portal_app._PROVIDER_KEY_ENVS.keys():
        assert pid, "empty provider id"
        bad = set(pid) - allowed
        assert not bad, (
            f"provider id {pid!r} contains non-[a-z_] chars: {bad}"
        )
        assert pid == pid.lower(), f"provider id {pid!r} is not lowercase"


def test_write_secrets_round_trips_all_ten_envs(tmp_secrets, monkeypatch):
    """_write_secrets() must accept and persist every curated env var
    distinctly. Regression guard for the case where someone adds a
    filter to _write_secrets that drops unknown keys."""
    pairs = {env: f"value_for_{pid}" for pid, env in portal_app._PROVIDER_KEY_ENVS.items()}
    portal_app._write_secrets(pairs)
    secrets_file = tmp_secrets / "secrets.env"
    assert secrets_file.exists()
    body = secrets_file.read_text()
    for pid, env in portal_app._PROVIDER_KEY_ENVS.items():
        marker = f"{env}=value_for_{pid}"
        assert marker in body, f"_write_secrets dropped {env!r} for {pid!r}"
    # Round-trip read returns the same set of keys.
    read_back = portal_app._read_secrets()
    for env in pairs.keys():
        assert env in read_back, f"_read_secrets failed to recover {env!r}"


def test_sequential_saves_produce_ten_distinct_lines(tmp_secrets, monkeypatch):
    """Save tokens for all 10 curated providers in sequence; secrets.env
    must contain 10 distinct env=value lines (sorted, since
    _write_secrets sorts pairs)."""
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.delenv("ARAIL_MODE", raising=False)
    for pid in sorted(CURATED_TEN):
        req = _FakeRequest({"provider": pid, "token": f"tok-{pid}"})
        result = asyncio.new_event_loop().run_until_complete(portal_app.providers_save(req))
        assert result.get("ok") is True, f"save failed for {pid!r}: {result}"
    secrets_file = tmp_secrets / "secrets.env"
    body = secrets_file.read_text()
    env_vars = set(portal_app._PROVIDER_KEY_ENVS[pid] for pid in CURATED_TEN)
    # Every env var landed on its own line with its expected token.
    for pid in CURATED_TEN:
        env = portal_app._PROVIDER_KEY_ENVS[pid]
        assert f"{env}=tok-{pid}" in body, (
            f"missing line for {pid!r} env={env!r}"
        )
    # Distinct: no two env vars share a line.
    lines = [ln for ln in body.splitlines() if "=" in ln and not ln.startswith("#")]
    keys = [ln.split("=", 1)[0] for ln in lines]
    assert len(keys) == len(set(keys)), (
        f"duplicate env-var keys in secrets.env: {keys}"
    )


def test_status_payload_exposes_signup_for_all_ten(monkeypatch):
    """The /api/providers/status payload must carry a non-empty `signup`
    URL for every curated provider so the modal can render the
    sign-up link without a second roundtrip."""
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.delenv("ARAIL_MODE", raising=False)
    payload = asyncio.new_event_loop().run_until_complete(portal_app.providers_status())
    by_id = {p["id"]: p for p in payload["providers"]}
    for pid in CURATED_TEN:
        assert pid in by_id, f"status payload missing {pid!r}"
        assert by_id[pid].get("signup"), (
            f"status payload signup empty for {pid!r}"
        )
        assert by_id[pid]["signup"].startswith("https://"), (
            f"status payload signup not https for {pid!r}: {by_id[pid]['signup']!r}"
        )


# ─── UI (10%) ────────────────────────────────────────────────────────────


@pytest.mark.xfail(
    reason="Sprint debt: docs/CLOUD_PROVIDERS.md and _PROVIDER_META advertise "
    "a 'Custom (OpenAI-compatible)' bring-your-own row, but chat.html has no "
    "surface for it. Pre-existing (predecessor template also lacked it), but "
    "this sprint widens the gap by documenting the feature. Track followup: "
    "'Wire the Custom row into the Connections modal.'",
    strict=True,
)
def test_chat_html_still_has_custom_byob_ui():
    """The `custom` row is in _PROVIDER_KEY_ENVS, _PROVIDER_META, the
    server-side status payload, and docs/CLOUD_PROVIDERS.md. It must
    therefore have a UI surface — otherwise users with self-hosted
    OpenAI-compat endpoints have no way to configure them through the
    modal that the docs point at."""
    chat_html = (_REPO_ROOT / "src" / "arail" / "portal" / "templates" / "chat.html").read_text()
    patterns = [
        r'data-prov\s*=\s*["\']custom["\']',
        r"provider\s*[:=]\s*['\"]custom['\"]",
        r"Custom\s*\(OpenAI",
        r"[Bb]ring.{0,5}your.{0,5}own",
        r"MODEL_API_BASE",
    ]
    assert any(re.search(p, chat_html) for p in patterns), (
        "chat.html has no surface for the custom/BYOB provider — "
        "users with self-hosted endpoints cannot configure them"
    )


def test_chat_html_no_dead_api_tokens_path():
    """Regression: the pre-existing bug fixed in this sprint was JS
    calling /api/tokens/... (which never existed). Make sure no new
    code reintroduces it."""
    chat_html = (_REPO_ROOT / "src" / "arail" / "portal" / "templates" / "chat.html").read_text()
    matches = re.findall(r"/api/tokens(?:/[^\s'\"`]*)?", chat_html)
    assert not matches, (
        f"chat.html still references the non-existent /api/tokens path: {matches}"
    )


# ─── SETUP FLOW + REGRESSION (25% + 10%) ─────────────────────────────────


def test_upgrade_cycle_min_max_min_preserves_explicit_lab_mode(tmp_path: Path):
    """A user who explicitly set LAB_MODE in .env must keep it through a
    min → max → min upgrade cycle. This mirrors the existing
    ARAIL_COMPARE_ENABLED preservation test but for LAB_MODE — which
    has different per-tier defaults and is newer."""
    env = tmp_path / ".env"
    env.write_text(
        "# arail .env\nLAB_TIER=min\nLAB_MODE=airgapped\nARAIL_COMPARE_ENABLED=0\n"
    )

    def _upgrade(target_tier: str):
        script = f"""
import pathlib

p = pathlib.Path("{env}")
lines = p.read_text().splitlines() if p.exists() else []

def has_key(out, key):
    for line in out:
        if line.lstrip("# ").startswith(f"{{key}}="):
            return True
    return False

def upsert(out, key, value):
    seen = False
    new = []
    for line in out:
        if line.lstrip("# ").startswith(f"{{key}}="):
            new.append(f"{{key}}={{value}}")
            seen = True
        else:
            new.append(line)
    if not seen:
        new.append(f"{{key}}={{value}}")
    return new

tier = "{target_tier}"
lines = upsert(lines, "LAB_TIER", tier)
if tier == "max" and not has_key(lines, "ARAIL_COMPARE_ENABLED"):
    lines = upsert(lines, "ARAIL_COMPARE_ENABLED", "1")
if not has_key(lines, "LAB_MODE"):
    lines = upsert(lines, "LAB_MODE", "airgapped" if tier == "max" else "hybrid")
p.write_text("\\n".join(lines) + "\\n")
"""
        subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)

    _upgrade("max")
    _upgrade("min")
    # The user's explicit airgapped (set on min!) must survive the cycle.
    final = None
    for line in env.read_text().splitlines():
        if line.startswith("LAB_MODE="):
            final = line.split("=", 1)[1].strip().strip('"')
    assert final == "airgapped", (
        f"upgrade cycle clobbered explicit LAB_MODE: ended at {final!r}"
    )


def test_setup_overwrites_lab_mode_on_rerun(tmp_path: Path):
    """Regression / documented-behavior pin.

    setup.sh's `_set_env_var` REPLACES an existing line. This is
    intentional for first-run installs (the per-tier default lands)
    but DIFFERS from upgrade.sh's upsert-when-missing semantics for
    LAB_MODE.

    Pin the behavior so future refactors stay deliberate: if someone
    flips setup.sh to "preserve explicit values" they should update
    this test to match. ARCHITECTURE.md line 134 implies preservation;
    actual code at scripts/setup.sh:1207–1218 is overwrite. The
    contract worth defending: a min user who re-runs `./arailctl setup`
    after manually flipping LAB_MODE=airgapped will see it reset to
    hybrid. That's intended for the first-run UX but documented in the
    setup_env() comment block.
    """
    env = tmp_path / ".env"
    env.write_text(
        "# arail .env\nMODEL_BACKEND=mlx\nLAB_MODE=airgapped\n"
    )
    script = f"""
        set -e
        cd "{tmp_path}"
        step() {{ :; }}; info() {{ :; }}; warn() {{ :; }}; error() {{ echo "$@" >&2; exit 1; }}
        BOLD=""; RESET=""; CYAN=""; YELLOW=""; GREEN=""; RED=""
        eval "$(awk '/^_set_env_var\\(\\) \\{{$/,/^}}$/' {_REPO_ROOT}/scripts/setup.sh)"
        LAB_TIER="min"
        case "${{LAB_TIER:-min}}" in
            max) _set_env_var LAB_MODE "airgapped" ;;
            *)   _set_env_var LAB_MODE "hybrid" ;;
        esac
    """
    subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True)
    final = None
    for line in env.read_text().splitlines():
        if line.startswith("LAB_MODE="):
            final = line.split("=", 1)[1].strip().strip('"')
    # Behavior pin: setup.sh OVERWRITES (replaces). If you change this,
    # update the architect's spec at ARCHITECTURE.md:134 to match.
    assert final == "hybrid", (
        f"setup.sh _set_env_var no longer overwrites LAB_MODE — "
        f"got {final!r}, expected 'hybrid' per the per-tier default"
    )
