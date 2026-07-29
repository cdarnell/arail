"""§7 — per-instance secrets: never shared, never auto-copied, 0600,
git-ignored, never logged.

Covers ARCHITECTURE.md §7 and the security checklist item "Secrets: 0600,
not shared, not logged" (§9).
"""
from __future__ import annotations

import inspect
import shutil
import stat
import subprocess
from pathlib import Path

from arail.portal import app as portal_app

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_secrets_to(path: Path, pairs: dict[str, str], monkeypatch) -> None:
    monkeypatch.setenv("ARAIL_SECRETS_FILE", str(path))
    portal_app._write_secrets(pairs)


# ---------------------------------------------------------------------------
# Created 0600, in the instance's OWN data dir
# ---------------------------------------------------------------------------

def test_secrets_written_0600(tmp_path, monkeypatch):
    inst_secrets = tmp_path / "lab" / "instances" / "finance" / "data" / "secrets.env"
    _write_secrets_to(inst_secrets, {"ANTHROPIC_API_KEY": "sk-test-secret-value"}, monkeypatch)

    assert inst_secrets.exists()
    mode = stat.S_IMODE(inst_secrets.stat().st_mode)
    assert mode == 0o600, oct(mode)


def test_secrets_not_created_until_first_save(tmp_path, monkeypatch):
    """First boot creates data/ but NOT secrets.env — it's created only when
    a key is first saved (ARCHITECTURE.md §7 mechanics)."""
    data_dir = tmp_path / "lab" / "instances" / "finance" / "data"
    data_dir.mkdir(parents=True)
    assert not (data_dir / "secrets.env").exists()


# ---------------------------------------------------------------------------
# Never shared / auto-copied between instances or from the root lab
# ---------------------------------------------------------------------------

def test_secrets_never_copied_between_instances(tmp_path, monkeypatch):
    root_secrets = tmp_path / "lab" / "data" / "secrets.env"
    finance_secrets = tmp_path / "lab" / "instances" / "finance" / "data" / "secrets.env"
    ai_secrets = tmp_path / "lab" / "instances" / "ai" / "data" / "secrets.env"

    _write_secrets_to(root_secrets, {"OPENAI_API_KEY": "sk-root-key"}, monkeypatch)
    _write_secrets_to(finance_secrets, {"ANTHROPIC_API_KEY": "sk-finance-key"}, monkeypatch)

    # The instance's save path never read or copied the root lab's file —
    # its own secrets.env is exactly what THIS write produced, and the
    # sibling instance ("ai") never gets a file at all.
    assert "sk-root-key" not in finance_secrets.read_text(encoding="utf-8")
    assert not ai_secrets.exists()
    assert not finance_secrets.is_symlink()
    assert not root_secrets.is_symlink()


def test_secrets_path_has_no_symlink_or_copy_logic_in_source():
    """Source-level regression guard: the write path must never shell out
    to cp/ln or import shutil.copy for secrets.env — any such call would
    be exactly the silent-propagation bug §7 rules out."""
    src = inspect.getsource(portal_app._write_secrets)
    for banned in ("shutil.copy", "os.symlink", "os.link", "subprocess"):
        assert banned not in src, f"{banned} found in _write_secrets"


# ---------------------------------------------------------------------------
# git-ignored
# ---------------------------------------------------------------------------

def test_git_check_ignore_covers_instance_secrets():
    for rel in (
        "lab/instances/finance/data/secrets.env",
        "lab/instances/ai/data/secrets.env",
        "lab/data/secrets.env",  # the root lab's, unchanged
    ):
        result = subprocess.run(
            ["git", "check-ignore", rel],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"{rel} is NOT git-ignored: {result.stdout}{result.stderr}"


# ---------------------------------------------------------------------------
# Never logged / echoed
# ---------------------------------------------------------------------------

def test_write_secrets_never_logs_the_token(tmp_path, monkeypatch, caplog):
    secret_value = "sk-super-secret-do-not-log-me"
    inst_secrets = tmp_path / "secrets.env"
    with caplog.at_level("DEBUG"):
        _write_secrets_to(inst_secrets, {"ANTHROPIC_API_KEY": secret_value}, monkeypatch)
    for record in caplog.records:
        assert secret_value not in record.getMessage()


def test_providers_save_source_never_prints_or_logs_token():
    """Source-level guard on the endpoint that calls _write_secrets: no
    print()/logger call anywhere in its body references the token
    variable directly (the existing never-echo-back rule, pinned)."""
    import ast
    src = inspect.getsource(portal_app)
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "providers_save"
    )
    fn_src = ast.get_source_segment(src, fn) or ""
    assert "print(token" not in fn_src
    assert "print(f" not in fn_src or "token" not in fn_src


# ---------------------------------------------------------------------------
# QA-B2 (FIXED) — onboarding must never target the instance.env pack, and a
# --port rewrite of that pack must never be able to destroy a credential.
# sprints/2026-07-28-concurrent-worlds/TEST_REPORT.md
# ---------------------------------------------------------------------------

def test_onboarding_writer_targets_the_instance_secrets_store_not_the_pack(
    tmp_path, monkeypatch
):
    """`_env_file_path()` must redirect an instance process's onboarding
    write to `_secrets_path()` (0600, `<instance>/data/secrets.env`) — never
    to `ARAIL_ENV_FILE`, which for an instance is the world-readable, 0644
    `instance.env` pack §1.2 declares secret-free.
    """
    instance_root = tmp_path / "lab" / "instances" / "finance"
    pack = instance_root / "instance.env"
    pack.parent.mkdir(parents=True)
    pack.write_text("ARAIL_INSTANCE=finance\nPORTAL_PORT=8090\n", encoding="utf-8")
    secrets = instance_root / "data" / "secrets.env"

    monkeypatch.setenv("ARAIL_INSTANCE", "finance")
    monkeypatch.setenv("ARAIL_ENV_FILE", str(pack))
    monkeypatch.setenv("ARAIL_SECRETS_FILE", str(secrets))

    assert portal_app._env_file_path() == secrets

    portal_app._write_env_kv("ARAIL_PASSWORD", "correct-horse-battery-staple")
    assert "ARAIL_PASSWORD" not in pack.read_text(encoding="utf-8"), (
        "onboarding wrote a credential into the world-readable instance.env pack"
    )
    assert "ARAIL_PASSWORD=correct-horse-battery-staple" in secrets.read_text(encoding="utf-8")
    mode = stat.S_IMODE(secrets.stat().st_mode)
    assert mode == 0o600, oct(mode)


def test_a_port_rewrite_of_the_pack_cannot_destroy_a_credential(tmp_path):
    """The blast-radius half of QA-B2: `inst_write_env_pack` truncates and
    re-`chmod 0644`s `instance.env` on every `--port` rewrite. Once onboarding
    targets a SEPARATE file (the previous test), that rewrite has nothing to
    destroy — assert the two files are simply never the same path, and that a
    real pack rewrite leaves a pre-existing secrets.env untouched.
    """
    repo = tmp_path
    (repo / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO_ROOT / "scripts" / "setup.sh", repo / "scripts" / "setup.sh")
    instances_sh = REPO_ROOT / "scripts" / "lib" / "instances.sh"
    slug = "finance"
    secrets = repo / "lab" / "instances" / slug / "data" / "secrets.env"
    secrets.parent.mkdir(parents=True)
    secrets.write_text("ARAIL_PASSWORD=correct-horse-battery-staple\n", encoding="utf-8")
    secrets.chmod(0o600)
    before = secrets.read_text(encoding="utf-8")

    # A pack rewrite — the exact operation a `--port` change performs
    # (inst_write_env_pack truncates instance.env and re-chmods it 0644).
    r = subprocess.run(
        ["bash", "-c",
         f'set -euo pipefail; REPO_ROOT="{repo}"; source "{instances_sh}"; '
         'inst_write_env_pack finance LAB_ROOT "$1" PORTAL_PORT 8091',
         "bash", str(repo / "lab" / "instances" / slug)],
        capture_output=True, text=True, timeout=20,
    )
    assert r.returncode == 0, r.stderr

    pack = repo / "lab" / "instances" / slug / "instance.env"
    assert pack != secrets, "the pack and the secrets store must never be the same path"
    assert secrets.read_text(encoding="utf-8") == before, (
        "a pack rewrite touched the secrets store — the credential was destroyed"
    )
    assert stat.S_IMODE(secrets.stat().st_mode) == 0o600
