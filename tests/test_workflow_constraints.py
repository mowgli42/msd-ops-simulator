"""Tests for expanded workflow constraints (#8)."""

from analysis.capacity_model import OpsParameters, analyze, replace_params


def test_vehicle_tempo_bottleneck():
    params = OpsParameters(
        vehicles=4,
        missions_per_vehicle_per_day=20.0,  # > 24/2 = 12
        mission_duration_hours=2.0,
        loading_stations=8,
        offload_stations=8,
        device_pool=100,
    )
    result = analyze(params)
    assert not result.vehicle_tempo_feasible
    assert result.bottleneck == "vehicle_tempo"
    assert result.max_missions_per_vehicle_day == 12.0


def test_ports_infeasible_when_min_devices_exceed_ports():
    params = OpsParameters(
        vehicles=4,
        min_devices_per_vehicle=3,
        ports_per_vehicle=2,
        loading_stations=4,
        offload_stations=4,
        device_pool=40,
    )
    result = analyze(params)
    assert not result.ports_feasible
    assert result.bottleneck == "ports"


def test_devices_per_mission_scales_arrival_rate():
    base = OpsParameters(vehicles=8, missions_per_vehicle_per_day=3.0, devices_per_mission=1)
    dual = replace_params(base, devices_per_mission=2)
    r1 = analyze(base)
    r2 = analyze(dual)
    assert r2.arrival_rate_per_hour == r1.arrival_rate_per_hour * 2


def test_install_and_sanitize_extend_cycle():
    base = OpsParameters()
    extended = replace_params(base, install_time_hours=0.25, sanitize_time_hours=0.25)
    r0 = analyze(base)
    r1 = analyze(extended)
    assert r1.cycle_time_hours > r0.cycle_time_hours
    assert r1.offload_utilization > r0.offload_utilization


def test_preload_raises_device_floor():
    params = OpsParameters(vehicles=8, ports_per_vehicle=2, preload_all_ports=True, device_pool=20)
    result = analyze(params)
    assert result.devices_recommended >= 16


def test_constraint_utilizations_populated():
    result = analyze(OpsParameters())
    assert set(result.constraint_utilizations) >= {
        "loading",
        "offload",
        "devices",
        "vehicle_tempo",
        "ports",
    }


def test_replace_params_rejects_unknown():
    try:
        replace_params(OpsParameters(), not_a_field=1)
        assert False, "expected TypeError"
    except TypeError:
        pass
