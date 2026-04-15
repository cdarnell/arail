"""OGLab brand layer — configurable per lab instance.

When a user forks this blueprint and runs ``./oglab setup``, they can
rename the lab to anything they want (``MyLab``, ``PeanutLab``,
``glassblowing-lab``) and every user-facing string picks up the new
name without touching code. The Python package name stays ``oglab``
so the installable entry point is stable, but everything a user sees —
the portal title, dashboard logo, nav bar, activity log, setup banner,
status card, wiki landing page — reads from these env vars.

Fields:
    name        Display name           ``LAB_NAME``        (default: "OGLab")
    short_name  Lowercase short         ``LAB_SHORT_NAME``  (default: "oglab")
    tagline     One-line description    ``LAB_TAGLINE``     (default: "AI Lab Blueprint")
    logo        Nav-bar glyph+name      ``LAB_LOGO``        (default: "⟨OGLab⟩")
    version     From ``oglab.__version__`` (not configurable)

To rebrand:

    echo 'LAB_NAME="PeanutLab"' >> .env
    echo 'LAB_SHORT_NAME="peanutlab"' >> .env
    echo 'LAB_TAGLINE="Grow more peanuts"' >> .env

Then ``./oglab start`` — every template, every activity event, every
status banner now says PeanutLab. The logo falls back to
``⟨{name}⟩`` if you don't override it explicitly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Brand:
    name: str
    short_name: str
    tagline: str
    logo: str
    version: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "short_name": self.short_name,
            "tagline": self.tagline,
            "logo": self.logo,
            "version": self.version,
        }


def _version() -> str:
    try:
        from oglab import __version__
        return __version__
    except Exception:  # pragma: no cover
        return "0.0.0"


def load_brand() -> Brand:
    """Read the brand from env vars. Safe to call from any context."""
    name = os.getenv("LAB_NAME", "OGLab")
    short_name = os.getenv("LAB_SHORT_NAME", name.lower().replace(" ", "-"))
    tagline = os.getenv("LAB_TAGLINE", "AI Lab Blueprint")
    logo = os.getenv("LAB_LOGO", f"⟨{name}⟩")
    return Brand(
        name=name,
        short_name=short_name,
        tagline=tagline,
        logo=logo,
        version=_version(),
    )


@lru_cache(maxsize=1)
def cached_brand() -> Brand:
    """Process-wide brand cache. Tests that tweak env vars should call
    :func:`reset_brand_cache` afterwards."""
    return load_brand()


def reset_brand_cache() -> None:
    """Invalidate the cached brand — call this after changing env vars
    at runtime (tests, a future /api/brand/update endpoint, etc.)."""
    cached_brand.cache_clear()
