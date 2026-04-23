"""Arail Model Router — unified interface across all backends."""

from __future__ import annotations

"""Arail Model Router — init."""

from arail.router.backends import ModelResponse
from arail.router.core import ModelRouter

__all__ = ["ModelRouter", "ModelResponse"]
