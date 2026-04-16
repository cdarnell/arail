---
title: brand module
section: docs
tags: [python, module]
aliases: [brand, brand.py]
source: src/oglab/brand.py
generated: 2026-04-15T17:33:38Z
---

# brand module

**Source:** `src/oglab/brand.py`

OGLab brand layer — configurable per lab instance.

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

## Classes

### `Brand`

**Methods:**

- `to_dict(self)`

## Functions

### `load_brand()`

Read the brand from env vars. Safe to call from any context.

### `cached_brand()`

Process-wide brand cache. Tests that tweak env vars should call
:func:`reset_brand_cache` afterwards.

### `reset_brand_cache()`

Invalidate the cached brand — call this after changing env vars
at runtime (tests, a future /api/brand/update endpoint, etc.).
