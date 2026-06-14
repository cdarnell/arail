"""Capability error hierarchy.

All carry a ``.user_message`` attribute (operator-actionable), mirroring the
``world_mount.BundleError`` convention so the portal can surface a clean
message instead of a 500-with-traceback.
"""

from __future__ import annotations


class CapabilityError(Exception):
    """Base for all capability errors. ``.user_message`` is operator-actionable."""

    def __init__(self, message: str, *, user_message: str | None = None):
        super().__init__(message)
        self.user_message = user_message or message


class CapabilityUnavailable(CapabilityError):
    """A capability is declared/registered but cannot run on this host right now.

    Examples: wrong platform, missing Apple CLT, TCC permission denied, no
    on-device model. Maps to a 409 at the portal — the lab keeps working.
    """


class CapabilityNotImplemented(CapabilityUnavailable):
    """A backend is registered (so the platform is selectable) but has no
    implementation yet — e.g. the Linux STT stub. A subclass of
    CapabilityUnavailable so callers that catch the broader type still work."""
