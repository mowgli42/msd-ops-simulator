"""Tests for MSD capacity model."""

from analysis.capacity_model import OpsParameters, analyze, erlang_c, stations_required


def test_erlang_c_stable_low_load():
    # Low traffic — most arrivals should not wait
    pw = erlang_c(lambda_rate=0.5, mu=2.0, servers=2)
    assert 0.0 <= pw < 0.5


def test_erlang_c_saturated():
    pw = erlang_c(lambda_rate=4.0, mu=1.0, servers=2)
    assert pw == 1.0


def test_stations_required():
    assert stations_required(lambda_rate=1.0, mu=2.0, utilization_target=0.85) == 1
    assert stations_required(lambda_rate=2.0, mu=2.0, utilization_target=0.85) == 2


def test_baseline_scenario_stable():
    params = OpsParameters(
        vehicles=8,
        missions_per_vehicle_per_day=3,
        mission_duration_hours=2.0,
        load_time_hours=0.5,
        offload_time_hours=0.5,
        loading_stations=2,
        offload_stations=3,
        device_pool=20,
    )
    result = analyze(params)
    assert result.loading_stable
    assert result.offload_stable
    assert result.devices_recommended <= 20
    assert result.bottleneck in ("balanced", "devices", "loading", "offload")


def test_offload_bottleneck_when_underprovisioned():
    params = OpsParameters(
        vehicles=8,
        missions_per_vehicle_per_day=6,
        mission_duration_hours=2.0,
        load_time_hours=0.5,
        offload_time_hours=1.0,
        loading_stations=3,
        offload_stations=1,
        device_pool=50,
    )
    result = analyze(params)
    assert result.bottleneck == "offload"
    assert not result.offload_stable


def test_high_data_volume_offload_equals_mission_factor():
    params = OpsParameters(
        vehicles=8,
        missions_per_vehicle_per_day=4,
        mission_duration_hours=2.0,
        load_time_hours=0.5,
        offload_time_hours=0.5,
        loading_stations=3,
        offload_stations=1,
        device_pool=40,
        high_data_volume_mode=True,
        offload_factor=0.9,
    )
    assert params.effective_offload_hours() == 1.8
    result = analyze(params)
    assert result.bottleneck == "offload"
