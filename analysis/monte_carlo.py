"""Optional Poisson Monte Carlo validation for offload queue waits."""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass

from analysis.capacity_model import OpsParameters, analyze


@dataclass(frozen=True)
class MonteCarloSummary:
    replications: int
    horizon_hours: float
    arrivals_simulated: int
    mean_wait_hours: float
    p50_wait_hours: float
    p95_wait_hours: float
    max_wait_hours: float
    saturated_arrivals: int
    deterministic_mean_wait_hours: float


def _simulate_mmc_waits(
    lambda_rate: float,
    mu: float,
    servers: int,
    horizon_hours: float,
    rng: random.Random,
) -> list[float]:
    """Single replication of M/M/c with Poisson arrivals over a fixed horizon."""
    if servers < 1 or lambda_rate <= 0 or mu <= 0:
        return []

    busy_until = [0.0] * servers
    waits: list[float] = []
    t = 0.0

    while t < horizon_hours:
        t += rng.expovariate(lambda_rate)
        if t >= horizon_hours:
            break
        idx = min(range(servers), key=busy_until.__getitem__)
        start = max(t, busy_until[idx])
        waits.append(start - t)
        busy_until[idx] = start + rng.expovariate(mu)

    return waits


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * p
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return sorted_values[low]
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def monte_carlo_offload_waits(
    params: OpsParameters,
    *,
    replications: int = 500,
    horizon_hours: float | None = None,
    seed: int = 42,
) -> MonteCarloSummary:
    """Sample offload queue waits under Poisson arrivals."""
    if replications < 1:
        raise ValueError("replications must be >= 1")

    horizon = horizon_hours if horizon_hours is not None else params.operating_hours_per_day
    lambda_rate = params.vehicles * params.missions_per_vehicle_per_day / params.operating_hours_per_day
    offload_h = params.effective_offload_hours()
    mu = 1.0 / offload_h if offload_h > 0 else math.inf
    deterministic = analyze(params)

    rng = random.Random(seed)
    pooled: list[float] = []
    saturated = 0

    for _ in range(replications):
        waits = _simulate_mmc_waits(lambda_rate, mu, params.offload_stations, horizon, rng)
        pooled.extend(waits)
        if lambda_rate >= params.offload_stations * mu:
            saturated += len(waits)

    pooled.sort()
    mean_wait = sum(pooled) / len(pooled) if pooled else 0.0

    return MonteCarloSummary(
        replications=replications,
        horizon_hours=horizon,
        arrivals_simulated=len(pooled),
        mean_wait_hours=round(mean_wait, 4),
        p50_wait_hours=round(_percentile(pooled, 0.50), 4),
        p95_wait_hours=round(_percentile(pooled, 0.95), 4),
        max_wait_hours=round(pooled[-1], 4) if pooled else 0.0,
        saturated_arrivals=saturated,
        deterministic_mean_wait_hours=deterministic.mean_offload_wait_hours,
    )


def format_monte_carlo_summary(summary: MonteCarloSummary) -> str:
    return "\n".join(
        [
            "Monte Carlo offload wait (Poisson arrivals)",
            "============================================",
            f"Replications:          {summary.replications}",
            f"Horizon:               {summary.horizon_hours} h",
            f"Arrivals simulated:    {summary.arrivals_simulated}",
            f"Mean wait:             {summary.mean_wait_hours} h",
            f"P50 wait:              {summary.p50_wait_hours} h",
            f"P95 wait:              {summary.p95_wait_hours} h",
            f"Max wait:              {summary.max_wait_hours} h",
            f"M/M/c deterministic:   {summary.deterministic_mean_wait_hours} h",
        ]
    )


def summary_to_dict(summary: MonteCarloSummary) -> dict:
    return asdict(summary)
