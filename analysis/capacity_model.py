"""MSD ops capacity model — M/M/c queue sizing and bottleneck detection.

Correct, minimal queueing math for investment decisions. See docs/CAPACITY_ANALYSIS.md.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, fields, replace


@dataclass(frozen=True)
class OpsParameters:
    """Operational scenario inputs.

    Core station/pool fields are stable. Workflow fields
    (devices_per_mission, install/sanitize times, port preload) extend
    end-to-end constraint detection without changing call sites that use
    ``replace_params`` / ``asdict`` overrides.
    """

    vehicles: int = 8
    missions_per_vehicle_per_day: float = 3.0
    mission_duration_hours: float = 2.0
    load_time_hours: float = 0.5
    offload_time_hours: float = 0.5
    ports_per_vehicle: int = 2
    loading_stations: int = 2
    offload_stations: int = 3
    device_pool: int = 20
    operating_hours_per_day: float = 24.0
    utilization_target: float = 0.85
    device_buffer_fraction: float = 0.10
    high_data_volume_mode: bool = False
    offload_factor: float = 0.9
    # Full-workflow extensions
    devices_per_mission: int = 1
    min_devices_per_vehicle: int = 1
    install_time_hours: float = 0.0
    sanitize_time_hours: float = 0.0
    preload_all_ports: bool = False

    @property
    def process_time_hours(self) -> float:
        """Alias for load time (backward compatibility)."""
        return self.load_time_hours

    def effective_offload_hours(self) -> float:
        if self.high_data_volume_mode:
            return self.mission_duration_hours * self.offload_factor
        return self.offload_time_hours

    def effective_station_offload_hours(self) -> float:
        """Offload station occupancy = extract + sanitize."""
        return self.effective_offload_hours() + max(0.0, self.sanitize_time_hours)

    def max_missions_per_vehicle_day(self) -> float:
        """Physical tempo ceiling if a vehicle flew continuously."""
        if self.mission_duration_hours <= 0:
            return math.inf
        return self.operating_hours_per_day / self.mission_duration_hours

    def device_planning_floor(self) -> int:
        """Minimum pool to keep the fleet mission-capable."""
        if self.preload_all_ports:
            per_v = max(self.min_devices_per_vehicle, self.ports_per_vehicle)
        else:
            per_v = max(1, self.min_devices_per_vehicle)
        return max(1, self.vehicles * per_v)


KNOWN_PARAM_NAMES = frozenset(f.name for f in fields(OpsParameters))


def replace_params(params: OpsParameters, **overrides: object) -> OpsParameters:
    """Return a copy with overrides; unknown keys raise ``TypeError``."""
    unknown = set(overrides) - KNOWN_PARAM_NAMES
    if unknown:
        raise TypeError(f"Unknown OpsParameters fields: {sorted(unknown)}")
    return replace(params, **overrides)


def params_from_mapping(data: dict) -> OpsParameters:
    """Build OpsParameters from a flat dict (ignores unknown keys)."""
    filtered = {k: v for k, v in data.items() if k in KNOWN_PARAM_NAMES}
    return OpsParameters(**filtered)


@dataclass(frozen=True)
class MaxFleetResult:
    max_vehicles_stable: int
    max_vehicles_at_target: int
    limiting_factor_stable: str
    limiting_factor_target: str


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
    # Full-workflow metrics
    vehicle_utilization: float = 0.0
    port_utilization: float = 0.0
    max_missions_per_vehicle_day: float = 0.0
    device_reuse_rate: float = 1.0
    mission_start_delay_hours: float = 0.0
    vehicle_tempo_feasible: bool = True
    ports_feasible: bool = True
    constraint_utilizations: dict[str, float] | None = None


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


def _fleet_feasible(params: OpsParameters, vehicles: int, *, at_target: bool) -> tuple[bool, str]:
    """Return whether `vehicles` is supportable and which constraint binds next."""
    trial = replace_params(params, vehicles=vehicles)
    result = analyze(trial)
    hard = ("loading", "offload", "devices", "vehicle_tempo", "ports")
    if result.bottleneck in hard and result.bottleneck != "balanced":
        # Unstable / infeasible labels always bind
        if not result.loading_stable:
            return False, "loading"
        if not result.offload_stable:
            return False, "offload"
        if not result.vehicle_tempo_feasible:
            return False, "vehicle_tempo"
        if not result.ports_feasible:
            return False, "ports"
        if result.devices_recommended > params.device_pool:
            return False, "devices"
    if not result.loading_stable:
        return False, "loading"
    if not result.offload_stable:
        return False, "offload"
    if not result.vehicle_tempo_feasible:
        return False, "vehicle_tempo"
    if not result.ports_feasible:
        return False, "ports"
    if result.devices_recommended > params.device_pool:
        return False, "devices"
    if at_target:
        if result.loading_utilization > params.utilization_target:
            return False, "loading"
        if result.offload_utilization > params.utilization_target:
            return False, "offload"
        if result.vehicle_utilization > params.utilization_target:
            return False, "vehicle_tempo"
        if result.port_utilization > params.utilization_target:
            return False, "ports"
    return True, "balanced"


def max_sustainable_vehicles(params: OpsParameters, *, max_search: int = 512) -> MaxFleetResult:
    """Binary search for max fleet size with stable queues and pool headroom."""

    def search(at_target: bool) -> tuple[int, str]:
        lo, hi = 1, max(max_search, params.vehicles)
        best = 0
        limit = "balanced"
        while lo <= hi:
            mid = (lo + hi) // 2
            ok, factor = _fleet_feasible(params, mid, at_target=at_target)
            if ok:
                best = mid
                lo = mid + 1
            else:
                limit = factor
                hi = mid - 1
        if best > 0:
            _, limit = _fleet_feasible(params, best + 1, at_target=at_target)
        return best, limit

    stable_n, stable_lim = search(at_target=False)
    target_n, target_lim = search(at_target=True)
    return MaxFleetResult(
        max_vehicles_stable=stable_n,
        max_vehicles_at_target=target_n,
        limiting_factor_stable=stable_lim,
        limiting_factor_target=target_lim,
    )


def analyze(params: OpsParameters) -> CapacityResult:
    notes: list[str] = []

    if params.vehicles < 1:
        notes.append("vehicles must be >= 1")
    if params.missions_per_vehicle_per_day < 0:
        notes.append("missions_per_vehicle_per_day must be >= 0")
    if params.devices_per_mission < 1:
        notes.append("devices_per_mission must be >= 1")
    if params.min_devices_per_vehicle < 1:
        notes.append("min_devices_per_vehicle must be >= 1")
    if params.min_devices_per_vehicle > params.ports_per_vehicle:
        notes.append(
            f"min_devices_per_vehicle ({params.min_devices_per_vehicle}) exceeds "
            f"ports_per_vehicle ({params.ports_per_vehicle})"
        )

    # Device arrivals through load/offload stations
    mission_rate = params.vehicles * params.missions_per_vehicle_per_day / params.operating_hours_per_day
    lambda_rate = mission_rate * max(1, params.devices_per_mission)

    mu_load = 1.0 / params.load_time_hours if params.load_time_hours > 0 else math.inf
    offload_h = params.effective_station_offload_hours()
    mu_offload = 1.0 / offload_h if offload_h > 0 else math.inf

    rho_l = lambda_rate / (params.loading_stations * mu_load) if params.loading_stations > 0 else math.inf
    rho_o = lambda_rate / (params.offload_stations * mu_offload) if params.offload_stations > 0 else math.inf

    pw_l = erlang_c(lambda_rate, mu_load, params.loading_stations)
    pw_o = erlang_c(lambda_rate, mu_offload, params.offload_stations)

    wq_l = mean_wait_hours(lambda_rate, mu_load, params.loading_stations)
    wq_o = mean_wait_hours(lambda_rate, mu_offload, params.offload_stations)

    w_load = (wq_l if math.isfinite(wq_l) else math.inf) + params.load_time_hours
    w_offload = (wq_o if math.isfinite(wq_o) else math.inf) + offload_h
    install = max(0.0, params.install_time_hours)
    cycle = w_load + install + params.mission_duration_hours + w_offload

    devices_required = lambda_rate * cycle if math.isfinite(cycle) else math.inf
    device_floor = params.device_planning_floor()
    devices_rec = max(
        device_floor,
        math.ceil(devices_required * (1.0 + params.device_buffer_fraction))
        if math.isfinite(devices_required)
        else device_floor,
    )

    s_l_min = stations_required(lambda_rate, mu_load, params.utilization_target)
    s_o_min = stations_required(lambda_rate, mu_offload, params.utilization_target)

    loading_stable = rho_l < 1.0
    offload_stable = rho_o < 1.0

    # Vehicle tempo: requested missions vs continuous-flight ceiling
    max_m = params.max_missions_per_vehicle_day()
    vehicle_util = (
        params.missions_per_vehicle_per_day / max_m if math.isfinite(max_m) and max_m > 0 else math.inf
    )
    vehicle_tempo_feasible = params.missions_per_vehicle_per_day <= max_m + 1e-9

    # Port / onboard device constraint (Little's Law on mission phase)
    ports_feasible = params.min_devices_per_vehicle <= params.ports_per_vehicle
    devices_on_vehicles = mission_rate * params.mission_duration_hours * max(1, params.devices_per_mission)
    port_slots = params.vehicles * params.ports_per_vehicle
    port_util = devices_on_vehicles / port_slots if port_slots > 0 else math.inf
    if params.preload_all_ports:
        # Planning intent: fill all ports before launch → higher peak demand signal
        port_util = max(port_util, params.min_devices_per_vehicle / max(1, params.ports_per_vehicle))

    # Device reuse / feedback: fraction of recommended circulation the pool can sustain
    if math.isfinite(devices_required) and devices_required > 0:
        device_reuse = min(1.0, params.device_pool / max(devices_required, 1e-9))
    else:
        device_reuse = 0.0 if not math.isfinite(devices_required) else 1.0

    # Approximate mission-start delay when pool is short (devices stuck in cycle)
    if params.device_pool < devices_rec and lambda_rate > 0 and math.isfinite(devices_required):
        shortfall = devices_rec - params.device_pool
        mission_start_delay = shortfall / lambda_rate
    else:
        mission_start_delay = 0.0

    constraint_utils = {
        "loading": rho_l if math.isfinite(rho_l) else math.inf,
        "offload": rho_o if math.isfinite(rho_o) else math.inf,
        "devices": (devices_required / params.device_pool) if params.device_pool > 0 else math.inf,
        "vehicle_tempo": vehicle_util if math.isfinite(vehicle_util) else math.inf,
        "ports": port_util if math.isfinite(port_util) else math.inf,
    }

    bottleneck = "balanced"
    if not loading_stable:
        bottleneck = "loading"
        notes.append("loading queue unstable (rho >= 1)")
    elif not offload_stable:
        bottleneck = "offload"
        notes.append("offload queue unstable (rho >= 1)")
    elif not vehicle_tempo_feasible:
        bottleneck = "vehicle_tempo"
        notes.append(
            f"missions/vehicle/day {params.missions_per_vehicle_per_day} exceeds "
            f"tempo ceiling {max_m:.2f} (= H / T_m)"
        )
    elif not ports_feasible:
        bottleneck = "ports"
        notes.append("min devices per vehicle exceeds available ports")
    elif devices_rec > params.device_pool:
        bottleneck = "devices"
        notes.append(f"pool {params.device_pool} < recommended {devices_rec}")
    else:
        # Soft pressure: highest utilization vs target among workflow resources
        scored = {
            k: (v / params.utilization_target if params.utilization_target else v)
            for k, v in constraint_utils.items()
        }
        worst = max(scored, key=scored.get)
        if scored[worst] > 1.0:
            bottleneck = worst
            if worst == "devices":
                notes.append("device pool utilization above target")
            elif worst == "vehicle_tempo":
                notes.append("vehicle mission tempo above utilization target")
            elif worst == "ports":
                notes.append("onboard port occupancy above utilization target")

    if install > 0:
        notes.append(f"install overhead included in cycle ({install} h)")
    if params.sanitize_time_hours > 0:
        notes.append(f"sanitize added to offload station time (+{params.sanitize_time_hours} h)")
    if params.devices_per_mission > 1:
        notes.append(f"λ scaled by devices_per_mission={params.devices_per_mission}")

    def _r(x: float, n: int = 4) -> float:
        return round(x, n) if math.isfinite(x) else math.inf

    return CapacityResult(
        arrival_rate_per_hour=_r(lambda_rate),
        service_rate_per_station=_r(mu_offload),
        loading_utilization=_r(rho_l),
        offload_utilization=_r(rho_o),
        loading_wait_prob=_r(pw_l),
        offload_wait_prob=_r(pw_o),
        mean_load_wait_hours=_r(wq_l) if math.isfinite(wq_l) else math.inf,
        mean_offload_wait_hours=_r(wq_o) if math.isfinite(wq_o) else math.inf,
        cycle_time_hours=_r(cycle) if math.isfinite(cycle) else math.inf,
        devices_required=round(devices_required, 2) if math.isfinite(devices_required) else math.inf,
        devices_recommended=devices_rec,
        loading_stations_min=s_l_min,
        offload_stations_min=s_o_min,
        bottleneck=bottleneck,
        loading_stable=loading_stable,
        offload_stable=offload_stable,
        notes=notes,
        vehicle_utilization=_r(vehicle_util) if math.isfinite(vehicle_util) else math.inf,
        port_utilization=_r(port_util) if math.isfinite(port_util) else math.inf,
        max_missions_per_vehicle_day=_r(max_m, 4) if math.isfinite(max_m) else math.inf,
        device_reuse_rate=_r(device_reuse),
        mission_start_delay_hours=_r(mission_start_delay),
        vehicle_tempo_feasible=vehicle_tempo_feasible,
        ports_feasible=ports_feasible,
        constraint_utilizations={k: _r(v) if math.isfinite(v) else math.inf for k, v in constraint_utils.items()},
    )


def format_summary(params: OpsParameters, result: CapacityResult) -> str:
    fleet = max_sustainable_vehicles(params)
    cu = result.constraint_utilizations or {}
    lines = [
        "MSD Ops Capacity Analysis",
        "========================",
        f"Vehicles:              {params.vehicles}",
        f"Missions/vehicle/day:  {params.missions_per_vehicle_per_day} "
        f"(max feasible ≈ {result.max_missions_per_vehicle_day})",
        f"Devices/mission:       {params.devices_per_mission}",
        f"Ports/vehicle:         {params.ports_per_vehicle} "
        f"(min installed {params.min_devices_per_vehicle}"
        f"{'; preload all' if params.preload_all_ports else ''})",
        f"Arrival rate:          {result.arrival_rate_per_hour} devices/hour",
        "",
        f"Loading  ρ={result.loading_utilization}  P(wait)={result.loading_wait_prob}  "
        f"stations={params.loading_stations} (min {result.loading_stations_min})",
        f"Offload  ρ={result.offload_utilization}  P(wait)={result.offload_wait_prob}  "
        f"stations={params.offload_stations} (min {result.offload_stations_min})",
        f"Vehicle  ρ={result.vehicle_utilization}  Port ρ={result.port_utilization}",
        "",
        f"Cycle time:            {result.cycle_time_hours} h "
        f"(+install {params.install_time_hours} h, +sanitize {params.sanitize_time_hours} h)",
        f"Devices required:      {result.devices_required}",
        f"Devices recommended:   {result.devices_recommended} (pool={params.device_pool})",
        f"Device reuse rate:     {result.device_reuse_rate}",
        f"Mission start delay:   {result.mission_start_delay_hours} h (approx)",
        "",
        f"Primary constraint:    {result.bottleneck}",
        f"Constraint ρ map:      "
        + ", ".join(f"{k}={v}" for k, v in sorted(cu.items())),
        "",
        f"Max vehicles (stable): {fleet.max_vehicles_stable} (limit: {fleet.limiting_factor_stable})",
        f"Max vehicles (@ {params.utilization_target:.0%} ρ): {fleet.max_vehicles_at_target} "
        f"(limit: {fleet.limiting_factor_target})",
    ]
    if result.notes:
        lines.append("Notes: " + "; ".join(result.notes))
    if params.vehicles > fleet.max_vehicles_at_target:
        lines.append(
            f"Warning: {params.vehicles} vehicles exceeds safe operating point "
            f"({fleet.max_vehicles_at_target} @ {params.utilization_target:.0%} utilization)"
        )
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
    parser.add_argument("--load-hours", type=float, default=None, help="Load time (maps/threats)")
    parser.add_argument("--offload-hours", type=float, default=None, help="Offload + sanitize time")
    parser.add_argument("--process-hours", type=float, default=None, help="Alias for --load-hours")
    parser.add_argument("--install-hours", type=float, default=None)
    parser.add_argument("--sanitize-hours", type=float, default=None)
    parser.add_argument("--devices-per-mission", type=int, default=None)
    parser.add_argument("--min-devices-per-vehicle", type=int, default=None)
    parser.add_argument("--ports-per-vehicle", type=int, default=None)
    parser.add_argument("--preload-all-ports", action="store_true")
    parser.add_argument("--high-data-volume", action="store_true", help="Offload = mission × factor")
    parser.add_argument("--offload-factor", type=float, default=None)
    parser.add_argument("--loading-stations", type=int, default=None)
    parser.add_argument("--offload-stations", type=int, default=None)
    parser.add_argument("--device-pool", type=int, default=None)
    parser.add_argument("--format", choices=("text", "json", "csv"), default="text")
    parser.add_argument(
        "--monte-carlo",
        type=int,
        default=0,
        metavar="N",
        help="Run N Poisson Monte Carlo replications for offload wait distribution",
    )
    args = parser.parse_args()

    if args.config:
        from analysis.config_loader import load_shared_config, to_ops_parameters

        params = to_ops_parameters(load_shared_config(args.config))
        overrides = {
            "vehicles": args.vehicles,
            "missions_per_vehicle_per_day": args.missions_per_day,
            "mission_duration_hours": args.mission_hours,
            "load_time_hours": args.load_hours if args.load_hours is not None else args.process_hours,
            "offload_time_hours": args.offload_hours,
            "install_time_hours": args.install_hours,
            "sanitize_time_hours": args.sanitize_hours,
            "devices_per_mission": args.devices_per_mission,
            "min_devices_per_vehicle": args.min_devices_per_vehicle,
            "ports_per_vehicle": args.ports_per_vehicle,
            "loading_stations": args.loading_stations,
            "offload_stations": args.offload_stations,
            "device_pool": args.device_pool,
            "high_data_volume_mode": True if args.high_data_volume else None,
            "offload_factor": args.offload_factor,
            "preload_all_ports": True if args.preload_all_ports else None,
        }
        params = replace_params(
            params, **{k: o for k, o in overrides.items() if o is not None}
        )
    else:
        params = OpsParameters(
            vehicles=args.vehicles if args.vehicles is not None else 8,
            missions_per_vehicle_per_day=args.missions_per_day if args.missions_per_day is not None else 3.0,
            mission_duration_hours=args.mission_hours if args.mission_hours is not None else 2.0,
            load_time_hours=(
                args.load_hours
                if args.load_hours is not None
                else (args.process_hours if args.process_hours is not None else 0.5)
            ),
            offload_time_hours=args.offload_hours if args.offload_hours is not None else 0.5,
            install_time_hours=args.install_hours if args.install_hours is not None else 0.0,
            sanitize_time_hours=args.sanitize_hours if args.sanitize_hours is not None else 0.0,
            devices_per_mission=args.devices_per_mission if args.devices_per_mission is not None else 1,
            min_devices_per_vehicle=(
                args.min_devices_per_vehicle if args.min_devices_per_vehicle is not None else 1
            ),
            ports_per_vehicle=args.ports_per_vehicle if args.ports_per_vehicle is not None else 2,
            loading_stations=args.loading_stations if args.loading_stations is not None else 2,
            offload_stations=args.offload_stations if args.offload_stations is not None else 3,
            device_pool=args.device_pool if args.device_pool is not None else 20,
            high_data_volume_mode=args.high_data_volume,
            offload_factor=args.offload_factor if args.offload_factor is not None else 0.9,
            preload_all_ports=args.preload_all_ports,
        )
    result = analyze(params)

    if args.format == "json":
        payload: dict = {"parameters": asdict(params), "result": asdict(result)}
        if args.monte_carlo > 0:
            from analysis.monte_carlo import monte_carlo_offload_waits, summary_to_dict

            payload["monte_carlo"] = summary_to_dict(
                monte_carlo_offload_waits(params, replications=args.monte_carlo)
            )
        print(json.dumps(payload, indent=2))
    elif args.format == "csv":
        row = {**asdict(params), **{f"result_{k}": v for k, v in asdict(result).items() if k != "notes"}}
        # Flatten constraint map for CSV
        cu = row.pop("result_constraint_utilizations", None) or {}
        for k, v in cu.items():
            row[f"result_cu_{k}"] = v
        print(",".join(str(row[k]) for k in row))
    else:
        print(format_summary(params, result))
        if args.monte_carlo > 0:
            from analysis.monte_carlo import format_monte_carlo_summary, monte_carlo_offload_waits

            print()
            print(
                format_monte_carlo_summary(
                    monte_carlo_offload_waits(params, replications=args.monte_carlo)
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
