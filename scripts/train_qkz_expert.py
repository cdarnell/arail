#!/usr/bin/env python3
"""Train the QuKaiZen expert LoRA — with a hard anti-fabrication guard.

WHY THIS EXISTS
---------------
Nucleus' ``MLXTrainer`` silently degrades to *simulation mode* when ``mlx_lm``
is unavailable. Its own docstring:

    "falls back to a simulation mode that writes a mock checkpoint and returns
     realistic metrics — allowing the full SSDP pipeline to run end-to-end
     without hardware dependencies."

That is fine for pipeline plumbing and catastrophic for producing a model. It
is almost certainly how ``models/graduated/qkz-project-aware-2b-v1.0`` came to
claim ``status: graduated`` with three passed certification gates and a 15 MB
adapter, while shipping **1,210 bytes of JSON with no tensors**.

This script makes that failure mode impossible to repeat:

  1. **Refuses to start** if the trainer would run simulated (``MLX_AVAILABLE``).
  2. **Verifies the emitted adapter contains real tensors**, and *deletes* it
     if it does not — so nothing downstream can mistake a mock for a model.

Mirrors the rule established in ``sprints/2026-07-23-clean-experience`` for the
Researcher: *measured, or it does not exist.*

The verifier is deliberately **dependency-free** — it parses the safetensors
header with stdlib only. Verifying an artifact must not require the ML stack
that produced it, or the check is worthless exactly when you need it (a box
missing ``mlx_lm`` is the box that produces fakes).

Reference numbers, measured on real artifacts (see
``sprints/2026-07-24-qkz-expert-2b/SPIKE.md`` Finding 6):

    genuine LoRA adapter : 6,822,619 bytes · 56 tensors · float32
    known-bad stub       :     1,210 bytes ·  0 tensors

Usage:
    python scripts/train_qkz_expert.py --verify-only <adapter-path>
    python scripts/train_qkz_expert.py --check-trainer
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

# A real LoRA adapter is megabytes. The known-bad stub is 1,210 bytes. 1 MB sits
# far above the fake and far below any genuine adapter we would ship.
MIN_ADAPTER_BYTES = 1_000_000
# At least one tensor must be substantial — a header full of 1-element scalars
# would otherwise pass a naive "has tensors" check.
MIN_LARGE_TENSOR_NUMEL = 1_000

_FLOAT_DTYPES = {"F16", "F32", "F64", "BF16", "F8_E4M3", "F8_E5M2"}


class SimulatedTrainerRefused(SystemExit):
    """Raised (as SystemExit) when the trainer would fabricate an artifact."""


@dataclass
class AdapterVerdict:
    """Result of inspecting a candidate adapter file."""
    path: Path
    ok: bool
    size_bytes: int = 0
    tensor_count: int = 0
    large_tensor_count: int = 0
    total_params: int = 0
    reasons: list[str] = field(default_factory=list)

    def summary(self) -> str:
        head = "REAL" if self.ok else "REJECTED"
        return (
            f"[{head}] {self.path}\n"
            f"  bytes         : {self.size_bytes:,}\n"
            f"  tensors       : {self.tensor_count}\n"
            f"  large tensors : {self.large_tensor_count} "
            f"(numel > {MIN_LARGE_TENSOR_NUMEL})\n"
            f"  params        : {self.total_params:,}\n"
            + ("".join(f"  reason        : {r}\n" for r in self.reasons))
        )


def read_safetensors_header(path: Path) -> dict:
    """Parse a safetensors header using stdlib only.

    Format: u64 little-endian header length, then that many bytes of JSON
    mapping tensor name -> {dtype, shape, data_offsets}. Raises ValueError on
    anything that is not a well-formed safetensors file.
    """
    with path.open("rb") as fh:
        raw_len = fh.read(8)
        if len(raw_len) < 8:
            raise ValueError("file is too small to contain a safetensors header")
        (header_len,) = struct.unpack("<Q", raw_len)
        if header_len <= 0 or header_len > 100_000_000:
            raise ValueError(f"implausible safetensors header length: {header_len}")
        header_bytes = fh.read(header_len)
        if len(header_bytes) < header_len:
            raise ValueError("truncated safetensors header")
    try:
        header = json.loads(header_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(f"safetensors header is not valid JSON: {exc}") from exc
    if not isinstance(header, dict):
        raise ValueError("safetensors header is not a JSON object")
    return header


def verify_real_adapter(
    path: str | Path,
    *,
    min_bytes: int = MIN_ADAPTER_BYTES,
    delete_on_failure: bool = False,
) -> AdapterVerdict:
    """Return a verdict on whether *path* is a genuine trained adapter.

    Rejects: missing files, files below ``min_bytes`` (the stub is 1,210 B),
    non-safetensors payloads, headers with no tensors, and headers whose
    tensors are all trivially small.

    ``delete_on_failure`` removes a rejected artifact so no later step can
    mistake it for a real model.
    """
    p = Path(path)
    verdict = AdapterVerdict(path=p, ok=False)

    if not p.exists():
        verdict.reasons.append("file does not exist")
        return verdict
    if p.is_dir():
        # Convenience: accept a directory containing the conventional filename.
        candidate = p / "adapters.safetensors"
        if candidate.exists():
            return verify_real_adapter(
                candidate, min_bytes=min_bytes, delete_on_failure=delete_on_failure
            )
        verdict.reasons.append(f"directory has no adapters.safetensors: {p}")
        return verdict

    verdict.size_bytes = p.stat().st_size
    if verdict.size_bytes < min_bytes:
        verdict.reasons.append(
            f"file is {verdict.size_bytes:,} bytes, below the {min_bytes:,}-byte "
            "floor — this is the signature of a simulation-mode mock checkpoint "
            "(the known-bad stub is 1,210 bytes)"
        )
        _maybe_delete(p, verdict, delete_on_failure)
        return verdict

    try:
        header = read_safetensors_header(p)
    except ValueError as exc:
        verdict.reasons.append(f"not a readable safetensors file: {exc}")
        _maybe_delete(p, verdict, delete_on_failure)
        return verdict

    for name, meta in header.items():
        if name == "__metadata__" or not isinstance(meta, dict):
            continue
        shape = meta.get("shape") or []
        if not isinstance(shape, list):
            continue
        numel = 1
        for dim in shape:
            if not isinstance(dim, int):
                numel = 0
                break
            numel *= dim
        verdict.tensor_count += 1
        verdict.total_params += numel
        if numel > MIN_LARGE_TENSOR_NUMEL and meta.get("dtype") in _FLOAT_DTYPES:
            verdict.large_tensor_count += 1

    if verdict.tensor_count == 0:
        verdict.reasons.append(
            "header declares zero tensors — metadata-only file, not weights"
        )
    if verdict.large_tensor_count == 0:
        verdict.reasons.append(
            f"no float tensor with numel > {MIN_LARGE_TENSOR_NUMEL} — "
            "an adapter with no substantial weights is not trained"
        )

    verdict.ok = not verdict.reasons
    if not verdict.ok:
        _maybe_delete(p, verdict, delete_on_failure)
    return verdict


def _maybe_delete(p: Path, verdict: AdapterVerdict, delete: bool) -> None:
    if not delete:
        return
    try:
        p.unlink()
        verdict.reasons.append(f"DELETED {p} so it cannot be mistaken for a model")
    except OSError as exc:
        verdict.reasons.append(f"could not delete rejected artifact: {exc}")


def require_real_trainer() -> None:
    """Abort unless nucleus' trainer will genuinely train.

    Imported lazily so this module stays importable (and testable) on machines
    without the nucleus package.
    """
    try:
        from nucleus.trainer.mlx_trainer import MLX_AVAILABLE  # type: ignore
    except ImportError as exc:
        raise SimulatedTrainerRefused(
            "REFUSING TO TRAIN: could not import nucleus.trainer.mlx_trainer "
            f"({exc}). Install/point at qukaizen-nucleus before training."
        ) from exc

    if not MLX_AVAILABLE:
        raise SimulatedTrainerRefused(
            "REFUSING TO TRAIN: mlx_lm is unavailable, so nucleus' MLXTrainer "
            "would silently run in SIMULATION MODE — writing a mock checkpoint "
            "and returning realistic-looking metrics.\n"
            "\n"
            "That is how models/graduated/qkz-project-aware-2b-v1.0 almost "
            "certainly came to claim three passed certification gates and a "
            "15MB adapter while shipping 1,210 bytes with no tensors.\n"
            "\n"
            "Fix: pip install mlx-lm  (Apple Silicon required), then re-run."
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="train_qkz_expert.py",
        description="Train the QuKaiZen expert LoRA with an anti-fabrication guard.",
    )
    ap.add_argument("--verify-only", metavar="PATH",
                    help="verify an existing adapter and exit (no training)")
    ap.add_argument("--check-trainer", action="store_true",
                    help="check the trainer would train for real, and exit")
    ap.add_argument("--delete-on-failure", action="store_true",
                    help="delete a rejected artifact so nothing can reuse it")
    args = ap.parse_args(argv)

    if args.verify_only:
        verdict = verify_real_adapter(
            args.verify_only, delete_on_failure=args.delete_on_failure
        )
        print(verdict.summary(), end="")
        return 0 if verdict.ok else 1

    if args.check_trainer:
        require_real_trainer()
        print("trainer check: OK — mlx_lm present, training would be real")
        return 0

    # Training itself is A3 in sprints/2026-07-24-qkz-expert-2b/ARCHITECTURE.md
    # and lands once the corpus builder (A2) exists. The guard ships first, on
    # purpose: without it, every downstream metric is unfalsifiable.
    require_real_trainer()
    print(
        "Guard passed, but the training path is not wired yet.\n"
        "Next: A2 (corpus) then A3 (training) — see "
        "sprints/2026-07-24-qkz-expert-2b/ARCHITECTURE.md",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
