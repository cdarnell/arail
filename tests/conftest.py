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


@pytest.fixture(autouse=True)
def _arail_password_for_tests(monkeypatch):
    """Set a non-placeholder ARAIL_PASSWORD for every test by default.

    Onboarding-flow tests can monkeypatch this back if they want to
    exercise the no-password code path.
    """
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
