#!/usr/bin/env python3
"""
ModelRouter: Agent decision logic for model selection based on budget.

Uses model_profiles.json (from benchmark_models.py) to route experiments
to the best model for the available time + expected tokens.

Integration point for experiment runners:

    from model_router import ModelRouter

    router = ModelRouter()
    model_choice = router.select_model(
        expected_tokens=1500,
        available_seconds=300,
        prefer_cost_savings=True,
    )
    # Returns: ModelChoice(model="Qwen2.5-7B-Instruct", backend="airllm", batched=False)

Then dispatch the experiment with that model + batching preference.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ModelProfile:
    """Capability profile for a model."""

    model: str
    backend: str
    single_prompt_tps: float | None
    batched_tps: float | None
    cost_per_1m_tokens: float

    def estimate_latency_seconds(
        self,
        tokens: int,
        batched: bool = False,
    ) -> float | None:
        """Estimate wall-clock seconds for N tokens."""
        tps = self.batched_tps if batched else self.single_prompt_tps
        if not tps or tps <= 0:
            return None
        return tokens / tps


@dataclass
class ModelChoice:
    """Decision output."""

    model: str
    backend: str
    batched: bool
    estimated_seconds: float
    reason: str


class ModelRouter:
    """Route experiments to models based on latency + cost budgets."""

    def __init__(self, profiles_path: Path | str = "lab/data/model_profiles.json"):
        self.profiles_path = Path(profiles_path)
        self.profiles = self._load_profiles()

    def _load_profiles(self) -> dict[str, ModelProfile]:
        """Load model_profiles.json."""
        if not self.profiles_path.exists():
            return {}
        try:
            data = json.loads(self.profiles_path.read_text())
            profiles = {}
            for key, profile_dict in data.items():
                profiles[key] = ModelProfile(
                    model=profile_dict["model"],
                    backend=profile_dict["backend"],
                    single_prompt_tps=profile_dict.get("single_prompt_tps"),
                    batched_tps=profile_dict.get("batched_tps"),
                    cost_per_1m_tokens=profile_dict.get("cost_per_1m_tokens", 0),
                )
            return profiles
        except Exception:
            return {}

    def select_model(
        self,
        expected_tokens: int,
        available_seconds: float,
        prefer_cost_savings: bool = True,
        allow_batching: bool = True,
    ) -> ModelChoice | None:
        """
        Select the best model for the given budget.

        Args:
            expected_tokens: Est. output tokens
            available_seconds: Seconds until loop timeout
            prefer_cost_savings: If True, prefer local models; if False, prefer speed
            allow_batching: If True, can recommend batched runs (requires queuing)

        Returns:
            ModelChoice with model, backend, batched flag, estimated latency, reason
        """
        if not self.profiles:
            return None

        # Estimate fits: single-prompt vs batched
        candidates = []
        for key, profile in self.profiles.items():
            # Single-prompt path
            single_sec = profile.estimate_latency_seconds(expected_tokens, batched=False)
            if single_sec and single_sec < available_seconds - 10:  # 10s buffer
                candidates.append(
                    (
                        "single",
                        profile,
                        single_sec,
                        profile.cost_per_1m_tokens * expected_tokens / 1e6,
                    )
                )

            # Batched path (if allowed and TPS available)
            if allow_batching:
                batched_sec = profile.estimate_latency_seconds(expected_tokens, batched=True)
                if batched_sec and batched_sec < available_seconds - 10:
                    candidates.append(
                        (
                            "batched",
                            profile,
                            batched_sec,
                            profile.cost_per_1m_tokens * expected_tokens / 1e6,
                        )
                    )

        if not candidates:
            # Nothing fits; return fastest single-prompt or None
            fastest = None
            best_tps = 0
            for profile in self.profiles.values():
                tps = profile.single_prompt_tps or 0
                if tps > best_tps:
                    best_tps = tps
                    fastest = profile
            if fastest:
                sec = fastest.estimate_latency_seconds(expected_tokens, batched=False) or 999
                return ModelChoice(
                    model=fastest.model,
                    backend=fastest.backend,
                    batched=False,
                    estimated_seconds=sec,
                    reason=f"No model fits in {available_seconds}s; using fastest ({best_tps:.1f} tok/s)",
                )
            return None

        # Rank: prefer cost savings if available, else speed
        if prefer_cost_savings:
            candidates.sort(key=lambda x: (x[3], x[2]))  # Sort by cost, then latency
        else:
            candidates.sort(key=lambda x: x[2])  # Sort by latency only

        mode, profile, latency_sec, cost_usd = candidates[0]
        return ModelChoice(
            model=profile.model,
            backend=profile.backend,
            batched=mode == "batched",
            estimated_seconds=latency_sec,
            reason=(
                f"{profile.model} ({profile.backend}) "
                f"{'batched' if mode == 'batched' else 'single'}: "
                f"{latency_sec:.1f}s est. "
                f"(${cost_usd:.4f} cost)"
            ),
        )


if __name__ == "__main__":
    # Example: pick a model for a hypothetical experiment
    router = ModelRouter()
    choice = router.select_model(
        expected_tokens=2000,
        available_seconds=300,
        prefer_cost_savings=True,
    )
    if choice:
        print(f"✓ {choice.reason}")
        print(f"  Use model: {choice.model} ({choice.backend})")
        print(f"  Batched: {choice.batched}")
    else:
        print("✗ No suitable model found")
