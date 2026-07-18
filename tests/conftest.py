"""Pytest fixtures shared by every test in this suite.

The portal middleware redirects unauthenticated requests to /welcome
when ARAIL_PASSWORD is missing/placeholder. Tests instantiate the app
directly via TestClient and don't go through setup, so we plant a
real-looking password into the environment for the test session.

Tests that specifically want to exercise the onboarding flow can
monkeypatch the env var back to empty.
"""

from __future__ import annotations

import os
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Session-level .env isolation — MUST run before any `import arail.*`.
#
# arail.config calls load_dotenv() at import time. Without ARAIL_ENV_FILE it
# uses python-dotenv's walk-up search, which escapes the checkout (a git
# worktree finds the parent repo's real .env) and hydrates the developer's
# lab config (LAB_INTENT, LAB_MODE, COMPUTE_SOURCE, ...) into the test
# process at collection time — the tests then behave differently than CI.
# Point it at a file that does not exist inside a session tmp dir so the
# import-time load is a no-op. The autouse fixture below re-points it at a
# per-test tmp file for endpoints that WRITE the .env (welcome, airgap
# toggle), so no test can touch a real checkout's .env either.
# ---------------------------------------------------------------------------
_SESSION_ENV_DIR = tempfile.mkdtemp(prefix="arail-pytest-env-")
os.environ["ARAIL_ENV_FILE"] = os.path.join(_SESSION_ENV_DIR, "portal.env")
os.environ["ARAIL_AIRGAP_AUDIT_FILE"] = os.path.join(
    _SESSION_ENV_DIR, "airgap_audit.jsonl"
)
os.environ["ARAIL_SECRETS_FILE"] = os.path.join(_SESSION_ENV_DIR, "secrets.env")


@pytest.fixture
def isolated_secrets(monkeypatch, tmp_path):
    """Redirect the portal's secrets file to a tmp path and restore env on teardown.

    Any test that calls an endpoint that writes lab/data/secrets.env (e.g.
    POST /api/chat/default, POST /api/providers/save) must use this fixture so it
    never clobbers a developer's real secrets and never leaks COMPUTE_SOURCE /
    ARAIL_CHAT_DEFAULT_MODEL / ARAIL_MODEL_CTX_OVERRIDES into the process for
    downstream tests.

    The fixture:
      1. Monkeypatches portal_app._secrets_path to return a tmp file.
      2. Deletes the three polluting env keys before the test runs.
      3. After the test, restores any values those keys had — the endpoint
         writes os.environ directly (bypassing monkeypatch), so we must
         restore by hand in teardown.
    """
    from arail.portal import app as portal_app

    fake = tmp_path / "secrets.env"
    monkeypatch.setattr(portal_app, "_secrets_path", lambda: fake)

    _leaky = ("COMPUTE_SOURCE", "ARAIL_CHAT_DEFAULT_MODEL", "ARAIL_MODEL_CTX_OVERRIDES")
    _saved = {k: os.environ.get(k) for k in _leaky}
    for k in _leaky:
        monkeypatch.delenv(k, raising=False)

    yield fake

    # The endpoint writes os.environ directly — monkeypatch won't clean those up.
    for k, v in _saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(autouse=True)
def _isolated_env_file(monkeypatch, tmp_path):
    """Point the portal's .env (and airgap audit log) at per-test tmp files.

    ARAIL_ENV_FILE is honored by arail.config's load_dotenv, the onboarding
    writer/reader (_write_env_kv / _lab_password_set), and the airgap
    toggle's _toggle_env_path — so a test that hits POST /api/airgap/toggle
    or /api/welcome/setup without further setup writes tmp files instead of
    the developer's real .env / lab/data/airgap_audit.jsonl. Tests that
    monkeypatch app._TOGGLE_ENV_PATH / _TOGGLE_AUDIT_PATH still win (the
    module override takes precedence); tests that want a specific path can
    setenv ARAIL_ENV_FILE themselves (their setenv runs after this one).
    """
    monkeypatch.setenv("ARAIL_ENV_FILE", str(tmp_path / "portal.env"))
    monkeypatch.setenv(
        "ARAIL_AIRGAP_AUDIT_FILE", str(tmp_path / "airgap_audit.jsonl")
    )
    # Same treatment for the provider-token store: endpoints that persist
    # tokens / chat defaults (POST /api/providers/save, /api/chat/default)
    # must never rewrite a developer's real lab/data/secrets.env. Tests that
    # use the isolated_secrets fixture replace _secrets_path wholesale, which
    # still takes precedence over this env default.
    monkeypatch.setenv("ARAIL_SECRETS_FILE", str(tmp_path / "secrets.env"))


@pytest.fixture(autouse=True)
def _no_ambient_lab_mode_env(monkeypatch):
    """Delete (and restore after the test) the lab-mode/identity env keys.

    Two leak classes this closes:
      1. Ambient values from the developer's shell (arailctl sources .env)
         — e.g. LAB_INTENT=other flips identity defaults the tests assume.
      2. Endpoints that write os.environ directly (the airgap toggle sets
         LAB_MODE/ARAIL_MODE, /api/welcome/setup sets LAB_NAME and
         OPEN_NOTEBOOK_ENCRYPTION_KEY) — monkeypatch snapshots the pre-test
         state here and restores it on teardown, so a hybrid toggle in one
         test can't make lab_mode() report hybrid in the next.

    Tests that need one of these set use monkeypatch.setenv in their own
    body/fixture, which runs after this autouse fixture and wins.
    """
    for key in (
        "LAB_MODE",
        "ARAIL_MODE",
        "LAB_INTENT",
        "LAB_INTENT_NAME",
        "LAB_INTENT_DESCRIPTION",
        "LAB_NAME",
        "OPEN_NOTEBOOK_ENCRYPTION_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _arail_password_for_tests(monkeypatch):
    """Set a non-placeholder ARAIL_PASSWORD for every test by default.

    Onboarding-flow tests can monkeypatch this back if they want to
    exercise the no-password code path.
    """
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")


@pytest.fixture(autouse=True)
def _allow_testclient_host(monkeypatch):
    """Let Starlette TestClient's default ``Host: testserver`` through the
    local_trust_boundary middleware (anti-DNS-rebinding Host allowlist).

    In production only loopback names pass; `testserver` is a synthetic
    host a real browser can never send while connecting to the lab, so
    allowing it in tests creates no attack surface. Tests that want to
    exercise a rejected Host monkeypatch this back or pass an explicit
    non-loopback Host header.
    """
    monkeypatch.setenv("ARAIL_ALLOWED_HOSTS", "testserver")


@pytest.fixture(autouse=True)
def _no_ambient_window_override(monkeypatch, tmp_path_factory):
    """Isolate the persisted work-window override per test.

    ``scheduler.current_window()`` now consults a persisted override
    (``lab/data/window_override.json``). Without isolation a developer's
    (or another test's) ambient override leaks into every scheduler
    consumer and makes unrelated tests non-deterministic. Point the
    override file at a fresh tmp path and clear in-memory state.
    """
    from arail import scheduler
    d = tmp_path_factory.mktemp("window_override")
    monkeypatch.setattr(scheduler, "_override_path", lambda: d / "window_override.json")
    scheduler._reset_window_override_for_tests()


@pytest.fixture(autouse=True)
def _no_ambient_halt_flag(monkeypatch, tmp_path_factory):
    """Isolate the persisted halt flag per test (same rationale as the
    window override above — a developer's halted lab must not leak into
    tests, and a test that halts must not halt the developer's lab)."""
    from arail import scheduler
    d = tmp_path_factory.mktemp("halt_flag")
    monkeypatch.setattr(scheduler, "_halt_path", lambda: d / "halt.json")
    scheduler._reset_halt_for_tests()


@pytest.fixture(autouse=True)
def _no_ambient_world_mount(monkeypatch, tmp_path_factory):
    """Hide any World a developer has mounted on this machine from the tests.

    The portal endpoints / Buddy resolve the mount via
    ``world_mount.current_mount()`` (no arg) → ``_default_data_dir()`` → the
    real ``lab/data``. If a developer has run ``./arailctl world mount`` (e.g.
    the physics World), that ambient state leaks into unrelated portal tests and
    makes them non-deterministic — CI passes only because ``lab/`` is
    git-ignored. We point the *default* data dir at a fresh empty directory, so
    the ambient lookup finds nothing mounted. Tests that set up their own mount
    re-``monkeypatch.setattr(world_mount, "_default_data_dir", ...)`` in their
    body (same monkeypatch instance → their override wins), and tests that pass
    an explicit ``current_mount(data_dir=...)`` are unaffected.
    """
    try:
        from arail import world_mount
    except Exception:  # noqa: BLE001
        return  # feature not importable in this context → nothing to isolate

    clean = tmp_path_factory.mktemp("no-ambient-world")
    monkeypatch.setattr(world_mount, "_default_data_dir", lambda: clean)
    # Also isolate the catalog dir: mount() now adopts a byte-copy of each
    # bundle into WORLDS_DIR so it survives unmount. Point that at a fresh
    # empty dir so tests never write into the real repo lab/worlds/ (and so a
    # developer's ambient catalog can't leak into listing tests). Tests that
    # need their own catalog override _default_worlds_dir in their own body.
    clean_worlds = tmp_path_factory.mktemp("no-ambient-worlds-dir")
    monkeypatch.setattr(world_mount, "_default_worlds_dir", lambda: clean_worlds)


@pytest.fixture(autouse=True)
def _reset_egress_guard():
    """Reset the egress guard to un-installed state between tests.

    The guard monkey-patches ``requests.adapters.HTTPAdapter`` and the
    urllib opener.  Without this reset, a test that calls
    ``install_guard()`` would poison every subsequent test that creates a
    ``requests.Session()``.

    This fixture runs after each test (teardown phase) so the guard can
    be inspected in post-test assertions before reset.
    """
    yield
    try:
        import arail.egress
        arail.egress._reset_for_tests()
    except Exception:  # noqa: BLE001
        pass  # If egress hasn't been imported yet, nothing to reset.
