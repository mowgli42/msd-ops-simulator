"""MSD ops capacity model — M/M/c queue sizing and bottleneck detection.

Correct, minimal queueing math for investment decisions. See docs/CAPACITY_ANALYSIS.md.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class OpsParameters:
    vehicles: int = 8
    missions_per_vehicle_per_day: float = 3.0
    mission_duration_hours: float = 2.0
    process_time_hours: float = 0.5
    ports_per_vehicle: int = 2
    loading_stations: int = 2
    offload_stations: int = 3
    device_pool: int = 20
    operating_hours_per_day: float = 24.0
    utilization_target: float = 0.85
    device_buffer_fraction: float = 0.10


@dataclass(frozen=True)
class CapacityResult:
    arrival_rate_per_hour: float
    service_rate_per_station: float
    loading_utilization: float
    offload_utilization: float
    loading_wait_prob: float
    offload_wait_prob: float
    mean_load_wait_hours: float
    mean_offload_wait_hours: float
    cycle_time_hours: float
    devices_required: float
    devices_recommended: int
    loading_stations_min: int
    offload_stations_min: int
    bottleneck: str
    loading_stable: bool
    offload_stable: bool
    notes: list[str]


def erlang_c(lambda_rate: float, mu: float, servers: int) -> float:
    """Probability of waiting in M/M/c (Erlang C). Returns 0 if unstable."""
    if servers < 1 or lambda_rate <= 0 or mu <= 0:
        return 0.0
    rho = lambda_rate / (servers * mu)
    if rho >= 1.0:
        return 1.0

    a = lambda_rate / mu
    sum_terms = 0.0
    for n in range(servers):
        sum_terms += (a**n) / math.factorial(n)
    last = (a**servers) / (math.factorial(servers) * (1.0 - rho))
    denom = sum_terms + last
    if denom <= 0:
        return 0.0
    return last / denom


def mean_wait_hours(lambda_rate: float, mu: float, servers: int) -> float:
    """Mean queue wait W_q for M/M/c. Returns inf if saturated."""
    if servers < 1 or lambda_rate <= 0:
        return 0.0
    if lambda_rate >= servers * mu:
        return math.inf
    pw = erlang_c(lambda_rate, mu, servers)
    return pw / (servers * mu - lambda_rate)


def stations_required(lambda_rate: float, mu: float, utilization_target: float) -> int:
    if lambda_rate <= 0 or mu <= 0 or utilization_target <= 0:
        return 1
    return max(1, math.ceil(lambda_rate / (mu * utilization_target)))


def analyze(params: OpsParameters) -> CapacityResult:
    notes: list[str] = []

    if params.vehicles < 1:
        notes.append("vehicles must be >= 1")
    if params.missions_per_vehicle_per_day < 0:
        notes.append("missions_per_vehicle_per_day must be >= 0")

    lambda_rate = (
        params.vehicles * params.missions_per_vehicle_per_day / params.operating_hours_per_day
    )
    mu = 1.0 / params.process_time_hours if params.process_time_hours > 0 else math.inf

    rho_l = lambda_rate / (params.loading_stations * mu) if params.loading_stations > 0 else math.inf
    rho_o = lambda_rate / (params.offload_stations * mu) if params.offload_stations > 0 else math.inf

    pw_l = erlang_c(lambda_rate, mu, params.loading_stations)
    pw_o = erlang_c(lambda_rate, mu, params.offload_stations)

    wq_l = mean_wait_hours(lambda_rate, mu, params.loading_stations)
    wq_o = mean_wait_hours(lambda_rate, mu, params.offload_stations)

    w_load = (wq_l if math.isfinite(wq_l) else math.inf) + params.process_time_hours
    w_offload = (wq_o if math.isfinite(wq_o) else math.inf) + params.process_time_hours
    cycle = w_load + params.mission_duration_hours + w_offload

    devices_required = lambda_rate * cycle if math.isfinite(cycle) else math.inf
    device_floor = params.vehicles  # at least one device per vehicle to operate
    devices_rec = max(
        device_floor,
        math.ceil(devices_required * (1.0 + params.device_buffer_fraction))
        if math.isfinite(devices_required)
        else device_floor,
    )

    s_l_min = stations_required(lambda_rate, mu, params.utilization_target)
    s_o_min = stations_required(lambda_rate, mu, params.utilization_target)

    loading_stable = rho_l < 1.0
    offload_stable = rho_o < 1.0

    bottleneck = "balanced"
    if not loading_stable:
        bottleneck = "loading"
        notes.append("loading queue unstable (rho >= 1)")
    elif not offload_stable:
        bottleneck = "offload"
        notes.append("offload queue unstable (rho >= 1)")
    elif devices_rec > params.device_pool:
        bottleneck = "devices"
        notes.append(f"pool {params.device_pool} < recommended {devices_rec}")
    else:
        util = {
            "loading": rho_l / params.utilization_target if params.utilization_target else rho_l,
            "offload": rho_o / params.utilization_target if params.utilization_target else rho_o,
        }
        worst = max(util, key=util.get)
        if util[worst] > 1.0:
            bottleneck = worst

    return CapacityResult(
        arrival_rate_per_hour=round(lambda_rate, 4),
        service_rate_per_station=round(mu, 4),
        loading_utilization=round(rho_l, 4),
        offload_utilization=round(rho_o, 4),
        loading_wait_prob=round(pw_l, 4),
        offload_wait_prob=round(pw_o, 4),
        mean_load_wait_hours=round(wq_l, 4) if math.isfinite(wq_l) else math.inf,
        mean_offload_wait_hours=round(wq_o, 4) if math.isfinite(wq_o) else math.inf,
        cycle_time_hours=round(cycle, 4) if math.isfinite(cycle) else math.inf,
        devices_required=round(devices_required, 2) if math.isfinite(devices_required) else math.inf,
        devices_recommended=devices_rec,
        loading_stations_min=s_l_min,
        offload_stations_min=s_o_min,
        bottleneck=bottleneck,
        loading_stable=loading_stable,
        offload_stable=offload_stable,
        notes=notes,
    )


def format_summary(params: OpsParameters, result: CapacityResult) -> str:
    lines = [
        "MSD Ops Capacity Analysis",
        "========================",
        f"Vehicles:              {params.vehicles}",
        f"Missions/vehicle/day:  {params.missions_per_vehicle_per_day}",
        f"Arrival rate:          {result.arrival_rate_per_hour} devices/hour",
        "",
        f"Loading  ρ={result.loading_utilization}  P(wait)={result.loading_wait_prob}  "
        f"stations={params.loading_stations} (min {result.loading_stations_min})",
        f"Offload  ρ={result.offload_utilization}  P(wait)={result.offload_wait_prob}  "
        f"stations={params.offload_stations} (min {result.offload_stations_min})",
        "",
        f"Cycle time:            {result.cycle_time_hours} h",
        f"Devices required:      {result.devices_required}",
        f"Devices recommended:   {result.devices_recommended} (pool={params.device_pool})",
        "",
        f"Bottleneck:            {result.bottleneck}",
    ]
    if result.notes:
        lines.append("Notes: " + "; ".join(result.notes))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="MSD ops capacity sizing")
    parser.add_argument(
        "--config",
        type=str,
        default="",
        help="YAML fixture (e.g. fixtures/baseline.yaml); CLI flags override loaded values",
    )
    parser.add_argument("--vehicles", type=int, default=None)
    parser.add_argument("--missions-per-day", type=float, default=None)
    parser.add_argument("--mission-hours", type=float, default=None)
    parser.add_argument("--process-hours", type=float, default=None)
    parser.add_argument("--loading-stations", type=int, default=None)
    parser.add_argument("--offload-stations", type=int, default=None)
    parser.add_argument("--device-pool", type=int, default=None)
    parser.add_argument("--format", choices=("text", "json", "csv"), default="text")
    args = parser.parse_args()

    if args.config:
        from analysis.config_loader import load_shared_config, to_ops_parameters

        params = to_ops_parameters(load_shared_config(args.config))
        overrides = {
            "vehicles": args.vehicles,
            "missions_per_vehicle_per_day": args.missions_per_day,
            "mission_duration_hours": args.mission_hours,
            "process_time_hours": args.process_hours,
            "loading_stations": args.loading_stations,
            "offload_stations": args.offload_stations,
            "device_pool": args.device_pool,
        }
        params = OpsParameters(
            **{k: v for k, v in {**asdict(params), **{k: o for k, o in overrides.items() if o is not None}}.items()}
        )
    else:
        params = OpsParameters(
            vehicles=args.vehicles if args.vehicles is not None else 8,
            missions_per_vehicle_per_day=args.missions_per_day if args.missions_per_day is not None else 3.0,
            mission_duration_hours=args.mission_hours if args.mission_hours is not None else 2.0,
            process_time_hours=args.process_hours if args.process_hours is not None else 0.5,
            loading_stations=args.loading_stations if args.loading_stations is not None else 2,
            offload_stations=args.offload_stations if args.offload_stations is not None else 3,
            device_pool=args.device_pool if args.device_pool is not None else 20,
        )
    result = analyze(params)

    if args.format == "json":
        print(json.dumps({"parameters": asdict(params), "result": asdict(result)}, indent=2))
    elif args.format == "csv":
        row = {**asdict(params), **{f"result_{k}": v for k, v in asdict(result).items() if k != "notes"}}
        print(",".join(str(row[k]) for k in row))
    else:
        print(format_summary(params, result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
