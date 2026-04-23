"""arail.experiments.tuning — config/tuning.yml loader with schema
validation.

The autoresearch agent is ONLY allowed to change values of knobs
listed in the `knobs` section. Any proposed value must pass
`validate_knob_value` before it lands on disk. That function is
the whole safety contract — everywhere else in this module just
serializes state.

We deliberately don't use pydantic/attrs here. A 100-line
hand-rolled schema is easier to audit than a generic library for
something this small, and this file is on the safety-critical path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None  # handled in load/save


# Path to the tracked config file. The autoresearch loop will write
# to this path as part of a commit — it must stay under version
# control at all times.
def _default_tuning_path() -> Path:
    # config/ sits at the repo root. We walk up from this file to
    # find it — two parents gets us to src/, three gets us to root.
    here = Path(__file__).resolve()
    return here.parent.parent.parent.parent / "config" / "tuning.yml"


@dataclass
class Knob:
    """One tunable knob with schema and current value."""
    name: str
    current: Any
    schema_type: str              # "string" | "int" | "bool"
    choices: Optional[List[Any]]  # for string enums
    min_value: Optional[int]      # for int range
    max_value: Optional[int]      # for int range
    rationale: str

    def validate(self, value: Any) -> tuple[bool, str]:
        """Check whether `value` is a legal setting for this knob.
        Returns (ok, reason)."""
        if self.schema_type == "bool":
            if not isinstance(value, bool):
                return False, f"expected bool, got {type(value).__name__}"
            return True, ""
        if self.schema_type == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                return False, f"expected int, got {type(value).__name__}"
            if self.min_value is not None and value < self.min_value:
                return False, f"below minimum ({self.min_value})"
            if self.max_value is not None and value > self.max_value:
                return False, f"above maximum ({self.max_value})"
            return True, ""
        if self.schema_type == "string":
            if not isinstance(value, str):
                return False, f"expected string, got {type(value).__name__}"
            if self.choices is not None and value not in self.choices:
                return False, (
                    f"not in allowed choices: {self.choices}"
                )
            return True, ""
        return False, f"unknown schema type: {self.schema_type}"


@dataclass
class ResearchModel:
    name: str
    precision: str
    expected_disk_gb: int
    family: str
    active_params_b: float
    total_params_b: float
    huggingface_id: str


@dataclass
class FrontierModel:
    """A model that exceeds every single-GPU memory ceiling available
    today (H100 / H200 / B200). The loop attempts to bench it; until
    the MLX streaming layer is built, every attempt records an honest
    status="error" row.

    `gpu_fit` is a dict keyed by GPU tier (e.g. "h100_80gb"). Values
    are bools — True means the model's 4-bit weights fit resident on
    that GPU class. False is the interesting case (that's the whole
    point of listing it here).
    """
    name: str
    huggingface_id: str
    family: str
    active_params_b: float
    total_params_b: float
    precision: str
    expected_disk_gb: int
    streaming_required: bool
    gpu_fit: Dict[str, bool]
    rationale: str = ""


@dataclass
class TuningConfig:
    """The full tunables document, hydrated from disk.

    Two baseline stores travel in parallel (MLX track only — the
    CUDA AeroLLM config keeps frontier_baselines empty):

      - baseline_metrics    : 1 stable reference (the research_model).
      - frontier_baselines  : dict keyed by huggingface_id. Each value
                              is the same shape as baseline_metrics.
                              Populated once streaming can actually
                              load the model; empty until then.
    """
    research_model: ResearchModel
    small_models: List[Dict[str, Any]]
    baseline_commit: Optional[str]
    baseline_metrics: Optional[Dict[str, Any]]
    baseline_prompt: str
    baseline_max_tokens: int
    knobs: Dict[str, Knob] = field(default_factory=dict)
    frontier_models: List[FrontierModel] = field(default_factory=list)
    frontier_baselines: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def knob_values(self) -> Dict[str, Any]:
        return {k: v.current for k, v in self.knobs.items()}

    def set_knob(self, name: str, value: Any) -> tuple[bool, str]:
        if name not in self.knobs:
            return False, f"unknown knob: {name}"
        ok, reason = self.knobs[name].validate(value)
        if not ok:
            return False, reason
        self.knobs[name].current = value
        return True, ""


def load_tuning(path: Path | None = None) -> TuningConfig:
    """Read tuning.yml and materialize a TuningConfig. Raises
    FileNotFoundError if missing, ValueError if the file is malformed
    or has no research_model, knobs, etc."""
    if yaml is None:
        raise RuntimeError(
            "PyYAML not installed. Run: pip install pyyaml"
        )
    path = path or _default_tuning_path()
    if not path.exists():
        raise FileNotFoundError(f"tuning config missing: {path}")
    raw = yaml.safe_load(path.read_text()) or {}

    rm = raw.get("research_model") or {}
    if not rm.get("name"):
        raise ValueError("tuning.yml: research_model.name is required")
    research = ResearchModel(
        name=rm["name"],
        precision=rm.get("precision", "fp16"),
        expected_disk_gb=int(rm.get("expected_disk_gb", 0)),
        family=rm.get("family", "dense"),
        active_params_b=float(rm.get("active_params_b", 0)),
        total_params_b=float(rm.get("total_params_b", 0)),
        huggingface_id=rm.get("huggingface_id", rm["name"]),
    )

    knobs_raw = raw.get("knobs") or {}
    knobs: Dict[str, Knob] = {}
    for name, entry in knobs_raw.items():
        schema = entry.get("schema") or {}
        knobs[name] = Knob(
            name=name,
            current=entry.get("current"),
            schema_type=schema.get("type", "string"),
            choices=schema.get("choices"),
            min_value=schema.get("min"),
            max_value=schema.get("max"),
            rationale=(schema.get("rationale") or "").strip(),
        )

    # Frontier models — optional. The CUDA AeroLLM config doesn't
    # include them; the MLX config lists "doesn't fit any single GPU"
    # targets.
    frontier_raw = raw.get("frontier_models") or []
    frontier_models: List[FrontierModel] = []
    for entry in frontier_raw:
        if not isinstance(entry, dict):
            continue
        # Skip entries that are missing the required fields rather than
        # crashing — better to surface a clean "no frontier models" in
        # the UI than a parse error that blocks the whole page.
        hf_id = entry.get("huggingface_id")
        if not hf_id:
            continue
        frontier_models.append(FrontierModel(
            name=entry.get("name", hf_id),
            huggingface_id=hf_id,
            family=entry.get("family", "dense"),
            active_params_b=float(entry.get("active_params_b", 0) or 0),
            total_params_b=float(entry.get("total_params_b", 0) or 0),
            precision=entry.get("precision", "q4"),
            expected_disk_gb=int(entry.get("expected_disk_gb", 0) or 0),
            streaming_required=bool(entry.get("streaming_required", False)),
            gpu_fit=dict(entry.get("gpu_fit") or {}),
            rationale=(entry.get("rationale") or "").strip(),
        ))

    frontier_baselines = dict(raw.get("frontier_baselines") or {})

    return TuningConfig(
        research_model=research,
        small_models=list(raw.get("small_models") or []),
        baseline_commit=raw.get("baseline_commit"),
        baseline_metrics=raw.get("baseline_metrics"),
        baseline_prompt=raw.get("baseline_prompt", ""),
        baseline_max_tokens=int(raw.get("baseline_max_tokens", 64)),
        knobs=knobs,
        frontier_models=frontier_models,
        frontier_baselines=frontier_baselines,
    )


def save_tuning(cfg: TuningConfig, path: Path | None = None) -> None:
    """Write a TuningConfig back to disk. Preserves only the shape
    load_tuning expects — comments in the source file are lost
    (PyYAML roundtripping doesn't preserve them). This is acceptable
    because the agent's edits should be minimal-delta; humans edit
    the file with comments intact."""
    if yaml is None:
        raise RuntimeError(
            "PyYAML not installed. Run: pip install pyyaml"
        )
    path = path or _default_tuning_path()
    doc: Dict[str, Any] = {
        "research_model": {
            "name": cfg.research_model.name,
            "precision": cfg.research_model.precision,
            "expected_disk_gb": cfg.research_model.expected_disk_gb,
            "family": cfg.research_model.family,
            "active_params_b": cfg.research_model.active_params_b,
            "total_params_b": cfg.research_model.total_params_b,
            "huggingface_id": cfg.research_model.huggingface_id,
        },
        "small_models": cfg.small_models,
        "baseline_commit": cfg.baseline_commit,
        "baseline_metrics": cfg.baseline_metrics,
        "baseline_prompt": cfg.baseline_prompt,
        "baseline_max_tokens": cfg.baseline_max_tokens,
        "knobs": {
            name: {
                "current": knob.current,
                "schema": _knob_schema_dict(knob),
            }
            for name, knob in cfg.knobs.items()
        },
    }
    # Only emit the frontier block when it's actually present in the
    # config — keeps the CUDA AeroLLM YAML free of Apple-specific
    # fields.
    if cfg.frontier_models:
        doc["frontier_models"] = [
            {
                "name": fm.name,
                "huggingface_id": fm.huggingface_id,
                "family": fm.family,
                "active_params_b": fm.active_params_b,
                "total_params_b": fm.total_params_b,
                "precision": fm.precision,
                "expected_disk_gb": fm.expected_disk_gb,
                "streaming_required": fm.streaming_required,
                "gpu_fit": dict(fm.gpu_fit),
                "rationale": fm.rationale + ("\n" if fm.rationale else ""),
            }
            for fm in cfg.frontier_models
        ]
    if cfg.frontier_baselines:
        doc["frontier_baselines"] = dict(cfg.frontier_baselines)
    path.write_text(yaml.safe_dump(doc, sort_keys=False))


def _knob_schema_dict(knob: Knob) -> Dict[str, Any]:
    s: Dict[str, Any] = {"type": knob.schema_type}
    if knob.choices is not None:
        s["choices"] = knob.choices
    if knob.min_value is not None:
        s["min"] = knob.min_value
    if knob.max_value is not None:
        s["max"] = knob.max_value
    if knob.rationale:
        s["rationale"] = knob.rationale + "\n"
    return s


def validate_knob_value(cfg: TuningConfig, name: str, value: Any) -> tuple[bool, str]:
    """Standalone validator — used by the HTTP layer before writing."""
    if name not in cfg.knobs:
        return False, f"unknown knob: {name}"
    return cfg.knobs[name].validate(value)
