"""Max sustainable fleet size."""

from analysis.capacity_model import OpsParameters, max_sustainable_vehicles


def test_baseline_has_positive_max_fleet():
    params = OpsParameters(
        vehicles=8,
        missions_per_vehicle_per_day=3.0,
        loading_stations=2,
        offload_stations=3,
        device_pool=20,
    )
    fleet = max_sustainable_vehicles(params)
    assert fleet.max_vehicles_stable >= 8
    assert fleet.max_vehicles_at_target >= 1
    assert fleet.max_vehicles_at_target <= fleet.max_vehicles_stable


def test_saturated_offload_limits_fleet():
    params = OpsParameters(
        vehicles=10,
        missions_per_vehicle_per_day=8.0,
        loading_stations=2,
        offload_stations=1,
        device_pool=50,
    )
    fleet = max_sustainable_vehicles(params)
    assert fleet.max_vehicles_stable < 10
    assert fleet.limiting_factor_stable in ("loading", "offload", "devices")


def test_small_pool_limits_fleet():
    params = OpsParameters(
        vehicles=12,
        missions_per_vehicle_per_day=3.0,
        loading_stations=2,
        offload_stations=3,
        device_pool=10,
    )
    fleet = max_sustainable_vehicles(params)
    assert fleet.max_vehicles_at_target < 12
    assert fleet.limiting_factor_target == "devices"
