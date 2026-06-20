"""Analysis vs discrete sim regression tests."""

from pathlib import Path

import pytest

from analysis.capacity_model import OpsParameters, analyze
from analysis.config_loader import load_shared_config, to_ops_parameters
from analysis.observed import infer_observed_bottleneck
from analysis.regression import load_regression_cases, run_case
from analysis.sim_engine import SimConfig, SimEngine

ROOT = Path(__file__).resolve().parents[1]
REGRESSION = ROOT / "fixtures" / "regression_scenarios.yaml"


@pytest.fixture(scope="module")
def regression_outcomes():
    return [run_case(c) for c in load_regression_cases(REGRESSION)]


def test_all_regression_scenarios_align(regression_outcomes):
    failed = [o for o in regression_outcomes if not o.aligned]
    details = ", ".join(
        f"{o.name}(pred={o.predicted_bottleneck},obs={o.observed_bottleneck})" for o in failed
    )
    assert not failed, f"Misaligned scenarios: {details}"


def test_baseline_sim_reaches_steady_low_queues():
    cfg = load_shared_config(ROOT / "fixtures" / "baseline.yaml")
    sim_cfg = SimConfig(
        num_vehicles=cfg.vehicles,
        total_devices=cfg.device_pool,
        num_loading_stations=cfg.loading_stations,
        num_offload_stations=cfg.offload_stations,
        mission_duration=cfg.mission_duration_ticks,
        process_time=cfg.process_time_ticks,
        missions_per_vehicle_per_day=cfg.missions_per_vehicle_per_day,
        ticks_per_hour=cfg.ticks_per_hour,
        operating_hours_per_day=cfg.operating_hours_per_day,
    )
    engine = SimEngine(sim_cfg)
    result = engine.run_until_steady(max_ticks=6000, ticks_per_hour=cfg.ticks_per_hour)
    assert result.metrics.offload_queue < 3
    assert result.metrics.loading_queue < 3
    assert result.metrics.waiting_vehicles == 0


def test_offload_saturated_sim_matches_prediction():
    params = OpsParameters(
        vehicles=10,
        missions_per_vehicle_per_day=8,
        process_time_hours=0.5,
        loading_stations=2,
        offload_stations=1,
        device_pool=40,
    )
    predicted = analyze(params)
    assert predicted.bottleneck == "offload"

    engine = SimEngine(
        SimConfig(
            num_vehicles=10,
            total_devices=40,
            num_loading_stations=2,
            num_offload_stations=1,
            mission_duration=40,
            process_time=10,
        )
    )
    result = engine.run_until_steady()
    observed = infer_observed_bottleneck(result.metrics)
    assert observed in ("offload", "devices")
    assert result.metrics.offload_queue >= 3
