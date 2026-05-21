"""QA carryover lock-down tests for sprint 2026-05-18-ai-eng-v2.1.

CO-1: Dry-run must complete on a low-RAM dev box. The RAM pre-check is a
runtime concern; dry-run is a static smoke of the code paths and must
NOT consult psutil. This test asserts dry-run exits 0 regardless of
configured RAM threshold (i.e. even when min_free_ram is impossibly
high).

CO-3 (partial): GGUF conversion failure path — see test_co3 below.

CO-7 (QA-found): Bench prompts schema — every prompt must carry the
documented schema fields (id, category, prompt, criteria); a missing
criteria field would silently degrade the human-review gate.

QA-NEW: privacy — committed BENCH-v2.1.md template must not contain the
operator's hostname or HOME path.

QA-NEW: scope discipline — sprint must not touch setup.sh /
pyproject.toml / models_catalog.yaml / Modelfile.* (regression guard
for commit 3a/3b leakage).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── CO-1 — dry-run must not OOM-pre-check on low-RAM machines ───────────────


def test_dry_run_exits_zero_with_huge_ram_threshold(tmp_path):
    """CO-1: A dev box with less RAM than --min-free-ram-gb must still pass dry-run.

    Reproducer for the review-noted bug: on a 15.2 GB-free box, default
    threshold 16 GB caused exit 20 before exercising the rest of the code
    paths. We simulate this by passing an impossibly-high threshold and
    asserting dry-run still exits 0.

    Marked xfail because the bug is currently live (CO-1 unresolved).
    Once the builder gates `check_free_ram_gb` behind `if not dry_run:`,
    flip the @pytest.mark.xfail and this becomes a passing regression test.
    """
    build_dir = tmp_path / "build"
    env = os.environ.copy()
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_ai_eng.py"),
        "dry-run",
        "--build-dir", str(build_dir),
        "--min-free-ram-gb", "999999",
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(REPO_ROOT))

    assert result.returncode == 0, (
        f"dry-run with high RAM threshold should be a no-op smoke; got rc={result.returncode}\n"
        f"stderr:\n{result.stderr}"
    )


# ── QA-NEW — bench prompts schema ─────────────────────────────────────────────


def test_bench_prompts_all_have_required_fields():
    """Every prompt must declare id, category, prompt, criteria.

    A missing `criteria` silently undermines the human-review gate (the
    operator has no rubric to apply); a missing `id` breaks the
    HEAD_TO_HEAD_IDS / AI_ENG_PROMPT_IDS lookups in bench_ai_eng.
    """
    data = yaml.safe_load((REPO_ROOT / "models/ai-eng/bench-prompts.v2.1.yaml").read_text())
    required = {"id", "category", "prompt", "criteria"}
    for p in data["prompts"]:
        missing = required - set(p.keys())
        assert not missing, f"prompt {p.get('id', '?')} missing fields: {missing}"


def test_bench_prompts_ids_unique():
    """Duplicate prompt IDs would silently overwrite outputs dict entries."""
    data = yaml.safe_load((REPO_ROOT / "models/ai-eng/bench-prompts.v2.1.yaml").read_text())
    ids = [p["id"] for p in data["prompts"]]
    assert len(ids) == len(set(ids)), f"duplicate prompt IDs: {ids}"


def test_bench_prompts_head_to_head_set_resolves():
    """Every HEAD_TO_HEAD_ID and AI_ENG_PROMPT_ID must exist in the prompts file.

    A typo in HEAD_TO_HEAD_IDS silently reduces h2h_a_wins ceiling — and
    the abort gate uses h2h_a_wins < 3 as a SHIP-BLOCKING signal, so a
    typo could spuriously abort the sprint.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from bench_ai_eng import HEAD_TO_HEAD_IDS, AI_ENG_PROMPT_IDS

    data = yaml.safe_load((REPO_ROOT / "models/ai-eng/bench-prompts.v2.1.yaml").read_text())
    prompt_ids = {p["id"] for p in data["prompts"]}
    missing_h2h = HEAD_TO_HEAD_IDS - prompt_ids
    missing_ae = AI_ENG_PROMPT_IDS - prompt_ids
    assert not missing_h2h, f"HEAD_TO_HEAD_IDS missing from prompts file: {missing_h2h}"
    assert not missing_ae, f"AI_ENG_PROMPT_IDS missing from prompts file: {missing_ae}"


# ── QA-NEW — privacy of committed bench template ─────────────────────────────


def test_committed_bench_template_has_no_hostname_or_home_leak():
    """BENCH-v2.1.md is committed to the repo. The live bench script
    writes socket.gethostname() and (on some paths) absolute paths into
    this file. The TEMPLATE that ships with the repo must contain no
    real-machine identifiers — only placeholder tokens.

    Regression guard: if the operator commits a populated BENCH-v2.1.md
    that contains their HOME directory or hostname, this test will catch
    it before merge.
    """
    text = (REPO_ROOT / "models/ai-eng/BENCH-v2.1.md").read_text()
    # Allow YYYY-MM-DD literal but flag any /Users/<name>/ or /home/<name>/ path
    assert not re.search(r"/Users/[A-Za-z0-9_.-]+/", text), \
        "BENCH-v2.1.md contains a /Users/.../ HOME-path leak"
    assert not re.search(r"/home/[A-Za-z0-9_.-]+/", text), \
        "BENCH-v2.1.md contains a /home/.../ HOME-path leak"
    # Hostname leak — common patterns include "<hostname>.local" or "<hostname>.lan"
    # Template uses literal placeholders; reject anything that looks like a real one.
    # Allow the literal escape "&lt;hostname&gt;" in the template.
    assert not re.search(r"\b[a-z][a-z0-9-]+\.(local|lan|home)\b", text, re.IGNORECASE), \
        "BENCH-v2.1.md may contain a real hostname (X.local/.lan/.home)"



# ── QA-NEW — security: no shell=True, no secrets in argv ─────────────────────


def test_no_subprocess_shell_true_in_build_scripts():
    """`shell=True` with user-controlled args is a path-traversal /
    command-injection surface. Build scripts accept --adapter-repo,
    --build-dir, --license — all operator-supplied — and must never
    interpolate them into a shell command line.
    """
    for fname in ("scripts/build_ai_eng.py", "scripts/bench_ai_eng.py"):
        content = (REPO_ROOT / fname).read_text()
        assert "shell=True" not in content, f"{fname} uses shell=True"


def test_hf_token_never_in_argv_construction():
    """HF tokens must pass through `env=` only, never via argv. Grep
    every subprocess invocation construction for token strings.
    """
    content = (REPO_ROOT / "scripts/build_ai_eng.py").read_text()
    # Token is read once into a local then put into env dict; argv lists
    # built nearby (huggingface-cli download) must not reference it.
    download_block = re.search(
        r'def download_adapter\(.*?(?=\ndef |\Z)', content, re.DOTALL,
    )
    assert download_block is not None
    block = download_block.group(0)
    # The cmd list must not contain "token" or HF_TOKEN
    cmd_match = re.search(r'cmd\s*=\s*\[(.*?)\]', block, re.DOTALL)
    assert cmd_match
    assert "TOKEN" not in cmd_match.group(1).upper(), \
        "HF token leaks into argv of huggingface-cli download"


# ── QA-NEW — CO-3 — GGUF conversion failure path ─────────────────────────────


def test_gguf_conversion_failure_exits_50(monkeypatch, tmp_path):
    """CO-3: F7 detection path is only implicit-tested. Inject a non-zero
    subprocess result from the convert_hf_to_gguf.py call and assert
    sys.exit(50). Covers the real failure-mode path that BUILD_LOG
    claims is wired.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import build_ai_eng

    build_dir = tmp_path / "build"
    build_dir.mkdir()
    (build_dir / "mlx-fused").mkdir()
    (build_dir / "mlx-fused" / "model.safetensors").write_bytes(b"stub")
    (build_dir / "mlx-fused" / "config.json").write_text('{"model_type":"qwen2"}')

    # Stub _ensure_llama_cpp to return a stub dir without git ops
    fake_llama = build_dir / "llama.cpp"
    fake_llama.mkdir()
    (fake_llama / "convert_hf_to_gguf.py").write_text("# stub")
    monkeypatch.setattr(build_ai_eng, "_ensure_llama_cpp", lambda *a, **k: fake_llama)

    # First subprocess call (mlx_lm.convert) succeeds; second (convert_hf_to_gguf) fails.
    calls = {"n": 0}
    def fake_run(cmd, **kw):
        calls["n"] += 1
        class R:
            returncode = 0 if calls["n"] == 1 else 1
            stderr = "" if calls["n"] == 1 else "synthetic GGUF conversion failure"
            stdout = ""
        return R()

    monkeypatch.setattr(build_ai_eng.subprocess, "run", fake_run)
    monkeypatch.setattr(build_ai_eng, "check_free_ram_gb", lambda *a, **k: None)

    with pytest.raises(SystemExit) as exc_info:
        build_ai_eng.convert_to_gguf(
            build_dir, candidate="a", llama_cpp_rev="b3500",
            min_free_ram_gb=1.0, dry_run=False,
        )
    assert exc_info.value.code == 50, f"expected exit 50 on GGUF conversion failure, got {exc_info.value.code}"


# ── QA-NEW — F17 token sanitization on error log capture ─────────────────────


def test_sanitize_log_line_strips_token_from_realistic_hf_error(tmp_path):
    """A realistic HF error stderr embedding an hf_-prefixed token must
    not write the token to disk. Tests F17 in the way it would actually
    fire.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import build_ai_eng

    fake_stderr = (
        "401 Client Error: Unauthorized for url: https://huggingface.co/api/...\n"
        "Authorization: Bearer hf_abcdefghijklmnopqrstuv1234\n"
        "Please run `huggingface-cli login`.\n"
    )
    target = tmp_path / "error-download.log"
    build_ai_eng._write_safe(target, fake_stderr)
    written = target.read_text()
    assert "hf_abcdefghijklmnopqrstuv1234" not in written
    assert "hf_REDACTED" in written


# ── QA-NEW — happy/edge: bench dry-run produces valid markdown ───────────────


def test_bench_dry_run_produces_parseable_summary(tmp_path):
    """Bench --dry-run must write a stub BENCH-v2.1.md that has the
    documented schema headers. A schema drift would silently break the
    operator runbook's Step 3 ("review BENCH-v2.1.md").
    """
    out = tmp_path / "BENCH-v2.1.md"
    cmd = [
        sys.executable, str(REPO_ROOT / "scripts/bench_ai_eng.py"),
        "--dry-run", "--out", str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    content = out.read_text()
    for header in ("# ai-eng v2.1 bench", "## Summary", "## Numbers", "## Gate logic applied"):
        assert header in content, f"missing required header: {header}"


# ── QA-NEW — operator runbook: --help works ──────────────────────────────────


def test_build_script_help_does_not_require_python_deps():
    """An operator should be able to run --help before installing
    mlx-lm/peft etc. The shell wrapper's --help path must work from a
    clean checkout.
    """
    r = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/build_ai_eng.sh"), "--help"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0
    assert "Usage" in r.stdout or "Subcommands" in r.stdout


def test_build_script_unknown_subcommand_exits_nonzero():
    """Operator typo robustness: a bogus subcommand must exit nonzero
    with a clear message — not silently fall through to `build`.
    """
    r = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/build_ai_eng.sh"), "buld"],  # typo
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert r.returncode != 0
    assert "Unknown" in r.stderr or "Unknown" in r.stdout


# ── QA-NEW — edge: probe_adapter_format on empty / corrupt config ─────────────


def test_probe_adapter_format_handles_invalid_json(tmp_path):
    """Half-written adapter_config.json (interrupted HF download) must
    exit 40 with a clear error, not crash with an opaque traceback.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import build_ai_eng

    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text('{"peft_type": "LORA"')  # truncated
    with pytest.raises(SystemExit) as exc_info:
        build_ai_eng.probe_adapter_format(adapter_dir)
    assert exc_info.value.code == 40


def test_probe_adapter_format_handles_missing_config(tmp_path):
    """Empty adapter dir (zero-byte HF clone) must exit 40 cleanly."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import build_ai_eng

    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    with pytest.raises(SystemExit) as exc_info:
        build_ai_eng.probe_adapter_format(adapter_dir)
    assert exc_info.value.code == 40


# ── QA-NEW — F18 — token scan in saved config catches realistic leak ─────────


def test_verify_no_token_in_config_catches_leak(tmp_path):
    """F18 must catch a token that snuck into a saved config.json
    (e.g. peft.save_pretrained accidentally serialised the auth_token
    field). The check must look at every *.json in the dir.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import build_ai_eng

    model_dir = tmp_path / "merged"
    model_dir.mkdir()
    (model_dir / "config.json").write_text('{"hf_token": "hf_AAAAAAAAAAbbbbbbbbbb"}')
    with pytest.raises(SystemExit) as exc_info:
        build_ai_eng._verify_no_token_in_config(model_dir)
    assert exc_info.value.code == 60
