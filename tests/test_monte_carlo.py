"""Monte Carlo offload wait distribution."""

from analysis.capacity_model import OpsParameters
from analysis.monte_carlo import monte_carlo_offload_waits


def test_monte_carlo_produces_wait_distribution():
    params = OpsParameters(
        vehicles=8,
        missions_per_vehicle_per_day=3.0,
        offload_stations=3,
        offload_time_hours=0.5,
    )
    summary = monte_carlo_offload_waits(params, replications=50, seed=1)
    assert summary.arrivals_simulated > 0
    assert summary.p95_wait_hours >= summary.p50_wait_hours
    assert summary.mean_wait_hours >= 0


def test_monte_carlo_saturated_queue_has_high_waits():
    params = OpsParameters(
        vehicles=10,
        missions_per_vehicle_per_day=8.0,
        offload_stations=1,
        offload_time_hours=0.5,
    )
    summary = monte_carlo_offload_waits(params, replications=30, seed=2)
    assert summary.p95_wait_hours > 0.5
