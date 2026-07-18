"""Pure-math preflight estimator tests."""

from __future__ import annotations

import pytest

from arail.build.preflight import PreflightSpec, active_params_b, estimate


@pytest.fixture(autouse=True)
def _big_capacity(monkeypatch):
    """Pin capacity so the tests are machine-independent."""
    from arail.build import preflight
    monkeypatch.setattr(preflight, "_capacity", lambda: {
        "ram_gb": 32.0, "vram_gb": 24.0, "disk_gb": 200.0})


def _row(report, name_part):
    return next(r for r in report.rows if name_part in r.name)


def test_small_lora_is_green():
    report = estimate(PreflightSpec(
        params_b=3.0, precision="q4", method="lora",
        base_checkpoint="mlx-community/Qwen2.5-3B-Instruct-4bit"))
    assert report.overall == "green"
    assert not report.has_red
    assert _row(report, "VRAM").status == "green"
    assert report.est_wall_clock_hours["local"] > 0
    assert report.est_wall_clock_hours["remote"] < report.est_wall_clock_hours["local"]
    assert report.est_anthropic_cost_usd > 0


def test_20b_full_finetune_is_red_on_vram():
    report = estimate(PreflightSpec(params_b=20.0, precision="bf16",
                                    method="full",
                                    base_checkpoint="some/base"))
    assert _row(report, "VRAM").status == "red"
    assert report.has_red
    assert report.overall == "red"


def test_moe_active_params_below_dense():
    dense = PreflightSpec(params_b=20.0, arch="dense")
    moe = PreflightSpec(params_b=20.0, arch="moe",
                        moe={"num_experts": 32, "top_k": 4})
    assert active_params_b(moe) < active_params_b(dense)
    # gpt-oss-20b-ish shape: ~4/32 experts active → well under half the params.
    assert active_params_b(moe) < 20.0 * 0.55


def test_from_scratch_flags_amber():
    report = estimate(PreflightSpec(params_b=1.0, base_checkpoint=None))
    assert _row(report, "checkpoint").status == "amber"


def test_remote_target_skips_local_vram_gate():
    report = estimate(PreflightSpec(params_b=20.0, precision="bf16",
                                    method="full", compute_target="remote",
                                    base_checkpoint="some/base"))
    assert not any("VRAM" in r.name and r.status == "red" for r in report.rows)


def test_report_serializes():
    d = estimate(PreflightSpec()).to_dict()
    assert {"rows", "overall", "est_wall_clock_hours",
            "est_anthropic_cost_usd"} <= set(d)
