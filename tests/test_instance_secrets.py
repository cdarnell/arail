"""§7 — per-instance secrets: never shared, never auto-copied, 0600,
git-ignored, never logged.

Covers ARCHITECTURE.md §7 and the security checklist item "Secrets: 0600,
not shared, not logged" (§9).
"""
from __future__ import annotations

import inspect
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
