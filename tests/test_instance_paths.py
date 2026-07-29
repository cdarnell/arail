"""Instance env pack -> arail.config resolution (ARCHITECTURE.md §1.2, §6).

Drives a *hand-written* instance.env (the pack format WP3's writer will
produce) through the real `bash -c 'set -a; source ...; set +a'` load path
and through a fresh `arail.config` interpreter, and asserts:

  * all five path keys (LAB_ROOT, ARAIL_DATA_DIR, ARAIL_MODELS_DIR,
    ARAIL_WORLDS_DIR, LAB_PKB) resolve to absolute paths
  * ARAIL_MODELS_DIR / ARAIL_WORLDS_DIR stay pointed at the *shared* root
    even though LAB_ROOT points into the per-instance tree — this is the
    config.py:86 trap named in ARCHITECTURE.md §1.2: MODELS_DIR defaults to
    LAB_ROOT/models when unset, which would silently fork the weights dir
    per instance unless the pack sets it explicitly
  * ARAIL_ENV_FILE wins over a parent-directory .env python-dotenv would
    otherwise walk up and find
  * the pack round-trips through `bash -c 'set -a; source ...; set +a'`
    without error under `set -euo pipefail`

The app.py startup boot-assertion half of F14 (§6.4 guard 2: "assert
LAB_ROOT/DATA_DIR/PKB_ROOT/MODELS_DIR/WORLDS_DIR .is_absolute() when
ARAIL_INSTANCE is set, else raise") is WP6 scope (app.py is not touched by
this builder pass) and is intentionally NOT covered here — see BUILD_LOG.md
"Execution" notes for WP1. This file covers guard 1 only: the pack itself
never needs to fall back to a relative default.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")


def _write_pack(pack_path: Path, instance_root: Path, models_dir: Path, worlds_dir: Path) -> None:
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(
        textwrap.dedent(f"""\
            ARAIL_INSTANCE=finance
            ARAIL_ENV_FILE={pack_path}
            LAB_ROOT={instance_root}
            ARAIL_DATA_DIR={instance_root}/data
            LAB_PKB={instance_root}/pkb
            ARAIL_EXPERIMENTS_DIR={instance_root}/data/experiments
            ARAIL_MODELS_DIR={models_dir}
            ARAIL_WORLDS_DIR={worlds_dir}
            PORTAL_PORT=8090
            LANCE_PORT=8094
            BIND_ADDR=127.0.0.1
            LAB_NAME="Finance World"
            LAB_SHORT_NAME=finance-world
        """),
        encoding="utf-8",
    )


def _resolved_paths(env: dict[str, str], home: Path, cwd: Path | None = None) -> dict[str, str]:
    script = (
        "from arail.config import LAB_ROOT, DATA_DIR, MODELS_DIR, WORLDS_DIR, PKB_ROOT\n"
        "import json\n"
        "print(json.dumps({"
        "'LAB_ROOT': str(LAB_ROOT), 'DATA_DIR': str(DATA_DIR), "
        "'MODELS_DIR': str(MODELS_DIR), 'WORLDS_DIR': str(WORLDS_DIR), "
        "'PKB_ROOT': str(PKB_ROOT)}))\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(cwd or REPO_ROOT),
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(home),
            "PYTHONPATH": str(REPO_ROOT / "src"),
            **env,
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert res.returncode == 0, res.stderr
    import json as _json
    return _json.loads(res.stdout)


def test_pack_sources_cleanly_under_set_euo_pipefail(tmp_path):
    instance_root = tmp_path / "lab" / "instances" / "finance"
    models_dir = tmp_path / "lab" / "models"
    worlds_dir = tmp_path / "lab" / "worlds"
    pack = instance_root / "instance.env"
    _write_pack(pack, instance_root, models_dir, worlds_dir)

    res = subprocess.run(
        [_BASH, "-c", f'set -euo pipefail; set -a; source "{pack}"; set +a; echo "$PORTAL_PORT"'],
        capture_output=True, text=True, timeout=10,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "8090"


def test_all_five_paths_resolve_absolute(tmp_path):
    instance_root = tmp_path / "lab" / "instances" / "finance"
    models_dir = tmp_path / "lab" / "models"
    worlds_dir = tmp_path / "lab" / "worlds"
    pack = instance_root / "instance.env"
    _write_pack(pack, instance_root, models_dir, worlds_dir)
    home = tmp_path / "home"
    home.mkdir()

    resolved = _resolved_paths({"ARAIL_ENV_FILE": str(pack)}, home)
    for key, value in resolved.items():
        assert Path(value).is_absolute(), f"{key} resolved to a non-absolute path: {value}"


def test_models_dir_stays_shared_not_under_instance_root(tmp_path):
    """The config.py:86 trap: ARAIL_MODELS_DIR must NOT default under LAB_ROOT."""
    instance_root = tmp_path / "lab" / "instances" / "finance"
    models_dir = tmp_path / "lab" / "models"  # shared, sibling of instances/
    worlds_dir = tmp_path / "lab" / "worlds"
    pack = instance_root / "instance.env"
    _write_pack(pack, instance_root, models_dir, worlds_dir)
    home = tmp_path / "home"
    home.mkdir()

    resolved = _resolved_paths({"ARAIL_ENV_FILE": str(pack)}, home)
    assert resolved["MODELS_DIR"] == str(models_dir)
    assert not resolved["MODELS_DIR"].startswith(str(instance_root)), (
        "MODELS_DIR silently forked under the instance root — every instance "
        "would re-download the weights"
    )
    assert resolved["WORLDS_DIR"] == str(worlds_dir)
    assert not resolved["WORLDS_DIR"].startswith(str(instance_root))


def test_data_and_pkb_are_per_instance(tmp_path):
    instance_root = tmp_path / "lab" / "instances" / "finance"
    models_dir = tmp_path / "lab" / "models"
    worlds_dir = tmp_path / "lab" / "worlds"
    pack = instance_root / "instance.env"
    _write_pack(pack, instance_root, models_dir, worlds_dir)
    home = tmp_path / "home"
    home.mkdir()

    resolved = _resolved_paths({"ARAIL_ENV_FILE": str(pack)}, home)
    assert resolved["DATA_DIR"] == str(instance_root / "data")
    assert resolved["PKB_ROOT"] == str(instance_root / "pkb")


def test_arail_env_file_beats_a_parent_directory_env(tmp_path):
    """A worktree/checkout .env one level up must not leak into the instance."""
    parent_env = tmp_path / ".env"
    parent_env.write_text("LAB_ROOT=WRONG-parent-lab\n", encoding="utf-8")

    instance_root = tmp_path / "child" / "lab" / "instances" / "finance"
    models_dir = tmp_path / "child" / "lab" / "models"
    worlds_dir = tmp_path / "child" / "lab" / "worlds"
    pack = instance_root / "instance.env"
    _write_pack(pack, instance_root, models_dir, worlds_dir)
    home = tmp_path / "home"
    home.mkdir()

    # cwd is `tmp_path/child` so python-dotenv's walk-up search (if
    # ARAIL_ENV_FILE were absent) would find tmp_path/.env — confirm the pin
    # wins instead by asserting LAB_ROOT resolves to the pack's value.
    child_cwd = tmp_path / "child"
    child_cwd.mkdir(exist_ok=True)
    resolved = _resolved_paths({"ARAIL_ENV_FILE": str(pack)}, home, cwd=child_cwd)
    assert resolved["LAB_ROOT"] == str(instance_root)
    assert "WRONG-parent-lab" not in resolved["LAB_ROOT"]
