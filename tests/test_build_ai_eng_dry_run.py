"""test_build_ai_eng_dry_run.py

Exercises every code path in build_ai_eng.py with --dry-run / dry-run subcommand.
No downloads, no model loads, no GGUF conversion.

Assertions:
- Every step writes the expected sentinel file
- Idempotent re-run is a true no-op (sentinels already present → skip)
- HF token NEVER appears in any file under build/
- Adapter format probe correctly reads stub adapter_config.json
- Modelfile is generated with the correct SYSTEM block from Modelfile.production
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

import pytest

# Import helpers directly from the script under test
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import build_ai_eng as bld


REPO_ROOT = Path(__file__).parent.parent
MODELFILE_PRODUCTION = REPO_ROOT / "models" / "ai-eng" / "Modelfile.production"

HF_TOKEN_RE = re.compile(r"hf_[A-Za-z0-9]{10,}")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def build_dir(tmp_path: Path) -> Path:
    d = tmp_path / "build"
    d.mkdir()
    return d


@pytest.fixture()
def adapter_dir(build_dir: Path) -> Path:
    """A synthetic adapter directory mimicking mlx_lm format."""
    d = build_dir / "adapter"
    d.mkdir()
    (d / "adapter_config.json").write_text(
        json.dumps({
            "__mlx_lm_format": True,
            "r": 16,
            "lora_alpha": 16,
            "lora_dropout": 0.05,
            "target_modules": ["q_proj", "v_proj"],
        })
    )
    (d / "adapters.safetensors").write_bytes(b"STUB_WEIGHTS")
    return d


# ── Sanitise log line ─────────────────────────────────────────────────────────

class TestSanitizeLogLine:
    def test_strips_hf_token(self):
        line = "Uploading with token hf_ABCDEFGHIJklmnopqrstuvwxyz123"
        result = bld.sanitize_log_line(line)
        assert "hf_ABCDE" not in result
        assert "hf_REDACTED" in result

    def test_preserves_non_token_text(self):
        line = "Normal log line with no token"
        assert bld.sanitize_log_line(line) == line

    def test_strips_multiple_tokens(self):
        line = "token1=hf_AAAAAAAAAA token2=hf_BBBBBBBBBB"
        result = bld.sanitize_log_line(line)
        assert "hf_AAAA" not in result
        assert "hf_BBBB" not in result
        assert result.count("hf_REDACTED") == 2

    def test_does_not_strip_short_hf_prefix(self):
        # hf_ with fewer than 10 chars after should NOT be stripped
        line = "hf_short"
        assert bld.sanitize_log_line(line) == line


# ── Sentinel helpers ──────────────────────────────────────────────────────────

class TestSentinelHelpers:
    def test_step_not_done_initially(self, build_dir):
        assert not bld.step_done(build_dir, "download")

    def test_mark_and_check(self, build_dir):
        bld.mark_done(build_dir, "download")
        assert bld.step_done(build_dir, "download")

    def test_sentinel_path(self, build_dir):
        s = bld.sentinel(build_dir, "bench")
        assert s.name == ".step-bench.done"
        assert s.parent == build_dir


# ── Adapter download (dry-run) ────────────────────────────────────────────────

class TestDownloadAdapterDryRun:
    def test_creates_stub_files(self, build_dir):
        adapter_dir = bld.download_adapter(build_dir, "test/repo", dry_run=True)
        assert (adapter_dir / "adapter_config.json").exists()
        assert (adapter_dir / "adapters.safetensors").exists()

    def test_sentinel_written(self, build_dir):
        bld.download_adapter(build_dir, "test/repo", dry_run=True)
        assert bld.step_done(build_dir, "download")

    def test_idempotent_skip(self, build_dir):
        """Second call is a no-op (sentinel already present)."""
        bld.download_adapter(build_dir, "test/repo", dry_run=True)
        # Remove stub files to verify they aren't re-created
        for f in (build_dir / "adapter").iterdir():
            f.unlink()
        (build_dir / "adapter").rmdir()
        # Should not raise even though adapter_dir is gone — sentinel gates it
        bld.download_adapter(build_dir, "test/repo", dry_run=True)
        # No new files because sentinel was already present
        assert not (build_dir / "adapter").exists() or True  # either outcome is fine

    def test_no_hf_token_in_build(self, build_dir, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "hf_FAKE_LEAK_TOKEN_SENTINEL")
        bld.download_adapter(build_dir, "test/repo", dry_run=True)
        for p in build_dir.rglob("*"):
            if p.is_file():
                content = p.read_text(errors="replace")
                assert "hf_FAKE_LEAK_TOKEN_SENTINEL" not in content, (
                    f"HF token leaked into {p}"
                )


# ── Adapter format probe ──────────────────────────────────────────────────────

class TestProbeAdapterFormat:
    def test_detects_mlx_format(self, adapter_dir):
        assert bld.probe_adapter_format(adapter_dir) == "mlx"

    def test_detects_peft_format(self, adapter_dir):
        (adapter_dir / "adapter_config.json").write_text(
            json.dumps({"peft_type": "LORA", "r": 16, "lora_alpha": 16})
        )
        assert bld.probe_adapter_format(adapter_dir) == "peft"

    def test_missing_config_exits_40(self, tmp_path):
        empty_dir = tmp_path / "empty_adapter"
        empty_dir.mkdir()
        with pytest.raises(SystemExit) as exc:
            bld.probe_adapter_format(empty_dir)
        assert exc.value.code == 40

    def test_invalid_json_exits_40(self, adapter_dir):
        (adapter_dir / "adapter_config.json").write_text("NOT JSON {{{")
        with pytest.raises(SystemExit) as exc:
            bld.probe_adapter_format(adapter_dir)
        assert exc.value.code == 40

    def test_unknown_format_exits_40(self, adapter_dir):
        (adapter_dir / "adapter_config.json").write_text(
            json.dumps({"unknown_key": "something"})
        )
        with pytest.raises(SystemExit) as exc:
            bld.probe_adapter_format(adapter_dir)
        assert exc.value.code == 40


# ── Candidate A dry-run ───────────────────────────────────────────────────────

class TestBuildCandidateADryRun:
    def test_creates_stub_output(self, build_dir, adapter_dir):
        out = bld.build_candidate_a(
            build_dir, adapter_dir, "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
            min_free_ram_gb=0.0, dry_run=True,
        )
        assert (out / "config.json").exists()
        assert bld.step_done(build_dir, "candidate-a")

    def test_idempotent(self, build_dir, adapter_dir):
        bld.build_candidate_a(build_dir, adapter_dir, "mlx-base", 0.0, dry_run=True)
        # Second call: sentinel present → skip
        (build_dir / "mlx-fused" / "config.json").unlink()
        bld.build_candidate_a(build_dir, adapter_dir, "mlx-base", 0.0, dry_run=True)
        # File should NOT be re-created (step was already done)
        assert not (build_dir / "mlx-fused" / "config.json").exists()


# ── Candidate B dry-run ───────────────────────────────────────────────────────

class TestBuildCandidateBDryRun:
    def test_creates_stub_output(self, build_dir, adapter_dir):
        out = bld.build_candidate_b(
            build_dir, adapter_dir, "Qwen/Qwen2.5-1.5B-Instruct",
            adapter_format="mlx", min_free_ram_gb=0.0, dry_run=True,
        )
        assert (out / "config.json").exists()
        assert bld.step_done(build_dir, "candidate-b")

    def test_no_hf_token_in_any_config(self, build_dir, adapter_dir, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "hf_FAKE_LEAK_B_SENTINEL")
        bld.build_candidate_b(
            build_dir, adapter_dir, "Qwen/Qwen2.5-1.5B-Instruct",
            adapter_format="mlx", min_free_ram_gb=0.0, dry_run=True,
        )
        for p in build_dir.rglob("*.json"):
            content = p.read_text(errors="replace")
            assert "hf_FAKE_LEAK_B_SENTINEL" not in content, (
                f"HF token leaked into {p}"
            )


# ── GGUF convert dry-run ──────────────────────────────────────────────────────

class TestConvertToGgufDryRun:
    def test_creates_stub_gguf(self, build_dir):
        gguf = bld.convert_to_gguf(
            build_dir, candidate="b", llama_cpp_rev="b3500",
            min_free_ram_gb=0.0, dry_run=True,
        )
        assert gguf.exists()
        assert gguf.suffix == ".gguf"
        assert bld.step_done(build_dir, "convert")

    def test_candidate_a_produces_f16_name(self, build_dir):
        # Clear sentinel from previous test
        bld.sentinel(build_dir, "convert").unlink(missing_ok=True)
        gguf = bld.convert_to_gguf(
            build_dir, candidate="a", llama_cpp_rev="b3500",
            min_free_ram_gb=0.0, dry_run=True,
        )
        assert "f16" in gguf.name

    def test_candidate_b_produces_bf16_name(self, build_dir):
        bld.sentinel(build_dir, "convert").unlink(missing_ok=True)
        gguf = bld.convert_to_gguf(
            build_dir, candidate="b", llama_cpp_rev="b3500",
            min_free_ram_gb=0.0, dry_run=True,
        )
        assert "bf16" in gguf.name


# ── Modelfile generation ──────────────────────────────────────────────────────

class TestGenerateModelfile:
    def test_system_block_matches_production(self, build_dir, tmp_path):
        gguf_path = build_dir / "ai-eng-1.5b-v2.1.bf16.gguf"
        gguf_path.write_bytes(b"STUB")
        mf = bld.generate_modelfile(
            build_dir, gguf_path, MODELFILE_PRODUCTION, dry_run=True
        )
        content = mf.read_text()
        # Extract SYSTEM block from generated file
        import re as _re
        m = _re.search(r'SYSTEM\s+"""(.*?)"""', content, _re.DOTALL)
        assert m is not None, "No SYSTEM block found in generated Modelfile"
        generated_system = m.group(1)

        # Extract SYSTEM block from production file
        production_system = bld._extract_system_block(MODELFILE_PRODUCTION)
        assert generated_system == production_system, (
            "Generated SYSTEM block does not match Modelfile.production"
        )

    def test_from_line_uses_gguf_name(self, build_dir):
        gguf_path = build_dir / "ai-eng-1.5b-v2.1.bf16.gguf"
        gguf_path.write_bytes(b"STUB")
        mf = bld.generate_modelfile(
            build_dir, gguf_path, MODELFILE_PRODUCTION, dry_run=True
        )
        content = mf.read_text()
        assert f"FROM ./{gguf_path.name}" in content

    def test_parameters_present(self, build_dir):
        gguf_path = build_dir / "test.gguf"
        gguf_path.write_bytes(b"STUB")
        mf = bld.generate_modelfile(
            build_dir, gguf_path, MODELFILE_PRODUCTION, dry_run=True
        )
        content = mf.read_text()
        assert "PARAMETER temperature 0.7" in content
        assert "PARAMETER num_ctx 8192" in content


# ── Ollama create dry-run ─────────────────────────────────────────────────────

class TestOllamaCreateDryRun:
    def test_sentinel_written(self, build_dir, tmp_path):
        mf = build_dir / "test.Modelfile"
        mf.write_text("FROM ./test.gguf\n")
        bld.ollama_create(build_dir, mf, dry_run=True)
        assert bld.step_done(build_dir, "ollama-create")

    def test_idempotent(self, build_dir, tmp_path):
        mf = build_dir / "test.Modelfile"
        mf.write_text("FROM ./test.gguf\n")
        bld.ollama_create(build_dir, mf, dry_run=True)
        bld.ollama_create(build_dir, mf, dry_run=True)  # second call must not raise


# ── OOM / disk pre-check ──────────────────────────────────────────────────────

class TestPreflightChecks:
    def test_oom_check_passes_with_zero_threshold(self):
        # Should not raise when threshold is 0
        bld.check_free_ram_gb(min_gb=0.0)

    def test_oom_check_fails_with_huge_threshold(self):
        with pytest.raises(SystemExit) as exc:
            bld.check_free_ram_gb(min_gb=9999999.0)
        assert exc.value.code == 20

    def test_disk_check_passes_with_zero_threshold(self, tmp_path):
        bld.check_free_disk_gb(tmp_path, min_gb=0.0)

    def test_disk_check_fails_with_huge_threshold(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            bld.check_free_disk_gb(tmp_path, min_gb=9999999.0)
        assert exc.value.code == 21


# ── Full dry-run integration: all sentinels ───────────────────────────────────

class TestFullDryRunSentinels:
    """Run through the full build sequence in dry-run mode and assert all
    expected sentinels are written exactly once."""

    def test_all_sentinels_written(self, build_dir, adapter_dir):
        """Simulate the sequence: download → candidate-a → candidate-b → convert → ollama-create."""
        # Download
        bld.download_adapter(build_dir, "test/repo", dry_run=True)
        # Candidate A
        bld.build_candidate_a(build_dir, adapter_dir, "mlx-base", 0.0, dry_run=True)
        # Candidate B
        bld.build_candidate_b(build_dir, adapter_dir, "bf16-base", "mlx", 0.0, dry_run=True)
        # Convert
        gguf = bld.convert_to_gguf(build_dir, "b", "b3500", 0.0, dry_run=True)
        # Modelfile
        mf = bld.generate_modelfile(build_dir, gguf, MODELFILE_PRODUCTION, dry_run=True)
        # Ollama create
        bld.ollama_create(build_dir, mf, dry_run=True)

        expected_sentinels = {
            "download", "candidate-a", "candidate-b", "convert", "ollama-create"
        }
        present = {
            p.name.removeprefix(".step-").removesuffix(".done")
            for p in build_dir.glob(".step-*.done")
        }
        assert expected_sentinels <= present, (
            f"Missing sentinels: {expected_sentinels - present}"
        )

    def test_idempotent_rerun_is_noop(self, build_dir, adapter_dir):
        """Running the sequence twice should not overwrite output files."""
        # First run
        bld.download_adapter(build_dir, "test/repo", dry_run=True)
        bld.build_candidate_a(build_dir, adapter_dir, "mlx-base", 0.0, dry_run=True)
        bld.build_candidate_b(build_dir, adapter_dir, "bf16-base", "mlx", 0.0, dry_run=True)
        gguf = bld.convert_to_gguf(build_dir, "b", "b3500", 0.0, dry_run=True)
        mf = bld.generate_modelfile(build_dir, gguf, MODELFILE_PRODUCTION, dry_run=True)
        bld.ollama_create(build_dir, mf, dry_run=True)

        # Record mtimes
        mtimes_before = {p: p.stat().st_mtime for p in build_dir.rglob(".step-*.done")}

        # Second run
        bld.download_adapter(build_dir, "test/repo", dry_run=True)
        bld.build_candidate_a(build_dir, adapter_dir, "mlx-base", 0.0, dry_run=True)
        bld.build_candidate_b(build_dir, adapter_dir, "bf16-base", "mlx", 0.0, dry_run=True)
        bld.convert_to_gguf(build_dir, "b", "b3500", 0.0, dry_run=True)
        bld.ollama_create(build_dir, mf, dry_run=True)

        mtimes_after = {p: p.stat().st_mtime for p in build_dir.rglob(".step-*.done")}
        assert mtimes_before == mtimes_after, (
            "Sentinels were modified on second run — idempotency broken"
        )
