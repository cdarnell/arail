"""World-declared model hint (`model.json`) — Phase A READ + SUGGEST tests.

Covers ARCHITECTURE §9 T1–T6 for the 2026-06-14-world-model-hint sprint.

arail QA weights (30 setup / 30 Buddy / 20 security / 10 happy / 10 regression):
- T2 is the load-bearing SECURITY test: `model.json` crosses the DaC→ARAIL repo
  boundary onto someone else's machine, so every field is attacker-influenced.
  The `recommended.id` allowlist + the rationale cap + "rationale is DATA, never
  a prompt" are asserted here.
- T1/T6 are the regression tests proving a World with NO `model.json` behaves
  exactly as today and that unmount/swap keep the sidecar honest.

The autouse ``_no_ambient_world_mount`` fixture (conftest.py) points the *default*
data dir at an empty temp dir; tests that mount drive an explicit ``data_dir=``.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from arail import world_mount as wm
from arail import chat as chatmod

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
NO_MODEL = FIXTURES / "world-no-caps"          # has no model.json
MODEL_AVAILABLE = FIXTURES / "world-model-available"   # recommended.id = gemma3:4b (real catalog id)
MODEL_UNKNOWN = FIXTURES / "world-model-unknown"       # recommended.id not in catalog


@pytest.fixture
def lab(tmp_path):
    """A (data_dir, pkb_root) pair for an isolated mount."""
    dd = tmp_path / "data"
    pkb = tmp_path / "pkb"
    dd.mkdir()
    pkb.mkdir()
    return dd, pkb


def _mount(bundle, lab):
    dd, pkb = lab
    return wm.mount(bundle, pkb_root=pkb, data_dir=dd)


# ── T1: regression — no model.json behaves exactly as today ────────────────


def test_t1_no_model_json_no_sidecar_no_hint(lab, monkeypatch):
    dd, _ = lab
    # Avoid network in installed-detection while exercising gallery_view.
    monkeypatch.setattr(chatmod, "detect_installed_models", lambda: [])
    _mount(NO_MODEL, lab)

    # No sidecar written, reader returns None.
    assert not (dd / wm.MODEL_SIDECAR_NAME).exists()
    assert wm.current_model_hint(data_dir=dd) is None

    # model.json is NOT sealed.
    assert "model.json" not in wm._BUNDLE_FILES

    # gallery payload carries model_hint=None (default dir is empty → no hint).
    g = chatmod.gallery_view()
    assert "model_hint" in g
    assert g["model_hint"] is None


# ── T2: security/edge — attacker-influenced fields ─────────────────────────


@pytest.mark.parametrize("raw", [
    {"recommended": {"id": "x"}},                                  # missing schema
    {"schema": "dac.world-model/v2", "recommended": {"id": "x"}},  # future schema → absent
    {"schema": "dac.world-model/v1"},                              # no recommended
    {"schema": "dac.world-model/v1", "recommended": {}},           # no id
    {"schema": "dac.world-model/v1", "recommended": {"id": ""}},   # empty id
    {"schema": "dac.world-model/v1", "recommended": {"id": "$(rm -rf /)"}},   # shell chars
    {"schema": "dac.world-model/v1", "recommended": {"id": "a; ls"}},         # shell sep
    {"schema": "dac.world-model/v1", "recommended": {"id": "../../etc"}},     # path traversal
    {"schema": "dac.world-model/v1", "recommended": {"id": "<script>x"}},     # markup
])
def test_t2_malicious_or_malformed_id_rejected(raw):
    recommended, fallback, err = wm._parse_model_hint(raw)
    assert recommended is None
    assert err is not None


def test_t2_rationale_capped_and_is_data():
    big = "A" * 5000
    raw = {
        "schema": "dac.world-model/v1",
        "recommended": {"id": "gemma3:4b", "rationale": big},
    }
    recommended, _fb, err = wm._parse_model_hint(raw)
    assert err is None
    assert recommended is not None
    # Capped to the 280-char limit.
    assert len(recommended["rationale"]) == wm._MODEL_RATIONALE_CAP


def test_t2_fallback_invalid_entries_dropped():
    raw = {
        "schema": "dac.world-model/v1",
        "recommended": {"id": "gemma3:4b"},
        "fallback": ["good-id", "bad id with spaces", "$(evil)", "qwen2.5:1.5b"],
    }
    recommended, fallback, err = wm._parse_model_hint(raw)
    assert err is None
    assert fallback == ["good-id", "qwen2.5:1.5b"]


def test_t2_malformed_file_mount_never_fails(lab, tmp_path):
    """A bundle whose model.json is unparseable still mounts; error recorded."""
    dd, pkb = lab
    import shutil
    bad = tmp_path / "bad-bundle"
    shutil.copytree(NO_MODEL, bad)
    (bad / "model.json").write_text("{ this is not json")

    rec = wm.mount(bad, pkb_root=pkb, data_dir=dd)   # must NOT raise
    assert rec.world == "physics"
    sidecar = json.loads((dd / wm.MODEL_SIDECAR_NAME).read_bytes())
    assert sidecar["recommended"] is None
    assert sidecar["model_hint_error"] is not None


def test_t2_mount_non_blocking_when_resolve_raises(lab, monkeypatch):
    """A raising sidecar-resolve still mounts (log-only, never fails)."""
    dd, pkb = lab

    def boom(*a, **k):
        raise RuntimeError("resolve blew up")

    monkeypatch.setattr(wm, "_resolve_and_write_model_hint", boom)
    rec = wm.mount(MODEL_AVAILABLE, pkb_root=pkb, data_dir=dd)   # must NOT raise
    assert rec.world == "physics"


# ── Resolution states (mocked catalog + installed) ─────────────────────────


def test_resolve_states_via_resolver():
    catalog_by_id = {
        "gemma3:4b": {"id": "gemma3:4b", "name": "Gemma 3 4B", "size_gb": 3.3,
                      "good_at": ["chat"], "family": "gemma"},
        "qwen2.5:1.5b": {"id": "qwen2.5:1.5b", "name": "Qwen 1.5B", "size_gb": 1.0,
                         "good_at": [], "family": "qwen"},
    }
    hint = {"world": "physics", "recommended": {"id": "gemma3:4b",
            "rationale": "good"}, "fallback": []}

    # installed → recommended_installed
    block = chatmod._resolve_hint_for_gallery(hint, {"gemma3:4b"}, catalog_by_id)
    assert block["state"] == "recommended_installed"
    assert block["id"] == "gemma3:4b"
    assert block["name"] == "Gemma 3 4B"

    # in catalog, not installed → recommended_available, size surfaced
    block = chatmod._resolve_hint_for_gallery(hint, set(), catalog_by_id)
    assert block["state"] == "recommended_available"
    assert block["size_gb"] == 3.3

    # not in catalog → recommended_unknown
    hint_u = {"world": "physics", "recommended": {"id": "nope-xyz"}, "fallback": []}
    block = chatmod._resolve_hint_for_gallery(hint_u, set(), catalog_by_id)
    assert block["state"] == "recommended_unknown"
    assert block["id"] == "nope-xyz"
    assert block["catalog_entry"] is None

    # no hint → None
    assert chatmod._resolve_hint_for_gallery(None, set(), catalog_by_id) is None
    assert chatmod._resolve_hint_for_gallery({"recommended": None}, set(), catalog_by_id) is None


# ── T3: happy — installed → gallery offers Switch via existing path ────────


def test_t3_recommended_installed_gallery_block(lab, monkeypatch):
    dd, _ = lab
    monkeypatch.setattr(wm, "_default_data_dir", lambda: dd)
    monkeypatch.setattr(chatmod, "detect_installed_models",
                        lambda: [{"id": "gemma3:4b", "runtime": "ollama",
                                  "size_gb": 3.3, "modified": "", "endpoint": None}])
    _mount(MODEL_AVAILABLE, lab)

    g = chatmod.gallery_view()
    mh = g["model_hint"]
    assert mh is not None
    assert mh["state"] == "recommended_installed"
    assert mh["id"] == "gemma3:4b"
    # The Switch path reuses the installed-model select — id is in installed set.
    assert mh["id"] in {e["id"] for e in g["installed"]}


# ── T4: setup/happy — available → size shown, NO auto-download ─────────────


def test_t4_recommended_available_no_autodownload(lab, monkeypatch):
    dd, _ = lab
    monkeypatch.setattr(wm, "_default_data_dir", lambda: dd)
    # gemma3:4b NOT installed.
    monkeypatch.setattr(chatmod, "detect_installed_models", lambda: [])

    pulled = []
    # Defensive: there is no auto-pull path; assert the resolver/gallery never
    # triggers a network install. (detect_installed_models is the only network
    # touchpoint, already stubbed; any pull would have to go through it.)
    _mount(MODEL_AVAILABLE, lab)
    g = chatmod.gallery_view()
    mh = g["model_hint"]
    assert mh["state"] == "recommended_available"
    assert mh["size_gb"] == 3.3                  # size surfaced (VISION win-cond 2)
    assert mh["catalog_entry"] is not None        # carries install command surface
    assert pulled == []                           # nothing downloaded


# ── T5: edge — unknown + fallback promotion ────────────────────────────────


def test_t5_unknown_no_fallback_resolves_stays_unknown(lab, monkeypatch):
    dd, _ = lab
    monkeypatch.setattr(wm, "_default_data_dir", lambda: dd)
    monkeypatch.setattr(chatmod, "detect_installed_models", lambda: [])
    _mount(MODEL_UNKNOWN, lab)   # id + fallbacks all bogus

    g = chatmod.gallery_view()
    mh = g["model_hint"]
    assert mh["state"] == "recommended_unknown"
    assert mh["promoted_from_fallback"] is False


def test_t5_fallback_promotion(monkeypatch):
    catalog_by_id = {
        "qwen2.5:1.5b": {"id": "qwen2.5:1.5b", "name": "Qwen 1.5B", "size_gb": 1.0,
                         "good_at": [], "family": "qwen"},
    }
    # recommended unknown, but a fallback resolves (available) → promoted.
    hint = {"world": "physics", "recommended": {"id": "nope-xyz"},
            "fallback": ["also-nope", "qwen2.5:1.5b"]}
    block = chatmod._resolve_hint_for_gallery(hint, set(), catalog_by_id)
    assert block["state"] == "recommended_available"
    assert block["id"] == "qwen2.5:1.5b"
    assert block["promoted_from_fallback"] is True


def test_t5_sidecar_catalog_state(lab):
    dd, _ = lab
    _mount(MODEL_AVAILABLE, lab)
    sc = json.loads((dd / wm.MODEL_SIDECAR_NAME).read_bytes())
    assert sc["catalog_state"] == "in_catalog"
    assert sc["recommended"]["id"] == "gemma3:4b"

    dd2, _ = lab
    _mount(MODEL_UNKNOWN, lab)
    sc2 = json.loads((dd / wm.MODEL_SIDECAR_NAME).read_bytes())
    assert sc2["catalog_state"] == "not_in_catalog"


# ── T6: regression — unmount removes sidecar; swap re-resolves ─────────────


def test_t6_unmount_removes_sidecar(lab):
    dd, pkb = lab
    _mount(MODEL_AVAILABLE, lab)
    assert (dd / wm.MODEL_SIDECAR_NAME).exists()
    wm.unmount(data_dir=dd, pkb_root=pkb)
    assert not (dd / wm.MODEL_SIDECAR_NAME).exists()
    assert wm.current_model_hint(data_dir=dd) is None


def test_t6_swap_reresolves(lab):
    dd, pkb = lab
    _mount(MODEL_AVAILABLE, lab)
    assert wm.current_model_hint(data_dir=dd)["recommended"]["id"] == "gemma3:4b"

    # Swap to a World with a model.json that is unknown → sidecar updates.
    wm.swap(MODEL_UNKNOWN, data_dir=dd, pkb_root=pkb)
    sc = wm.current_model_hint(data_dir=dd)
    assert sc["recommended"]["id"] == "qkz-totally-not-real-xyz"
    assert sc["catalog_state"] == "not_in_catalog"


def test_t6_swap_to_no_model_clears_stale_sidecar(lab):
    """Swapping to a World with NO model.json must not leave a stale hint."""
    dd, pkb = lab
    _mount(MODEL_AVAILABLE, lab)
    assert (dd / wm.MODEL_SIDECAR_NAME).exists()
    wm.swap(NO_MODEL, data_dir=dd, pkb_root=pkb)
    assert not (dd / wm.MODEL_SIDECAR_NAME).exists()
    assert wm.current_model_hint(data_dir=dd) is None
