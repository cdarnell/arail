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

import pytest


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
def _arail_password_for_tests(monkeypatch):
    """Set a non-placeholder ARAIL_PASSWORD for every test by default.

    Onboarding-flow tests can monkeypatch this back if they want to
    exercise the no-password code path.
    """
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")


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
