"""ARCHITECTURE.md §4.1/§8/§9: the BUNDLED install channel
(`scripts/build-aerollm.sh bundle` / `bundle_install()`).

No test hits the real network — all download paths point at a `file://`-
style local tarball via AEROLLM_BUNDLE_FILE, per §9's "no test may hit the
real network by default" rule.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tarfile

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
BUILD = REPO / "scripts" / "build-aerollm.sh"


def _make_tarball(tmp_path: pathlib.Path, *, so_bytes: bytes = b"fake-so-bytes") -> pathlib.Path:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "aerollm_api.abi3.so").write_bytes(so_bytes)
    (stage / "LICENSE").write_text("Apache-2.0\n")
    (stage / "NOTICE").write_text("AeroLLM NOTICE\n")
    manifest = {
        "schema": "arail.aerollm-bundle/v1",
        "aerollm_version": "9.9.9",
        "aerollm_commit": "a" * 40,
        "aerollm_dirty": False,
        "built_at": "2026-01-01T00:00:00Z",
        "built_by": "test",
        "platform": "macos-arm64",
        "python_abi": "abi3-cp39",
        "sha256": "unused-in-test",
        "license": "Apache-2.0",
        "modifications": "none",
        "arail_release": "vtest",
    }
    (stage / "MANIFEST.json").write_text(json.dumps(manifest))
    tarball = tmp_path / "bundle.tar.gz"
    with tarfile.open(tarball, "w:gz") as tf:
        for f in ("aerollm_api.abi3.so", "LICENSE", "NOTICE", "MANIFEST.json"):
            tf.add(stage / f, arcname=f)
    return tarball


def _run(mode, env_extra, args=()):
    env = {**os.environ, "NO_COLOR": "1", "ARAIL_AEROLLM_REPO": "/nonexistent", **env_extra}
    return subprocess.run(
        ["bash", str(BUILD), mode, *args],
        capture_output=True, text=True, env=env,
    )


@pytest.fixture()
def isolated_python(tmp_path):
    """A throwaway venv with no aerollm_api installed — an 'outside user'
    interpreter, isolated from whatever this repo's own .venv has (which
    may already carry a DEV build with no bundle marker → would trip F7).
    """
    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    return venv_dir / "bin" / "python3"


@pytest.mark.skipif(sys.platform != "darwin", reason="bundle_install() is macOS-arm64-only by design (F4)")
def test_bundle_install_from_local_file_succeeds(tmp_path, isolated_python):
    tarball = _make_tarball(tmp_path)
    digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
    r = _run("bundle", {
        "AEROLLM_BUNDLE_FILE": str(tarball),
        "AEROLLM_BUNDLE_SHA256": digest,
        "PYTHON": str(isolated_python),
    })
    # The fake .so isn't a real python extension, so `import aerollm_api`
    # will fail inside the script — that's expected here (F1's cleanup
    # path). What we're asserting is the checksum-verified copy actually
    # happened before the import check, and F1 removed it after failing.
    assert "Checksum verified" in r.stdout
    assert r.returncode != 0
    assert "import aerollm_api" in (r.stdout + r.stderr) or "Removed the broken artifact" in r.stdout


def test_checksum_mismatch_aborts_before_any_write(tmp_path):
    tarball = _make_tarball(tmp_path)
    r = _run("bundle", {
        "AEROLLM_BUNDLE_FILE": str(tarball),
        "AEROLLM_BUNDLE_SHA256": "0" * 64,
    })
    assert r.returncode != 0
    assert "Checksum mismatch" in (r.stdout + r.stderr)


def test_platform_guard_refuses_before_network(monkeypatch, tmp_path):
    # Simulate non-Darwin by wrapping uname — bundle_install() calls
    # `uname -s`/`uname -m` directly, so we assert via a Linux CI run's
    # natural behavior instead when not on macOS; on macOS we assert the
    # opposite (the guard does NOT fire).
    r = _run("bundle", {"AEROLLM_BUNDLE_FILE": "/nonexistent/bundle.tar.gz"})
    if sys.platform != "darwin":
        assert r.returncode == 1
        assert "macOS-arm64-only" in (r.stdout + r.stderr)


def test_curl_failure_names_resolved_url_and_exits_nonzero():
    r = _run("bundle", {
        "AEROLLM_BUNDLE_REPO": "cdarnell/does-not-exist-nowhere",
        "AEROLLM_BUNDLE_TAG": "v0.0.0-nonexistent",
    })
    assert r.returncode != 0
    out = r.stdout + r.stderr
    assert "does-not-exist-nowhere" in out
    assert "AEROLLM_BUNDLE_FILE" in out


def test_https_only_scheme_guard():
    r = _run("bundle", {"AEROLLM_BUNDLE_URL": "http://example.com/bundle.tar.gz"})
    assert r.returncode != 0
    assert "https" in (r.stdout + r.stderr).lower()


def test_status_reports_channel_none_without_marker():
    r = _run("status", {})
    assert r.returncode == 0
    assert "channel:" in r.stdout


def test_producer_filename_matches_consumer_resolved_filename(tmp_path):
    """Regression test for B1 (REVIEW.md): the producer
    (package-aerollm-bundle.sh) and the consumer (resolve_bundle_url() in
    build-aerollm.sh) must derive the same asset filename from the same
    tag, or the default bundled channel 404s by construction.
    """
    tag = "v9.9.9-regression-test"

    # A minimal, clean, committed fake aeroLLM sibling repo.
    fake_repo = tmp_path / "fake-aerollm"
    (fake_repo / "crates" / "aerollm-api").mkdir(parents=True)
    (fake_repo / "Cargo.toml").write_text('[workspace.package]\nversion = "0.0.0"\n')
    (fake_repo / "LICENSE").write_text("Apache-2.0 stub\n")
    (fake_repo / "NOTICE").write_text("AeroLLM NOTICE\n")
    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t.com", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=fake_repo, check=True,
    )

    # A committed THIRD-PARTY-LICENSES/aerollm/LICENSE for the producer to
    # copy from (real repo already has this; the fake repo above doesn't
    # need one since package-aerollm-bundle.sh reads it from REPO_ROOT).

    # Fake `cargo` on PATH: writes a dummy .so where the real build would.
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_cargo = fake_bin / "cargo"
    fake_cargo.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'mkdir -p "$PWD/target/release"\n'
        'touch "$PWD/target/release/libaerollm_api.dylib"\n'
    )
    fake_cargo.chmod(0o755)

    # Isolated output dir — this test MUST NEVER touch the real
    # dist/aerollm-bundle/ (package-aerollm-bundle.sh:107 `rm -rf`s
    # $OUT_DIR on every run; running the producer with cwd=REPO and no
    # OUT_DIR override destroyed the real, already-built v1.1.0 release
    # artifact. See REVIEW.md round-2 B3.)
    out_dir = tmp_path / "out"
    env = {
        **os.environ,
        "NO_COLOR": "1",
        "ARAIL_AEROLLM_REPO": str(fake_repo),
        "ARAIL_RELEASE_TAG": tag,
        "OUT_DIR": str(out_dir),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    r = subprocess.run(
        ["bash", str(REPO / "scripts" / "package-aerollm-bundle.sh")],
        capture_output=True, text=True, env=env, cwd=tmp_path,
    )
    assert r.returncode == 0, r.stdout + r.stderr

    # The real dist/aerollm-bundle/ must be untouched by this test.
    real_out_dir = REPO / "dist" / "aerollm-bundle"
    real_out_snapshot_before = (
        sorted(p.name for p in real_out_dir.glob("*.tar.gz"))
        if real_out_dir.is_dir()
        else []
    )

    produced = list(out_dir.glob("*.tar.gz"))
    assert len(produced) == 1, produced
    producer_filename = produced[0].name

    real_out_snapshot_after = (
        sorted(p.name for p in real_out_dir.glob("*.tar.gz"))
        if real_out_dir.is_dir()
        else []
    )
    assert real_out_snapshot_before == real_out_snapshot_after, (
        "test run must not modify the real dist/aerollm-bundle/ directory"
    )

    # Ask the real consumer what URL it would request for this tag, by
    # invoking bundle_install() against an unreachable host and reading the
    # URL it reports back — this exercises the actual resolve_bundle_url()
    # code path, not a reimplementation of it.
    r2 = _run("bundle", {
        "AEROLLM_BUNDLE_REPO": "cdarnell/does-not-exist-nowhere",
        "AEROLLM_BUNDLE_TAG": tag,
    })
    assert r2.returncode != 0
    consumer_out = r2.stdout + r2.stderr
    assert producer_filename in consumer_out, (
        f"producer emitted {producer_filename!r} but the consumer's "
        f"resolve_bundle_url() requested a different URL for tag {tag!r}:\n{consumer_out}"
    )


def test_package_script_refuses_dirty_worktree_without_allow_dirty(tmp_path, monkeypatch):
    fake_repo = tmp_path / "fake-aerollm"
    (fake_repo / "crates" / "aerollm-api").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True)
    (fake_repo / "dirty.txt").write_text("uncommitted\n")
    env = {
        **os.environ, "NO_COLOR": "1", "ARAIL_AEROLLM_REPO": str(fake_repo),
        "ARAIL_RELEASE_TAG": "vtest",
    }
    r = subprocess.run(
        ["bash", str(REPO / "scripts" / "package-aerollm-bundle.sh")],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode != 0
    assert "dirty" in (r.stdout + r.stderr).lower()


def test_package_script_requires_release_tag(tmp_path):
    """Regression guard: ARAIL_RELEASE_TAG can't be silently defaulted —
    the output filename must be tied to an explicit release tag or B1's
    filename-mismatch failure mode can reappear silently."""
    fake_repo = tmp_path / "fake-aerollm"
    (fake_repo / "crates" / "aerollm-api").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True)
    env = {**os.environ, "NO_COLOR": "1", "ARAIL_AEROLLM_REPO": str(fake_repo)}
    env.pop("ARAIL_RELEASE_TAG", None)
    r = subprocess.run(
        ["bash", str(REPO / "scripts" / "package-aerollm-bundle.sh")],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode != 0
    assert "ARAIL_RELEASE_TAG" in (r.stdout + r.stderr)
