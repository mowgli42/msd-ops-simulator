"""Additional bottleneck classifier regression cases."""

from analysis.capacity_model import OpsParameters, analyze


def test_loading_bottleneck_saturated():
    params = OpsParameters(
        vehicles=10,
        missions_per_vehicle_per_day=12,
        load_time_hours=1.0,
        offload_time_hours=0.5,
        loading_stations=1,
        offload_stations=5,
        device_pool=100,
    )
    result = analyze(params)
    assert result.bottleneck == "loading"
    assert not result.loading_stable


def test_devices_bottleneck_short_pool():
    params = OpsParameters(
        vehicles=12,
        missions_per_vehicle_per_day=2,
        mission_duration_hours=4.0,
        load_time_hours=0.5,
        offload_time_hours=0.5,
        loading_stations=3,
        offload_stations=3,
        device_pool=8,
    )
    result = analyze(params)
    assert result.bottleneck == "devices"


def test_balanced_baseline_fixture_rates():
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
    assert result.bottleneck == "balanced"
    assert result.loading_stable and result.offload_stable
