"""arail.capabilities — declared-need → resolved-adapter capability engine.

Importing this package registers all backends (macOS + Linux) into the
``registry`` singleton. Callers go through ``registry`` /
``resolve_capabilities`` / the adapter ABCs only — never a backend module —
which keeps the system Linux-ready by construction (WC-B).
"""

from __future__ import annotations

from .adapter import Adapter, AudioCaptureAdapter, SpeechToTextAdapter
from .errors import CapabilityError, CapabilityNotImplemented, CapabilityUnavailable
from .resolve import ResolvedCapability, resolve_capabilities
from .spec import CapabilitySpec, MalformedCapabilities, parse_capabilities_file
from . import registry

# Register backends at import. Each backend module calls registry.register(...)
# at module scope. Import is side-effecting and intentional.
from .backends import macos as _macos  # noqa: E402,F401
from .backends import linux as _linux  # noqa: E402,F401

__all__ = [
    "Adapter",
    "AudioCaptureAdapter",
    "SpeechToTextAdapter",
    "CapabilitySpec",
    "MalformedCapabilities",
    "parse_capabilities_file",
    "ResolvedCapability",
    "resolve_capabilities",
    "CapabilityError",
    "CapabilityUnavailable",
    "CapabilityNotImplemented",
    "registry",
]
