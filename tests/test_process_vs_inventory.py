"""Tests for shared-cabinet, topologies, process, wait, shift, recommend."""

from pathlib import Path

import math

from analysis.capacity_model import (
    OpsParameters,
    ProcessConfig,
    analyze,
    shift_pulse_metrics,
)
from analysis.config_loader import load_shared_config, to_ops_parameters
from analysis.sim_engine import SimConfig, SimEngine
from analysis.wait_report import run_wait_report

ROOT = Path(__file__).resolve().parents[1]


def test_cabinet_rho_one_and_two_slots():
    base = dict(
        vehicles=24,  # λ = 24*1/24 = 1
        missions_per_vehicle_per_day=1.0,
        load_time_hours=0.5,
        offload_time_hours=0.5,
        shared_station=True,
        cabinet_slots=2,
        device_pool=50,
        ports_per_vehicle=1,
        loading_stations=1,
        offload_stations=1,
    )
    r1 = analyze(OpsParameters(**base, slots_in_use=1))
    r2 = analyze(OpsParameters(**base, slots_in_use=2))
    assert r1.cabinet_rho == 1.0
    assert r2.cabinet_rho == 0.5


def test_high_data_shared_cabinet_unstable():
    params = OpsParameters(
        vehicles=8,
        missions_per_vehicle_per_day=3,
        mission_duration_hours=2.0,
        load_time_hours=0.5,
        offload_time_hours=0.5,
        high_data_volume_mode=True,
        offload_factor=0.9,
        shared_station=True,
        cabinet_slots=2,
        slots_in_use=1,
        device_pool=40,
        ports_per_vehicle=1,
        loading_stations=1,
        offload_stations=1,
    )
    assert params.effective_offload_hours() == 1.8
    result = analyze(params)
    assert not result.cabinet_stable
    assert result.bottleneck in ("shared_station", "offload_time", "offload")


def test_shared_cabinet_fixture_loads():
    cfg = load_shared_config(ROOT / "fixtures" / "shared-cabinet.yaml")
    params = to_ops_parameters(cfg)
    assert params.shared_station is True
    assert params.cabinet_slots == 2
    assert params.slots_in_use == 1
    assert params.ports_per_vehicle == 1


def test_site_eight_fixture_loads():
    cfg = load_shared_config(ROOT / "fixtures" / "site-eight.yaml")
    params = to_ops_parameters(cfg)
    assert params.vehicles == 8
    assert params.device_pool == 8
    assert params.shared_station is True
    assert params.slots_in_use == 1
    assert params.cabinet_slots == 2
    assert params.ports_per_vehicle == 1
    result = analyze(params)
    assert result.cabinet_rho is not None
    assert result.arrival_rate_per_hour == 1.0  # 8 × 3 / 24


def test_topology_vsd_mapping_frozen():
    expected = {
        "1-1-1": (1, 1, 1),
        "2-3-2": (2, 3, 2),
        "5-3-5": (5, 3, 5),
    }
    for code, (v, s, d) in expected.items():
        cfg = load_shared_config(ROOT / "fixtures" / "topologies" / f"{code}.yaml")
        params = to_ops_parameters(cfg)
        assert params.vehicles == v
        assert params.slots_in_use == s
        assert params.device_pool == d
        assert cfg.topology_code == code


def test_process_decomposition_rate_and_compression():
    p = ProcessConfig(
        bytes_per_mission_gb=40,
        compression_ratio=0.0,
        protocol_rate_MBps=80,
        mount_overhead_hours=0.05,
        sanitize_hours=0.15,
    )
    base = OpsParameters(process=p, high_data_volume_mode=False)
    extract = base.extract_hours()
    doubled = OpsParameters(
        process=ProcessConfig(**{**p.__dict__, "protocol_rate_MBps": 160}),
        high_data_volume_mode=False,
    )
    assert abs(doubled.extract_hours() - extract / 2) < 1e-9
    assert abs(
        doubled.effective_offload_hours() - doubled.extract_hours()
        - (p.mount_overhead_hours + p.sanitize_hours)
    ) < 1e-9

    half = OpsParameters(
        process=ProcessConfig(**{**p.__dict__, "compression_ratio": 0.5}),
        high_data_volume_mode=False,
    )
    assert abs(half.extract_hours() - extract / 2) < 1e-9

    sanitize_only = OpsParameters(
        process=ProcessConfig(**{**p.__dict__, "sanitize_hours": 0.30}),
        high_data_volume_mode=False,
    )
    assert abs(sanitize_only.extract_hours() - extract) < 1e-9


def test_shift_pulse_worked_examples():
    one = shift_pulse_metrics(returns=8, servers=1, offload_hours=0.5, window_hours=2)
    assert one.t_clear_hours == 4.0
    assert one.w_last_hours == 3.5
    two = shift_pulse_metrics(returns=8, servers=2, offload_hours=0.5, window_hours=2)
    assert two.t_clear_hours == 2.0
    assert two.w_last_hours == 1.5


def test_wait_report_stops_at_missions():
    engine, rows = run_wait_report(ROOT / "fixtures" / "topologies" / "1-1-1.yaml", missions=20)
    assert engine.missions_completed >= 20
    assert any(r["device_id"] == "SUMMARY" for r in rows)


def test_wait_offload_dominates_high_data_111():
    engine, rows = run_wait_report(
        ROOT / "fixtures" / "topologies" / "1-1-1.yaml",
        missions=40,
        high_data_volume=True,
    )
    summary = next(r for r in rows if r["device_id"] == "SUMMARY")
    assert summary["wait_offload_hours"] >= summary["wait_assign_hours"]


def test_shared_sim_competes_for_one_slot():
    cfg = SimConfig(
        num_vehicles=1,
        total_devices=2,
        num_loading_stations=1,
        num_offload_stations=1,
        shared_station=True,
        ports_per_vehicle=1,
        seed_loaded_devices=1,
        mission_duration=10,
        load_time=5,
        offload_time=5,
        missions_per_vehicle_per_day=6,
        ticks_per_hour=20,
    )
    eng = SimEngine(cfg)
    eng.run_until_missions(5, max_ticks=50_000)
    assert eng.missions_completed >= 5
    assert len(eng.cabinet_stations) == 1


def test_recommend_marks_unstable():
    from analysis.recommend import build_packages, _score_package

    base = OpsParameters(
        vehicles=8,
        missions_per_vehicle_per_day=3,
        mission_duration_hours=2.0,
        load_time_hours=0.5,
        offload_time_hours=1.8,
        shared_station=True,
        cabinet_slots=2,
        slots_in_use=1,
        device_pool=2,
        ports_per_vehicle=1,
        loading_stations=1,
        offload_stations=1,
    )
    packages = dict(build_packages(base))
    baseline = _score_package("baseline", base, packages["baseline"], cycles=0, config_path=None)
    cut = _score_package("cut", base, packages["cut_T_O_50pct"], cycles=0, config_path=None)
    assert baseline["stable"] == "no" or baseline["cabinet_rho"] != ""
    # Cutting T_O should improve cabinet rho vs baseline
    if baseline["cabinet_rho"] != "" and cut["cabinet_rho"] != "":
        assert float(cut["cabinet_rho"]) < float(baseline["cabinet_rho"])
