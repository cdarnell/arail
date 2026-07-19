"""Build preflight — heuristic resource + wall-clock estimator.

Pure and dependency-light (psutil/shutil for capacity only) so the panel
works fully even when the nucleus orchestrator is offline. Every output is
an ESTIMATE and labeled as such in the UI; the point is honest green/amber/
red gating, not accounting-grade numbers.

Gating contract: any RED row blocks POST /api/build/start unless the caller
passes override_red=true (recorded in the job ledger + activity log).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# Bytes per parameter by precision.
_BYTES_PER_PARAM = {"bf16": 2.0, "fp16": 2.0, "q8": 1.0, "q4": 0.55}

# Rough tokens/sec by (device_class, method) for ~1B active params; scaled
# inversely with active params. Seeded conservatively for Apple-Silicon
# unified memory; overridden by measured profiles when available.
_BASE_TPS = {
    ("local", "lora"): 550.0,
    ("local", "qlora"): 420.0,
    ("local", "full"): 140.0,
    ("remote", "lora"): 2800.0,
    ("remote", "qlora"): 2200.0,
    ("remote", "full"): 1100.0,
}

# Anthropic teacher pricing (USD per Mtok) — mirrors the nucleus teacher
# backend's 2026-05 table; used only for the accelerated-option estimate.
_ANTHROPIC_PRICING = {"input_per_mtok": 15.0, "output_per_mtok": 75.0}

# Distillation teacher volume heuristic: tokens the teacher must generate
# per token of final training corpus (drafts, rejects, tier-2 escalation).
_TEACHER_AMPLIFICATION = 2.6


@dataclass
class PreflightSpec:
    dataset_source: str = ""            # path or hf-id or "kice" (generated)
    dataset_tokens_est: int = 20_000_000
    tokenizer: str = "auto"
    seq_len: int = 4096
    base_checkpoint: Optional[str] = None   # None => from scratch
    arch: str = "dense"                 # dense | moe
    moe: Optional[Dict[str, Any]] = None    # {num_experts, top_k}
    params_b: float = 3.0
    precision: str = "q4"               # bf16 | fp16 | q8 | q4
    method: str = "lora"                # lora | qlora | full
    batch_size: int = 4
    grad_accum: int = 4
    epochs: float = 1.0
    compute_target: str = "local"       # local | remote
    keep_checkpoints: int = 3

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PreflightSpec":
        known = {f: d[f] for f in cls.__dataclass_fields__ if f in d}
        return cls(**known)


@dataclass
class Requirement:
    name: str
    required: str
    available: str
    status: str          # green | amber | red
    note: str = ""


@dataclass
class PreflightReport:
    rows: List[Requirement] = field(default_factory=list)
    overall: str = "green"
    est_wall_clock_hours: Dict[str, float] = field(default_factory=dict)
    est_peak_vram_gb: float = 0.0
    est_disk_gb: float = 0.0
    est_teacher_tokens: int = 0
    est_anthropic_cost_usd: float = 0.0
    active_params_b: float = 0.0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def has_red(self) -> bool:
        return any(r.status == "red" for r in self.rows)


def _status(required: float, available: float) -> str:
    """green with ≥15% headroom, amber inside the margin, red over capacity."""
    if available <= 0:
        return "red"
    if required > available:
        return "red"
    if required > available * 0.85:
        return "amber"
    return "green"


def active_params_b(spec: PreflightSpec) -> float:
    if spec.arch != "moe" or not spec.moe:
        return spec.params_b
    experts = max(int(spec.moe.get("num_experts", 8)), 1)
    top_k = max(int(spec.moe.get("top_k", 2)), 1)
    # ~55% of a MoE checkpoint's params sit in expert FFNs; attention/
    # embeddings are always active.
    expert_fraction = 0.55
    return spec.params_b * ((1 - expert_fraction)
                            + expert_fraction * min(top_k / experts, 1.0))


def _capacity() -> Dict[str, float]:
    ram_gb = 0.0
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    except Exception:  # noqa: BLE001
        pass
    models_dir = os.getenv("ARAIL_MODELS_DIR", "lab/models")
    disk_gb = 0.0
    try:
        probe = models_dir if os.path.isdir(models_dir) else "."
        disk_gb = shutil.disk_usage(probe).free / (1024 ** 3)
    except Exception:  # noqa: BLE001
        pass
    # Apple-Silicon unified memory: GPU-addressable ≈ 75% of RAM (Metal
    # wired ceiling); a discrete-GPU path would read nvidia-smi instead.
    return {"ram_gb": ram_gb, "vram_gb": ram_gb * 0.75, "disk_gb": disk_gb}


def _measured_tps(active_b: float, method: str, target: str) -> float:
    """Prefer measured throughput from lab/data/model_profiles.json."""
    base = _BASE_TPS.get((target, method), 300.0)
    tps = base / max(active_b, 0.25)
    try:
        import json
        from arail.config import DATA_DIR
        profiles = json.loads((DATA_DIR / "model_profiles.json").read_text())
        rates = [v.get("tokens_per_sec") for v in profiles.values()
                 if isinstance(v, dict) and v.get("tokens_per_sec")]
        if rates and target == "local":
            # Inference tps ≈ 3× training tps on the same silicon.
            tps = max(tps, (sum(rates) / len(rates)) / 3.0 / max(active_b, 0.25))
    except Exception:  # noqa: BLE001
        pass
    return tps


def estimate(spec: PreflightSpec) -> PreflightReport:
    cap = _capacity()
    report = PreflightReport()
    active_b = active_params_b(spec)
    report.active_params_b = round(active_b, 3)

    bpp = _BYTES_PER_PARAM.get(spec.precision, 2.0)
    weights_gb = spec.params_b * 1e9 * bpp / (1024 ** 3)

    # Optimizer + gradients.
    if spec.method == "full":
        # AdamW moments (8 B/param fp32) + gradients (2 B/param) over ALL params.
        opt_gb = spec.params_b * 1e9 * 10 / (1024 ** 3)
    else:
        # (Q)LoRA: adapters are ~1% of params; base stays frozen.
        adapter_params = spec.params_b * 1e9 * 0.01
        opt_gb = adapter_params * 12 / (1024 ** 3)

    # Activations scale with batch × seq_len × hidden; hidden ≈ params^(1/3).
    hidden_est = 1024 * max(spec.params_b, 0.1) ** (1 / 3)
    act_gb = (spec.batch_size * spec.seq_len * hidden_est * 2 * 48
              / (1024 ** 3))

    peak_vram = (weights_gb + opt_gb + act_gb) * 1.2   # +20% headroom
    report.est_peak_vram_gb = round(peak_vram, 1)

    dataset_gb = spec.dataset_tokens_est * 4 / (1024 ** 3)   # ~4 B/token raw
    ckpt_gb = weights_gb if spec.method == "full" else max(weights_gb * 0.02, 0.1)
    disk_gb = weights_gb + dataset_gb + ckpt_gb * spec.keep_checkpoints + 2.0
    report.est_disk_gb = round(disk_gb, 1)

    train_tokens = spec.dataset_tokens_est * spec.epochs
    for target in ("local", "remote"):
        tps = _measured_tps(active_b, spec.method, target)
        report.est_wall_clock_hours[target] = round(
            train_tokens / max(tps, 1.0) / 3600.0, 2)
    # Teacher-side estimate (distillation corpus generation, accelerated path).
    report.est_teacher_tokens = int(spec.dataset_tokens_est
                                    * _TEACHER_AMPLIFICATION)
    report.est_anthropic_cost_usd = round(
        report.est_teacher_tokens / 1e6
        * (_ANTHROPIC_PRICING["input_per_mtok"] * 0.35
           + _ANTHROPIC_PRICING["output_per_mtok"] * 0.65), 2)

    rows = report.rows
    if spec.compute_target == "local":
        rows.append(Requirement(
            "Peak VRAM (unified memory)",
            f"{peak_vram:.1f} GB", f"{cap['vram_gb']:.1f} GB",
            _status(peak_vram, cap["vram_gb"]),
            "estimate: weights + optimizer + activations + 20% headroom"))
        rows.append(Requirement(
            "System RAM",
            f"{peak_vram * 1.1:.1f} GB", f"{cap['ram_gb']:.1f} GB",
            _status(peak_vram * 1.1, cap["ram_gb"])))
    else:
        rows.append(Requirement(
            "Remote compute", "gateway reachable + key",
            "see gate on the build option", "green",
            "training runs remotely; local VRAM not required"))
    rows.append(Requirement(
        "Disk", f"{disk_gb:.1f} GB", f"{cap['disk_gb']:.1f} GB",
        _status(disk_gb, cap["disk_gb"]),
        "base + dataset + kept checkpoints"))
    rows.append(Requirement(
        "Dataset", spec.dataset_source or "KICE-generated corpus",
        f"~{spec.dataset_tokens_est / 1e6:.0f}M tokens @ seq {spec.seq_len}",
        "green" if spec.dataset_tokens_est > 0 else "red",
        f"tokenizer: {spec.tokenizer}"))
    rows.append(Requirement(
        "Base checkpoint",
        spec.base_checkpoint or "from scratch",
        "provided" if spec.base_checkpoint else "—",
        "green" if spec.base_checkpoint else "amber",
        "" if spec.base_checkpoint else
        "from-scratch training multiplies time & data needs"))
    if spec.arch == "moe":
        moe = spec.moe or {}
        rows.append(Requirement(
            "Architecture",
            f"MoE {spec.params_b}B ({moe.get('num_experts', '?')} experts, "
            f"top-{moe.get('top_k', '?')})",
            f"~{active_b:.2f}B active/token", "green",
            "MoE-preferred: dense-like quality at lower active compute"))
    else:
        rows.append(Requirement(
            "Architecture", f"dense {spec.params_b}B",
            f"{spec.params_b}B active/token", "green"))

    report.overall = ("red" if report.has_red else
                      "amber" if any(r.status == "amber" for r in rows)
                      else "green")
    report.notes.append(
        "All figures are heuristic estimates; a Dry run validates the "
        "config against the real pipeline without training.")
    return report
