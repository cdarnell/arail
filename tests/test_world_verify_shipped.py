"""verify_shipped_worlds + the `verify-shipped` CLI command.

The vendored-bundle integrity check behind:
  - ./arailctl world verify-shipped   (operator check)
  - setup.sh step 11                  (warn-not-abort)
  - portal _startup()                 (advisory activity-log shout)
"""

from __future__ import annotations

import argparse

import pytest

from arail import world_mount as wm
from tests.world_bundle_builder import make_bundle


@pytest.fixture
def catalog(tmp_path):
    wd = tmp_path / "worlds"
    wd.mkdir()
    make_bundle(wd, slug="alpha", display_name="Alpha")
    make_bundle(wd, slug="beta", display_name="Beta")
    return wd


def test_all_ok(catalog):
    results = wm.verify_shipped_worlds(catalog)
    assert [r["slug"] for r in results] == ["alpha", "beta"]
    assert all(r["ok"] for r in results)
    assert all(r["seal"] for r in results)
    assert all(r["terms"] >= 1 for r in results)


def test_corrupt_terms_fails_that_bundle_only(catalog):
    terms = catalog / "beta" / "terms.json"
    terms.write_bytes(terms.read_bytes() + b" ")
    results = {r["slug"]: r for r in wm.verify_shipped_worlds(catalog)}
    assert results["alpha"]["ok"] is True
    assert results["beta"]["ok"] is False
    assert results["beta"]["reason"]


def test_missing_dir_returns_empty(tmp_path):
    assert wm.verify_shipped_worlds(tmp_path / "nope") == []


def test_never_raises_on_garbage_dir(tmp_path):
    wd = tmp_path / "worlds"
    (wd / "junk").mkdir(parents=True)
    (wd / "junk" / "manifest.json").write_text("{not json")
    results = wm.verify_shipped_worlds(wd)
    assert len(results) == 1
    assert results[0]["ok"] is False
    assert results[0]["slug"] == "junk"  # dir-name fallback


# ── CLI command ──────────────────────────────────────────────────────────────


def _run_cli(monkeypatch, wd, capsys, examples=False):
    monkeypatch.setattr(wm, "_default_worlds_dir", lambda: wd)
    args = argparse.Namespace(examples=examples)
    rc = wm._cmd_verify_shipped(args)
    return rc, capsys.readouterr()


def test_cli_exit_zero_when_all_seal(catalog, monkeypatch, capsys):
    rc, out = _run_cli(monkeypatch, catalog, capsys)
    assert rc == 0
    assert out.out.count("OK ") == 2


def test_cli_exit_two_and_names_slug_on_corruption(catalog, monkeypatch, capsys):
    terms = catalog / "beta" / "terms.json"
    terms.write_bytes(terms.read_bytes() + b" ")
    rc, out = _run_cli(monkeypatch, catalog, capsys)
    assert rc == 2
    assert "beta" in out.err
    assert "git checkout" in out.err  # remediation hint


def test_cli_exit_two_when_nothing_found(tmp_path, monkeypatch, capsys):
    rc, out = _run_cli(monkeypatch, tmp_path / "empty", capsys)
    assert rc == 2
    assert "No World bundles" in out.err


def test_parser_accepts_verify_shipped():
    parser = wm._build_parser()
    args = parser.parse_args(["verify-shipped", "--examples"])
    assert args.command == "verify-shipped"
    assert args.examples is True
