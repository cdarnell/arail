"""Brand layer — configurable per lab instance.

The blueprint's default display name is **Autoresearch AI Lab**. When an
operator forks this repo and runs ``./lab setup`` they can rename the lab to
anything they want (``Sam's AI Lab``, ``gentoofoo's ai lab``, ``PeanutLab``,
``glassblowing-lab``) and every user-facing string picks up the new name
without touching code.

The internal Python package name stays ``arail`` so the installable entry
point is stable, but everything a user *sees* — the portal title, dashboard
logo, nav bar, activity log, setup banner, status card, wiki landing page —
reads from these env vars.

Fields:
    name        Display name           ``LAB_NAME``        (default: "Autoresearch AI Lab")
    short_name  Lowercase short        ``LAB_SHORT_NAME``  (default: "autoresearch-lab")
    tagline     One-line description   ``LAB_TAGLINE``     (default: "A learn-by-doing AI research lab")
    logo        Nav-bar glyph+name     ``LAB_LOGO``        (default: "⟨Autoresearch⟩")
    version     From ``arail.__version__`` (not configurable)

To rebrand to your own lab:

    echo 'LAB_NAME="Sam''s AI Lab"'          >> .env
    echo 'LAB_SHORT_NAME="sams-lab"'         >> .env
    echo 'LAB_TAGLINE="Our family AI bench"' >> .env

Then ``./lab start`` — every template, every activity event, every status
banner now says "Sam's AI Lab". The logo falls back to ``⟨{name}⟩`` if you
don't override it explicitly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


DEFAULT_NAME = "Autoresearch AI Lab"
DEFAULT_SHORT_NAME = "autoresearch-lab"
DEFAULT_TAGLINE = "A learn-by-doing AI research lab"
DEFAULT_LOGO_TEMPLATE = "⟨Autoresearch⟩"


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
        from arail import __version__
        return __version__
    except Exception:  # pragma: no cover
        return "0.0.0"


def _default_short_name(name: str) -> str:
    if name == DEFAULT_NAME:
        return DEFAULT_SHORT_NAME
    return name.lower().replace(" ", "-").replace("'", "")


def _default_logo(name: str) -> str:
    if name == DEFAULT_NAME:
        return DEFAULT_LOGO_TEMPLATE
    return f"⟨{name}⟩"


def load_brand() -> Brand:
    """Read the brand from env vars. Safe to call from any context."""
    name = os.getenv("LAB_NAME", DEFAULT_NAME)
    short_name = os.getenv("LAB_SHORT_NAME", _default_short_name(name))
    tagline = os.getenv("LAB_TAGLINE", DEFAULT_TAGLINE)
    logo = os.getenv("LAB_LOGO", _default_logo(name))
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
