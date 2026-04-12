"""OGLab Model Router — unified interface across all backends."""

from __future__ import annotations

"""OGLab Model Router — init."""

from oglab.router.backends import ModelResponse
from oglab.router.core import ModelRouter

__all__ = ["ModelRouter", "ModelResponse"]
