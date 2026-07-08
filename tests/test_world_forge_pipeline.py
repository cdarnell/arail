"""forge_world pipeline tests with a deterministic FakeRouter.

The FakeRouter scripts responses by prompt shape (the stage is recognizable
from the ported prompt text), including the 1B-garbage cases the real spike
documented: non-JSON, arrays wrapped under random keys, one-token shorts.
"""

from __future__ import annotations

import json
import threading

import pytest

from arail.world_forge import (
    ForgeCancelled,
    ForgeParams,
    GateRefused,
    forge_world,
)


class FakeResponse:
    def __init__(self, text, model="qwen2.5:7b"):
        self.text = text
        self.model = model


class FakeRouter:
    """Answers by matching the stage from the prompt text."""

    def __init__(self, garbage_mode=False):
        self.garbage = garbage_mode
        self.calls = []

    def complete(self, prompt, **kw):
        self.calls.append(prompt)
        if "mapping the subject" in prompt:                       # SPEC
            if self.garbage:
                # array wrapped under a random key + junk prose around it
                return FakeResponse('Here you go: {"stuff": [{"id": "Basics!", "label": "Basics"}, {"id": "tools", "label": "Tools"}]}')
            return FakeResponse(json.dumps({"categories": [
                {"id": "basics", "label": "Basics"}, {"id": "tools", "label": "Tools"}]}))
        if "key concepts" in prompt:                              # SEED
            if "Basics" in prompt:
                return FakeResponse(json.dumps({"terms": [{"term": "Alpha"}, {"term": "Beta"}]}))
            return FakeResponse(json.dumps({"terms": [{"term": "Gamma"}]}))
        if "directly-associated concepts" in prompt:              # DISCOVER
            if self.garbage:
                return FakeResponse("I'm sorry, I can't do that")   # non-JSON → skip
            if '"Alpha"' in prompt:
                return FakeResponse(json.dumps({"related": [{"term": "Delta"}]}))
            return FakeResponse(json.dumps({"related": []}))
        if "THIS list of known concepts" in prompt:               # LINK
            # Suggest one legit slug + one hallucinated one (must be dropped).
            return FakeResponse(json.dumps({"related": ["alpha", "not-a-real-slug"]}))
        if "Define the concept" in prompt:                        # DEFINE
            if self.garbage:
                return FakeResponse(json.dumps({"short": "A", "definition": "A real definition sentence.", "example": "ex"}))
            return FakeResponse(json.dumps({
                "short": "a one-line short", "definition": "Two sentences. Of prose.",
                "example": "an example"}))
        return FakeResponse("{}")


def test_happy_path_forges_a_gated_world():
    r = forge_world(ForgeParams("test subject", "test-subject", max_terms=10),
                    router=FakeRouter())
    assert r.gate.ok
    assert r.tier == "model-asserted"
    assert r.source_tag == "model:qwen2.5/7b"          # :7b normalized to /7b
    slugs = {t["slug"] for t in r.terms}
    assert {"alpha", "beta", "gamma"} <= slugs
    assert "delta" in slugs                            # BFS discovery worked
    for t in r.terms:
        assert t["source"] == "model:qwen2.5/7b"
        assert t["definition"]
        assert "not-a-real-slug" not in t["related"]   # LINK only accepts known slugs
    alpha = next(t for t in r.terms if t["slug"] == "alpha")
    assert alpha["related"] == []                      # self-link excluded... beta/gamma link to alpha
    linked = [t for t in r.terms if "alpha" in t["related"]]
    assert linked                                       # graph is dense-ish
    assert r.spec["display_name"] == "Test Subject"
    assert r.spec["categories"][0]["id"] == "basics"
    assert r.stats["total"] == len(r.terms)


def test_survives_1b_garbage_and_still_gates():
    r = forge_world(ForgeParams("messy subject", "messy", max_terms=8),
                    router=FakeRouter(garbage_mode=True))
    assert r.gate.ok                                   # closed + sourced despite garbage
    assert r.stats["repair_events"] >= 1               # the non-JSON DISCOVER answers
    for t in r.terms:
        # one-token short ("A") falls back to the definition
        assert len(t["short"]) >= 3


def test_cancellation_raises_before_next_call():
    evt = threading.Event()

    class CancellingRouter(FakeRouter):
        def complete(self, prompt, **kw):
            resp = super().complete(prompt, **kw)
            if len(self.calls) >= 2:
                evt.set()                              # cancel after 2 calls
            return resp

    with pytest.raises(ForgeCancelled):
        forge_world(ForgeParams("s", "s", max_terms=10),
                    router=CancellingRouter(), cancel=evt)


def test_nothing_usable_raises_gate_refused():
    class EmptyRouter:
        def complete(self, prompt, **kw):
            return FakeResponse("nonsense that is not json")

    with pytest.raises(GateRefused):
        forge_world(ForgeParams("s", "s", max_terms=10), router=EmptyRouter())


def test_progress_callback_fires_and_never_kills_the_run():
    stages = []

    def cb(stage, done, total, note):
        stages.append(stage)
        raise RuntimeError("a broken progress consumer")   # must be swallowed

    r = forge_world(ForgeParams("s", "s", max_terms=10), router=FakeRouter(),
                    progress_cb=cb)
    assert r.gate.ok
    for expected in ("spec", "seed", "discover", "link", "define", "gate"):
        assert expected in stages


def test_params_normalization_and_knob_mapping():
    p = ForgeParams("  A Subject  ", "", max_terms=999).normalized()
    assert p.slug == "a-subject"
    assert p.max_terms == 150
    assert p.n_categories == 6 and p.n_seeds == 5
    p = ForgeParams("x", "x", max_terms=25).normalized()
    assert p.n_categories == 4 and p.n_seeds == 3
    p = ForgeParams("x", "x", max_terms=50).normalized()
    assert p.n_categories == 5 and p.n_seeds == 4
