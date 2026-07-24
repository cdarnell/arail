"""Anti-fabrication guard for QuKaiZen expert training (sprint 2026-07-24).

Nucleus' MLXTrainer silently falls back to simulation mode when mlx_lm is
missing — writing a mock checkpoint with realistic metrics. That almost
certainly produced the shipped qkz-project-aware-2b-v1.0 "graduated" adapter:
1,210 bytes, zero tensors, yet claiming three passed cert gates and 15MB.

These tests pin the guard that makes it impossible to repeat. Reference numbers
come from real artifacts measured in the A0 spike (SPIKE.md Finding 6):

    genuine adapter : 6,822,619 bytes · 56 tensors · float32
    known-bad stub  :     1,210 bytes ·  0 tensors
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from train_qkz_expert import (  # noqa: E402
    MIN_ADAPTER_BYTES,
    SimulatedTrainerRefused,
    read_safetensors_header,
    require_real_trainer,
    verify_real_adapter,
)


def _write_safetensors(path: Path, tensors: dict[str, tuple[str, list[int]]],
                       pad_to: int = 0) -> Path:
    """Hand-build a minimal safetensors file (stdlib only, no ML deps).

    ``tensors`` maps name -> (dtype, shape). Data is zero-filled; the guard
    inspects the header, not the values.
    """
    header: dict[str, dict] = {}
    offset = 0
    for name, (dtype, shape) in tensors.items():
        numel = 1
        for d in shape:
            numel *= d
        width = {"F32": 4, "F16": 2, "BF16": 2, "F64": 8, "I64": 8}.get(dtype, 4)
        nbytes = numel * width
        header[name] = {"dtype": dtype, "shape": shape,
                        "data_offsets": [offset, offset + nbytes]}
        offset += nbytes
    blob = json.dumps(header).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(struct.pack("<Q", len(blob)))
        fh.write(blob)
        fh.write(b"\0" * offset)
        if pad_to and (cur := 8 + len(blob) + offset) < pad_to:
            fh.write(b"\0" * (pad_to - cur))
    return path


# ── the guard refuses a simulating trainer ──────────────────────────

def test_require_real_trainer_refuses_when_mlx_missing(monkeypatch):
    """The whole point: if mlx_lm is absent the trainer would fabricate, so we
    must abort BEFORE producing anything."""
    import types
    fake = types.ModuleType("nucleus.trainer.mlx_trainer")
    fake.MLX_AVAILABLE = False
    monkeypatch.setitem(sys.modules, "nucleus", types.ModuleType("nucleus"))
    monkeypatch.setitem(sys.modules, "nucleus.trainer", types.ModuleType("nucleus.trainer"))
    monkeypatch.setitem(sys.modules, "nucleus.trainer.mlx_trainer", fake)

    with pytest.raises(SimulatedTrainerRefused) as exc:
        require_real_trainer()
    msg = str(exc.value)
    assert "SIMULATION MODE" in msg
    assert "1,210 bytes" in msg, "the message should cite the known-bad artifact"


def test_require_real_trainer_passes_when_mlx_present(monkeypatch):
    import types
    fake = types.ModuleType("nucleus.trainer.mlx_trainer")
    fake.MLX_AVAILABLE = True
    monkeypatch.setitem(sys.modules, "nucleus", types.ModuleType("nucleus"))
    monkeypatch.setitem(sys.modules, "nucleus.trainer", types.ModuleType("nucleus.trainer"))
    monkeypatch.setitem(sys.modules, "nucleus.trainer.mlx_trainer", fake)
    require_real_trainer()  # must not raise


def test_require_real_trainer_refuses_when_nucleus_absent(monkeypatch):
    """A missing trainer must fail loudly, not fall through to 'training'."""
    monkeypatch.setitem(sys.modules, "nucleus", None)
    with pytest.raises(SimulatedTrainerRefused):
        require_real_trainer()


# ── the verifier separates real weights from mocks ──────────────────

def test_accepts_a_realistic_adapter(tmp_path):
    """Shaped like the real spike output: 56 float32 LoRA tensors."""
    tensors = {}
    for i in range(28):
        tensors[f"layers.{i}.lora_a"] = ("F32", [12288, 8])
        tensors[f"layers.{i}.lora_b"] = ("F32", [8, 12288])
    p = _write_safetensors(tmp_path / "adapters.safetensors", tensors)
    v = verify_real_adapter(p)
    assert v.ok, v.summary()
    assert v.tensor_count == 56
    assert v.large_tensor_count == 56
    assert v.size_bytes > MIN_ADAPTER_BYTES


def test_rejects_tiny_stub(tmp_path):
    """A 1,210-byte metadata-only file is the fabrication signature."""
    p = tmp_path / "adapters.safetensors"
    p.write_bytes(b'{"__metadata__": {"note": "mock"}}'.ljust(1210, b" "))
    v = verify_real_adapter(p)
    assert not v.ok
    assert any("below the" in r for r in v.reasons)


def test_rejects_header_with_no_tensors(tmp_path):
    """Big enough to pass the size floor, but declares no weights."""
    p = _write_safetensors(tmp_path / "empty.safetensors", {}, pad_to=MIN_ADAPTER_BYTES + 10)
    v = verify_real_adapter(p)
    assert not v.ok
    assert any("zero tensors" in r for r in v.reasons)


def test_rejects_only_trivial_tensors(tmp_path):
    """Padded to size and full of scalars — passes a naive 'has tensors' check
    but is not a trained adapter."""
    tensors = {f"scalar.{i}": ("F32", [2, 2]) for i in range(20)}
    p = _write_safetensors(tmp_path / "trivial.safetensors", tensors,
                           pad_to=MIN_ADAPTER_BYTES + 10)
    v = verify_real_adapter(p)
    assert not v.ok
    assert any("numel >" in r for r in v.reasons)


def test_rejects_non_safetensors_payload(tmp_path):
    p = tmp_path / "junk.safetensors"
    p.write_bytes(b"\xff" * (MIN_ADAPTER_BYTES + 10))
    v = verify_real_adapter(p)
    assert not v.ok
    assert any("not a readable safetensors" in r for r in v.reasons)


def test_rejects_missing_file(tmp_path):
    v = verify_real_adapter(tmp_path / "nope.safetensors")
    assert not v.ok
    assert any("does not exist" in r for r in v.reasons)


def test_resolves_directory_to_conventional_filename(tmp_path):
    tensors = {f"l{i}.lora_a": ("F32", [12288, 8]) for i in range(20)}
    _write_safetensors(tmp_path / "adapters.safetensors", tensors)
    v = verify_real_adapter(tmp_path)
    assert v.ok, v.summary()


def test_delete_on_failure_removes_the_mock(tmp_path):
    """A rejected artifact must not survive to be mistaken for a model."""
    p = tmp_path / "adapters.safetensors"
    p.write_bytes(b"mock")
    v = verify_real_adapter(p, delete_on_failure=True)
    assert not v.ok
    assert not p.exists(), "rejected artifact should have been deleted"
    assert any("DELETED" in r for r in v.reasons)


def test_delete_on_failure_never_touches_a_good_adapter(tmp_path):
    tensors = {f"l{i}.lora_a": ("F32", [12288, 8]) for i in range(20)}
    p = _write_safetensors(tmp_path / "adapters.safetensors", tensors)
    v = verify_real_adapter(p, delete_on_failure=True)
    assert v.ok and p.exists()


# ── regression against the REAL shipped artifact ────────────────────

def test_rejects_the_actual_shipped_stub():
    """The v1.0 'graduated' adapter must be rejected by name.

    This is the artifact that claimed three passed cert gates and a 15MB
    adapter. If this ever passes, the guard has regressed.
    """
    stub = (REPO_ROOT / "models" / "graduated" / "qkz-project-aware-2b-v1.0"
            / "adapters" / "adapters.safetensors.placeholder")
    if not stub.exists():
        pytest.skip("shipped stub not present in this checkout")
    assert stub.stat().st_size < 2000, "fixture changed; revisit this test"
    v = verify_real_adapter(stub)
    assert not v.ok, "the known-fake adapter must never verify as real"


def test_header_reader_rejects_truncated_file(tmp_path):
    p = tmp_path / "trunc.safetensors"
    p.write_bytes(struct.pack("<Q", 500) + b"{}")
    with pytest.raises(ValueError):
        read_safetensors_header(p)
