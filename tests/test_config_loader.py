"""Tests for shared YAML config and tick/hour conversion."""

from pathlib import Path

from analysis.config_loader import (
    hours_to_ticks,
    load_shared_config,
    ops_from_sim_sliders,
    ticks_to_hours,
    to_ops_parameters,
)
from analysis.capacity_model import analyze

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "fixtures" / "baseline.yaml"


def test_baseline_yaml_loads():
    cfg = load_shared_config(BASELINE)
    assert cfg.scenario_id == "baseline"
    assert cfg.ticks_per_hour == 20
    assert cfg.mission_duration_ticks == 40
    assert cfg.process_time_ticks == 10


def test_tick_hour_roundtrip():
    assert hours_to_ticks(2.0, 20) == 40
    assert hours_to_ticks(0.5, 20) == 10
    assert ticks_to_hours(40, 20) == 2.0


def test_ops_from_sim_sliders_matches_yaml_analysis():
    cfg = load_shared_config(BASELINE)
    params_yaml = to_ops_parameters(cfg)
    params_sim = ops_from_sim_sliders(
        vehicles=cfg.vehicles,
        missions_per_vehicle_per_day=cfg.missions_per_vehicle_per_day,
        device_pool=cfg.device_pool,
        loading_stations=cfg.loading_stations,
        offload_stations=cfg.offload_stations,
        mission_ticks=cfg.mission_duration_ticks,
        process_ticks=cfg.process_time_ticks,
        ticks_per_hour=cfg.ticks_per_hour,
        operating_hours_per_day=cfg.operating_hours_per_day,
        utilization_target=cfg.utilization_target,
        device_buffer_fraction=cfg.device_buffer_fraction,
        ports_per_vehicle=cfg.ports_per_vehicle,
    )
    r_yaml = analyze(params_yaml)
    r_sim = analyze(params_sim)
    assert r_yaml.bottleneck == r_sim.bottleneck
    assert r_yaml.devices_recommended == r_sim.devices_recommended


def test_cli_config_flag():
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, "-m", "analysis.capacity_model", "--config", str(BASELINE), "--format", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "bottleneck" in r.stdout
