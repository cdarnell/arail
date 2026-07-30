"""The falsifiable core (ARCHITECTURE.md §9, VISION win condition #1):
mounting a second World in a second instance's root must NOT touch the
first instance's staged data, index, or egress log — process separation
IS the isolation mechanism, and mount()/pkb.search()/egress's explicit
pkb_root/data_dir/ARAIL_DATA_DIR parameters are the seam this test drives
in-process (a real two-uvicorn-process run is exercised by
tests/instance_start_driver.sh; this file pins the underlying data-path
guarantee that makes that safe).

Covers: A32.1 (process separation is sufficient isolation), §6.3 (egress
lands per-instance), and the "instance PKB invisible to the root lab's
search" assertion named in §9's test-strategy table.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

from arail import world_mount as wm
from arail import pkb
from arail import egress
from tests.world_bundle_builder import make_bundle


def _sha256_tree(root: pathlib.Path) -> dict[str, str]:
    """sha256 of every file under root, keyed by path relative to root."""
    out = {}
    if not root.exists():
        return out
    for f in sorted(root.rglob("*")):
        if f.is_file():
            out[str(f.relative_to(root))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def _two_instances(tmp_path):
    """Two instance roots sharing one Worlds catalog — mirrors the real
    layout (ARAIL_WORLDS_DIR shared, pkb/data per-instance)."""
    worlds_dir = tmp_path / "shared-worlds"
    worlds_dir.mkdir()
    a = make_bundle(
        worlds_dir, slug="world-a-instance", display_name="A Instance World",
        terms_list=[{
            "slug": "term-a", "term": "Term A", "category": "cat-a",
            "short": "short a", "definition": "definition a",
            "example": "example a", "related": [], "source": "model-asserted",
        }],
        categories=[{"id": "cat-a", "label": "Cat A"}],
    )
    b = make_bundle(
        worlds_dir, slug="world-b-instance", display_name="B Instance World",
        terms_list=[{
            "slug": "term-b", "term": "Term B", "category": "cat-b",
            "short": "short b", "definition": "definition b",
            "example": "example b", "related": [], "source": "model-asserted",
        }],
        categories=[{"id": "cat-b", "label": "Cat B"}],
    )
    inst_a = {
        "worlds": worlds_dir,
        "data": tmp_path / "instance-a" / "data",
        "pkb": tmp_path / "instance-a" / "pkb",
        "bundle": a,
    }
    inst_b = {
        "worlds": worlds_dir,
        "data": tmp_path / "instance-b" / "data",
        "pkb": tmp_path / "instance-b" / "pkb",
        "bundle": b,
    }
    return inst_a, inst_b


# ---------------------------------------------------------------------------
# The falsifiable core: byte-identical sha256 per file, LanceDB cache
# untouched, after a SECOND instance mounts a DIFFERENT World.
# ---------------------------------------------------------------------------

def test_mounting_world_b_in_instance_b_never_touches_instance_a(tmp_path):
    inst_a, inst_b = _two_instances(tmp_path)

    rec_a = wm.mount(inst_a["bundle"], pkb_root=inst_a["pkb"], data_dir=inst_a["data"])
    assert rec_a.world == "world-a-instance"

    staged_a = inst_a["pkb"] / "sources" / "world-world-a-instance"
    assert staged_a.exists()
    before = _sha256_tree(staged_a)
    assert before, "instance A's staged World must be non-empty before B mounts"

    lancedb_a = inst_a["pkb"] / ".cache" / "lancedb"
    lancedb_a.mkdir(parents=True, exist_ok=True)
    sentinel = lancedb_a / "sentinel.txt"
    sentinel.write_text("untouched", encoding="utf-8")
    sentinel_before_mtime = sentinel.stat().st_mtime_ns

    # ── The second instance mounts a DIFFERENT World, into its OWN root ──
    rec_b = wm.mount(inst_b["bundle"], pkb_root=inst_b["pkb"], data_dir=inst_b["data"])
    assert rec_b.world == "world-b-instance"

    # A's staged tree is byte-identical, file for file.
    after = _sha256_tree(staged_a)
    assert after == before, "instance A's staged World changed after instance B's mount"

    # A's LanceDB cache directory was never touched.
    assert sentinel.exists()
    assert sentinel.stat().st_mtime_ns == sentinel_before_mtime

    # A's own mount record is unaffected — it's still world-a-instance.
    assert wm.current_mount(inst_a["data"]).world == "world-a-instance"
    # B's mount record is independent, and points at B's own World.
    assert wm.current_mount(inst_b["data"]).world == "world-b-instance"

    # B never staged anything under A's pkb root.
    assert not (inst_a["pkb"] / "sources" / "world-world-b-instance").exists()
    # A never staged anything under B's pkb root.
    assert not (inst_b["pkb"] / "sources" / "world-world-a-instance").exists()


def test_third_mount_in_instance_a_still_leaves_b_untouched(tmp_path):
    """Symmetric check: activity in A doesn't touch B either."""
    inst_a, inst_b = _two_instances(tmp_path)
    wm.mount(inst_a["bundle"], pkb_root=inst_a["pkb"], data_dir=inst_a["data"])
    wm.mount(inst_b["bundle"], pkb_root=inst_b["pkb"], data_dir=inst_b["data"])

    staged_b = inst_b["pkb"] / "sources" / "world-world-b-instance"
    before = _sha256_tree(staged_b)

    # Re-mount A on top of itself (a realistic "reboot the instance" case).
    wm.mount(inst_a["bundle"], pkb_root=inst_a["pkb"], data_dir=inst_a["data"])

    after = _sha256_tree(staged_b)
    assert after == before


# ---------------------------------------------------------------------------
# §6.3: egress.jsonl lands under the INSTANCE's own data dir, never the
# other instance's (regression cover for the documented egress.py:92
# os.getenv("ARAIL_DATA_DIR") bypass — untouched, but re-reads the env var
# the instance pack always exports explicitly).
# ---------------------------------------------------------------------------

def test_egress_log_lands_per_instance_data_dir(tmp_path, monkeypatch):
    inst_a, inst_b = _two_instances(tmp_path)
    inst_a["data"].mkdir(parents=True, exist_ok=True)
    inst_b["data"].mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("ARAIL_DATA_DIR", str(inst_a["data"]))
    egress.record_block("https://example.com/thing", "test.caller", "airgapped")

    a_log = inst_a["data"] / "egress.jsonl"
    b_log = inst_b["data"] / "egress.jsonl"
    assert a_log.exists()
    assert not b_log.exists()
    line = json.loads(a_log.read_text(encoding="utf-8").splitlines()[-1])
    assert line["url_host"] == "example.com"

    # Now switch to instance B's data dir — its own log, A's is untouched.
    a_before = a_log.read_text(encoding="utf-8")
    monkeypatch.setenv("ARAIL_DATA_DIR", str(inst_b["data"]))
    egress.record_block("https://other.example/thing", "test.caller", "airgapped")
    assert b_log.exists()
    assert a_log.read_text(encoding="utf-8") == a_before


# ---------------------------------------------------------------------------
# Instance PKB is invisible to the root lab's pkb.search (explicit
# pkb_root parameter — the seam pkb.search() already exposes).
# ---------------------------------------------------------------------------

def test_instance_pkb_invisible_to_a_different_roots_search(tmp_path):
    inst_a, inst_b = _two_instances(tmp_path)
    wm.mount(inst_a["bundle"], pkb_root=inst_a["pkb"], data_dir=inst_a["data"])

    root_lab_pkb = tmp_path / "root-lab" / "pkb"
    root_lab_pkb.mkdir(parents=True)

    # A search rooted at the (empty) root lab's PKB must not find A's
    # staged term, even though a search rooted at A's OWN pkb does.
    results_root_lab = pkb.search("Term A", pkb_root=root_lab_pkb)
    assert results_root_lab == [] or all(
        "term-a" not in json.dumps(r) for r in results_root_lab
    )
