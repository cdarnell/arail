"""docs/concurrent-worlds.md must not contradict itself about in-place World
switching (REVIEW.md ASK-3): the doc claims removal at the API/UI layer while
`./arailctl world swap` remains a real, documented CLI-only escape hatch. The
doc must say so explicitly rather than leaving the two claims to collide.
"""
from __future__ import annotations

import pathlib

DOC = pathlib.Path(__file__).parent.parent / "docs" / "concurrent-worlds.md"


def test_doc_claims_removal_and_acknowledges_the_cli_verb():
    text = DOC.read_text(encoding="utf-8")
    assert "In-place World switching has been removed" in text
    # The CLI verb is real (arailctl:182, world_mount.py's `swap` subcommand)
    # and must be reconciled, not silently contradicted.
    assert "world swap" in text
    assert "CLI-only escape hatch" in text
