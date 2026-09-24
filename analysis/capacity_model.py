"""MSD ops capacity model — M/M/c queue sizing and bottleneck detection.

Correct, minimal queueing math for investment decisions. See docs/CAPACITY_ANALYSIS.md.
Supports independent load/offload queues (legacy) and shared-cabinet occupancy.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class ProcessConfig:
    """Optional bytes/protocol decomposition for T_L and T_O."""

    bytes_per_mission_gb: float = 40.0
    compression_ratio: float = 0.0  # 0 = none, 0.5 = half bytes on the wire
    protocol_rate_MBps: float = 80.0
    mount_overhead_hours: float = 0.05
    sanitize_hours: float = 0.15
    preload_gb: float = 2.0
    write_rate_MBps: float = 80.0
    write_overhead_hours: float = 0.0
    verify_hours: float = 0.0


@dataclass(frozen=True)
class OpsParameters:
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
    # Shared cabinet (site default when enabled)
    shared_station: bool = False
    cabinet_slots: int = 2
    slots_in_use: int = 1
    # Optional process decomposition (None → use slider / high-data)
    process: ProcessConfig | None = None
    # Arrival mode: smooth (default) or shift (pulse windows)
    arrival_mode: str = "smooth"
    preload_window_hours: float = 2.0
    offload_window_hours: float = 2.0

    @property
    def process_time_hours(self) -> float:
        """Alias for load time (backward compatibility)."""
        return self.effective_load_hours()

    def extract_hours(self) -> float:
        """Bytes-on-wire extract time only (excludes mount/sanitize)."""
        if self.process is None:
            return 0.0
        p = self.process
        bytes_on_wire = self.process.bytes_per_mission_gb * (1.0 - p.compression_ratio)
        if p.protocol_rate_MBps <= 0:
            return math.inf
        return (bytes_on_wire * 1000.0) / p.protocol_rate_MBps / 3600.0

    def effective_load_hours(self) -> float:
        if self.process is None:
            return self.load_time_hours
        p = self.process
        if p.write_rate_MBps <= 0:
            return math.inf
        transfer = (p.preload_gb * 1000.0) / p.write_rate_MBps / 3600.0
        return p.write_overhead_hours + transfer + p.verify_hours

    def effective_offload_hours(self) -> float:
        if self.high_data_volume_mode:
            return self.mission_duration_hours * self.offload_factor
        if self.process is not None:
            p = self.process
            return p.mount_overhead_hours + self.extract_hours() + p.sanitize_hours
        return self.offload_time_hours

    def cabinet_servers(self) -> int:
        if self.shared_station:
            return max(1, self.slots_in_use)
        return 0

    def with_overrides(self, **kwargs: object) -> OpsParameters:
        return replace(self, **kwargs)


@dataclass(frozen=True)
class MaxFleetResult:
    max_vehicles_stable: int
    max_vehicles_at_target: int
    limiting_factor_stable: str
    limiting_factor_target: str


@dataclass(frozen=True)
class ShiftPulseResult:
    returns_in_window: int
    servers: int
    t_clear_hours: float
    w_last_hours: float
    lambda_window: float
    cabinet_rho_window: float
    window_hours: float


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
    cabinet_rho: float | None = None
    cabinet_stable: bool = True
    shift_pulse: ShiftPulseResult | None = None


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


def shift_pulse_metrics(
    *,
    returns: int,
    servers: int,
    offload_hours: float,
    window_hours: float,
) -> ShiftPulseResult:
    """Deterministic pulse clear time for end-of-shift offload dump."""
    c = max(1, servers)
    t_o = max(offload_hours, 0.0)
    batches = math.ceil(returns / c) if returns > 0 else 0
    t_clear = batches * t_o
    w_last = max(0.0, t_clear - t_o) if returns > 0 else 0.0
    window = max(window_hours, 1e-9)
    lambda_window = returns / window
    cabinet_rho_window = (lambda_window * t_o / c) if c > 0 else math.inf
    return ShiftPulseResult(
        returns_in_window=returns,
        servers=c,
        t_clear_hours=round(t_clear, 4),
        w_last_hours=round(w_last, 4),
        lambda_window=round(lambda_window, 4),
        cabinet_rho_window=round(cabinet_rho_window, 4),
        window_hours=window_hours,
    )


def _fleet_feasible(params: OpsParameters, vehicles: int, *, at_target: bool) -> tuple[bool, str]:
    """Return whether `vehicles` is supportable and which constraint binds next."""
    trial = replace(params, vehicles=vehicles)
    result = analyze(trial)
    if params.shared_station:
        if not result.cabinet_stable:
            return False, "shared_station"
    else:
        if not result.loading_stable:
            return False, "loading"
        if not result.offload_stable:
            return False, "offload"
    if result.devices_recommended > params.device_pool:
        return False, "devices"
    if at_target:
        if params.shared_station and result.cabinet_rho is not None:
            if result.cabinet_rho > params.utilization_target:
                return False, "shared_station"
        else:
            if result.loading_utilization > params.utilization_target:
                return False, "loading"
            if result.offload_utilization > params.utilization_target:
                return False, "offload"
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

    lambda_rate = (
        params.vehicles * params.missions_per_vehicle_per_day / params.operating_hours_per_day
    )
    load_h = params.effective_load_hours()
    offload_h = params.effective_offload_hours()
    mu_load = 1.0 / load_h if load_h > 0 else math.inf
    mu_offload = 1.0 / offload_h if offload_h > 0 else math.inf

    c_load = params.loading_stations
    c_off = params.offload_stations
    cabinet_rho: float | None = None
    cabinet_stable = True

    if params.shared_station:
        c = params.cabinet_servers()
        cabinet_rho = (
            lambda_rate * (load_h + offload_h) / c if c > 0 and math.isfinite(load_h + offload_h) else math.inf
        )
        cabinet_stable = cabinet_rho < 1.0
        notes.append(
            f"slots_available={params.cabinet_slots}, slots_in_use={params.slots_in_use}"
        )
        if params.slots_in_use < params.cabinet_slots:
            notes.append(
                f"policy uses {params.slots_in_use} of {params.cabinet_slots} physical slots"
            )
        implied = params.loading_stations + params.offload_stations
        if implied != params.cabinet_slots and (
            params.loading_stations != params.slots_in_use
            or params.offload_stations != params.slots_in_use
        ):
            notes.append(
                f"warning: YAML station counts (L={params.loading_stations}, "
                f"O={params.offload_stations}) disagree with cabinet_slots={params.cabinet_slots}"
            )
        notes.append(
            "warning: independent-queue ρ understates a shared cabinet; use cabinet_rho"
        )
        # Competing for c slots: treat load and offload as sequential on the same servers.
        # Logical per-stage ρ for reporting (not independent capacity).
        rho_l = lambda_rate * load_h / c if c > 0 else math.inf
        rho_o = lambda_rate * offload_h / c if c > 0 else math.inf
        # Wait: model combined M/M/c with service T_L+T_O for cycle contribution,
        # and stage waits proportional to stage service times when stable.
        mu_cab = 1.0 / (load_h + offload_h) if (load_h + offload_h) > 0 else math.inf
        pw_cab = erlang_c(lambda_rate, mu_cab, c)
        wq_cab = mean_wait_hours(lambda_rate, mu_cab, c)
        # Attribute shared wait to stages by service share
        total_svc = load_h + offload_h
        if total_svc > 0 and math.isfinite(wq_cab):
            wq_l = wq_cab * (load_h / total_svc)
            wq_o = wq_cab * (offload_h / total_svc)
        else:
            wq_l = wq_cab
            wq_o = wq_cab
        pw_l = pw_cab
        pw_o = pw_cab
        c_load = c
        c_off = c
        loading_stable = cabinet_stable
        offload_stable = cabinet_stable
    else:
        rho_l = lambda_rate / (c_load * mu_load) if c_load > 0 else math.inf
        rho_o = lambda_rate / (c_off * mu_offload) if c_off > 0 else math.inf
        pw_l = erlang_c(lambda_rate, mu_load, c_load)
        pw_o = erlang_c(lambda_rate, mu_offload, c_off)
        wq_l = mean_wait_hours(lambda_rate, mu_load, c_load)
        wq_o = mean_wait_hours(lambda_rate, mu_offload, c_off)
        loading_stable = rho_l < 1.0
        offload_stable = rho_o < 1.0

    w_load = (wq_l if math.isfinite(wq_l) else math.inf) + load_h
    w_offload = (wq_o if math.isfinite(wq_o) else math.inf) + offload_h
    cycle = w_load + params.mission_duration_hours + w_offload

    devices_required = lambda_rate * cycle if math.isfinite(cycle) else math.inf
    device_floor = params.vehicles
    devices_rec = max(
        device_floor,
        math.ceil(devices_required * (1.0 + params.device_buffer_fraction))
        if math.isfinite(devices_required)
        else device_floor,
    )

    s_l_min = stations_required(lambda_rate, mu_load, params.utilization_target)
    s_o_min = stations_required(lambda_rate, mu_offload, params.utilization_target)
    if params.shared_station:
        mu_cab = 1.0 / (load_h + offload_h) if (load_h + offload_h) > 0 else math.inf
        s_cab = stations_required(lambda_rate, mu_cab, params.utilization_target)
        s_l_min = s_cab
        s_o_min = s_cab

    bottleneck = "balanced"
    if params.shared_station:
        if not cabinet_stable:
            # Distinguish queue growth (ρ>=1) vs long dwell with empty second slot
            if params.slots_in_use < params.cabinet_slots and offload_h >= load_h:
                bottleneck = "offload_time"
                notes.append("cabinet saturated; idle physical slots unused — μ/offload_time problem")
            else:
                bottleneck = "shared_station"
                notes.append("shared cabinet unstable (cabinet_rho >= 1)")
        elif devices_rec > params.device_pool:
            bottleneck = "devices"
            notes.append(f"pool {params.device_pool} < recommended {devices_rec}")
        elif cabinet_rho is not None and params.utilization_target and cabinet_rho > params.utilization_target:
            if offload_h > load_h * 1.25 and params.slots_in_use < params.cabinet_slots:
                bottleneck = "offload_time"
            else:
                bottleneck = "shared_station"
        elif math.isfinite(wq_o) and math.isfinite(wq_l) and wq_o > wq_l * 2 and wq_o > 0.05:
            bottleneck = "offload"
            notes.append("offload wait dominates on shared cabinet")
    else:
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

    pulse: ShiftPulseResult | None = None
    if params.arrival_mode == "shift":
        servers = params.cabinet_servers() if params.shared_station else params.offload_stations
        # ≈ one MSD per platform returning in the window
        returns = params.vehicles * max(1, params.ports_per_vehicle) if params.ports_per_vehicle == 1 else params.vehicles
        returns = params.vehicles  # 1 MSD per platform in site model
        pulse = shift_pulse_metrics(
            returns=returns,
            servers=servers,
            offload_hours=offload_h,
            window_hours=params.offload_window_hours,
        )
        notes.append(
            f"shift pulse: T_clear={pulse.t_clear_hours}h W_last={pulse.w_last_hours}h "
            f"λ_window={pulse.lambda_window}/h cabinet_rho_window={pulse.cabinet_rho_window}"
        )

    return CapacityResult(
        arrival_rate_per_hour=round(lambda_rate, 4),
        service_rate_per_station=round(mu_offload, 4),
        loading_utilization=round(rho_l, 4) if math.isfinite(rho_l) else math.inf,
        offload_utilization=round(rho_o, 4) if math.isfinite(rho_o) else math.inf,
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
        cabinet_rho=round(cabinet_rho, 4) if cabinet_rho is not None and math.isfinite(cabinet_rho) else cabinet_rho,
        cabinet_stable=cabinet_stable,
        shift_pulse=pulse,
    )


def format_summary(params: OpsParameters, result: CapacityResult) -> str:
    fleet = max_sustainable_vehicles(params)
    lines = [
        "MSD Ops Capacity Analysis",
        "========================",
        f"Vehicles:              {params.vehicles}",
        f"Missions/vehicle/day:  {params.missions_per_vehicle_per_day}",
        f"Arrival rate:          {result.arrival_rate_per_hour} devices/hour",
        f"Arrival mode:          {params.arrival_mode}",
        "",
    ]
    if params.shared_station:
        lines.extend(
            [
                f"Shared cabinet:        slots_available={params.cabinet_slots}, "
                f"slots_in_use={params.slots_in_use}",
                f"Cabinet ρ:             {result.cabinet_rho}",
                f"Stage share ρ_L/ρ_O:   {result.loading_utilization} / {result.offload_utilization}",
                f"T_L / T_O:             {params.effective_load_hours():.4f} h / "
                f"{params.effective_offload_hours():.4f} h",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"Loading  ρ={result.loading_utilization}  P(wait)={result.loading_wait_prob}  "
                f"stations={params.loading_stations} (min {result.loading_stations_min})",
                f"Offload  ρ={result.offload_utilization}  P(wait)={result.offload_wait_prob}  "
                f"stations={params.offload_stations} (min {result.offload_stations_min})",
                "",
            ]
        )
    lines.extend(
        [
            f"Cycle time:            {result.cycle_time_hours} h",
            f"Devices required:      {result.devices_required}",
            f"Devices recommended:   {result.devices_recommended} (pool={params.device_pool})",
            "",
            f"Bottleneck:            {result.bottleneck}",
            "",
            f"Max vehicles (stable): {fleet.max_vehicles_stable} (limit: {fleet.limiting_factor_stable})",
            f"Max vehicles (@ {params.utilization_target:.0%} ρ): {fleet.max_vehicles_at_target} "
            f"(limit: {fleet.limiting_factor_target})",
        ]
    )
    if result.shift_pulse:
        p = result.shift_pulse
        lines.extend(
            [
                "",
                "Shift pulse (offload window)",
                f"  N returns:           {p.returns_in_window}",
                f"  T_clear:             {p.t_clear_hours} h",
                f"  W_last:              {p.w_last_hours} h",
                f"  λ_window:            {p.lambda_window} /h",
                f"  cabinet ρ (window):  {p.cabinet_rho_window}",
            ]
        )
    if result.notes:
        lines.append("Notes: " + "; ".join(result.notes))
    if params.vehicles > fleet.max_vehicles_at_target:
        lines.append(
            f"Warning: {params.vehicles} vehicles exceeds safe operating point "
            f"({fleet.max_vehicles_at_target} @ {params.utilization_target:.0%} utilization)"
        )
    return "\n".join(lines)


def _result_to_dict(result: CapacityResult) -> dict:
    d = asdict(result)
    return d


def resolve_topology_path(topology: str, *, root: Path | None = None) -> Path:
    root = root or Path.cwd()
    code = topology.strip()
    candidate = root / "fixtures" / "topologies" / f"{code}.yaml"
    if not candidate.exists():
        raise FileNotFoundError(f"Unknown topology '{code}': expected {candidate}")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="MSD ops capacity sizing")
    parser.add_argument(
        "--config",
        type=str,
        default="",
        help="YAML fixture (e.g. fixtures/baseline.yaml); CLI flags override loaded values",
    )
    parser.add_argument(
        "--topology",
        type=str,
        default="",
        help="Topology code V-S-D (e.g. 1-1-1) → fixtures/topologies/<code>.yaml",
    )
    parser.add_argument("--vehicles", type=int, default=None)
    parser.add_argument("--missions-per-day", type=float, default=None)
    parser.add_argument("--mission-hours", type=float, default=None)
    parser.add_argument("--load-hours", type=float, default=None, help="Load time (maps/threats)")
    parser.add_argument("--offload-hours", type=float, default=None, help="Offload + sanitize time")
    parser.add_argument("--process-hours", type=float, default=None, help="Alias for --load-hours")
    parser.add_argument("--high-data-volume", action="store_true", help="Offload = mission × factor")
    parser.add_argument("--offload-factor", type=float, default=None)
    parser.add_argument("--loading-stations", type=int, default=None)
    parser.add_argument("--offload-stations", type=int, default=None)
    parser.add_argument("--device-pool", type=int, default=None)
    parser.add_argument("--shared-station", action="store_true", default=None)
    parser.add_argument("--slots-in-use", type=int, default=None)
    parser.add_argument("--cabinet-slots", type=int, default=None)
    parser.add_argument(
        "--arrival",
        choices=("smooth", "shift"),
        default=None,
        help="Arrival mode (default from YAML or smooth)",
    )
    parser.add_argument("--window-hours", type=float, default=None, help="Shift offload window hours")
    parser.add_argument("--format", choices=("text", "json", "csv"), default="text")
    parser.add_argument(
        "--monte-carlo",
        type=int,
        default=0,
        metavar="N",
        help="Run N Poisson Monte Carlo replications for offload wait distribution",
    )
    args = parser.parse_args()

    config_path = args.config
    if args.topology:
        config_path = str(resolve_topology_path(args.topology))

    if config_path:
        from analysis.config_loader import load_shared_config, to_ops_parameters

        params = to_ops_parameters(load_shared_config(config_path))
        overrides = {
            "vehicles": args.vehicles,
            "missions_per_vehicle_per_day": args.missions_per_day,
            "mission_duration_hours": args.mission_hours,
            "load_time_hours": args.load_hours if args.load_hours is not None else args.process_hours,
            "offload_time_hours": args.offload_hours,
            "loading_stations": args.loading_stations,
            "offload_stations": args.offload_stations,
            "device_pool": args.device_pool,
            "high_data_volume_mode": True if args.high_data_volume else None,
            "offload_factor": args.offload_factor,
            "shared_station": True if args.shared_station else None,
            "slots_in_use": args.slots_in_use,
            "cabinet_slots": args.cabinet_slots,
            "arrival_mode": args.arrival,
            "offload_window_hours": args.window_hours,
            "preload_window_hours": args.window_hours,
        }
        clean = {k: v for k, v in overrides.items() if v is not None}
        params = replace(params, **clean)
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
            loading_stations=args.loading_stations if args.loading_stations is not None else 2,
            offload_stations=args.offload_stations if args.offload_stations is not None else 3,
            device_pool=args.device_pool if args.device_pool is not None else 20,
            high_data_volume_mode=args.high_data_volume,
            offload_factor=args.offload_factor if args.offload_factor is not None else 0.9,
            shared_station=bool(args.shared_station),
            slots_in_use=args.slots_in_use if args.slots_in_use is not None else 1,
            cabinet_slots=args.cabinet_slots if args.cabinet_slots is not None else 2,
            arrival_mode=args.arrival or "smooth",
            offload_window_hours=args.window_hours if args.window_hours is not None else 2.0,
            preload_window_hours=args.window_hours if args.window_hours is not None else 2.0,
        )
    result = analyze(params)

    if args.format == "json":
        payload: dict = {"parameters": asdict(params), "result": _result_to_dict(result)}
        if args.monte_carlo > 0:
            from analysis.monte_carlo import monte_carlo_offload_waits, summary_to_dict

            payload["monte_carlo"] = summary_to_dict(
                monte_carlo_offload_waits(params, replications=args.monte_carlo)
            )
        print(json.dumps(payload, indent=2))
    elif args.format == "csv":
        row = {**asdict(params), **{f"result_{k}": v for k, v in asdict(result).items() if k not in ("notes", "shift_pulse")}}
        # Flatten nested process
        flat = {}
        for k, v in row.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    flat[f"{k}_{sk}"] = sv
            else:
                flat[k] = v
        print(",".join(str(flat[k]) for k in flat))
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
