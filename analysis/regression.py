"""Regression harness: analysis predictions vs discrete sim steady-state."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from analysis.capacity_model import OpsParameters, analyze
from analysis.config_loader import SharedConfig, load_shared_config, to_ops_parameters
from analysis.observed import bottlenecks_align, infer_observed_bottleneck
from analysis.sim_engine import SimConfig, SimEngine


@dataclass(frozen=True)
class RegressionCase:
    name: str
    params: OpsParameters
    sim: SimConfig
    ticks_per_hour: float
    max_ticks: int = 4000


@dataclass
class RegressionOutcome:
    name: str
    predicted_bottleneck: str
    observed_bottleneck: str
    aligned: bool
    loading_queue: int
    offload_queue: int
    waiting_vehicles: int
    missions_per_hour: float
    rho_load: float
    rho_offload: float
    steady: bool


def shared_to_sim_config(cfg: SharedConfig, overrides: dict | None = None) -> SimConfig:
    overrides = overrides or {}
    return SimConfig(
        num_vehicles=int(overrides.get("vehicles", cfg.vehicles)),
        total_devices=int(overrides.get("device_pool", cfg.device_pool)),
        num_loading_stations=int(overrides.get("loading_stations", cfg.loading_stations)),
        num_offload_stations=int(overrides.get("offload_stations", cfg.offload_stations)),
        mission_duration=int(
            overrides.get("mission_duration_ticks", cfg.mission_duration_ticks)
        ),
        process_time=int(overrides.get("process_time_ticks", cfg.process_time_ticks)),
        ports_per_vehicle=int(overrides.get("ports_per_vehicle", cfg.ports_per_vehicle)),
        seed_loaded_devices=int(overrides.get("seed_loaded_devices", 5)),
        missions_per_vehicle_per_day=float(
            overrides.get("missions_per_vehicle_per_day", cfg.missions_per_vehicle_per_day)
        ),
        ticks_per_hour=float(overrides.get("ticks_per_hour", cfg.ticks_per_hour)),
        operating_hours_per_day=float(
            overrides.get("operating_hours_per_day", cfg.operating_hours_per_day)
        ),
    )


def run_case(case: RegressionCase) -> RegressionOutcome:
    predicted = analyze(case.params)
    engine = SimEngine(case.sim)
    result = engine.run_until_steady(max_ticks=case.max_ticks, ticks_per_hour=case.ticks_per_hour)
    observed = infer_observed_bottleneck(result.metrics)
    aligned = bottlenecks_align(predicted.bottleneck, observed)

    return RegressionOutcome(
        name=case.name,
        predicted_bottleneck=predicted.bottleneck,
        observed_bottleneck=observed,
        aligned=aligned,
        loading_queue=result.metrics.loading_queue,
        offload_queue=result.metrics.offload_queue,
        waiting_vehicles=result.metrics.waiting_vehicles,
        missions_per_hour=result.metrics.missions_per_hour,
        rho_load=predicted.loading_utilization,
        rho_offload=predicted.offload_utilization,
        steady=result.steady,
    )


def load_regression_cases(path: str | Path) -> list[RegressionCase]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    base_cfg = load_shared_config(data.get("base_config", "fixtures/baseline.yaml"))
    cases: list[RegressionCase] = []

    for entry in data.get("cases", []):
        name = entry["name"]
        ops_overrides = entry.get("operations", {})
        sim_overrides = entry.get("sim", {})
        timing = entry.get("timing", {})

        merged_ops = {
            "vehicles": ops_overrides.get("vehicles", base_cfg.vehicles),
            "missions_per_vehicle_per_day": ops_overrides.get(
                "missions_per_vehicle_per_day", base_cfg.missions_per_vehicle_per_day
            ),
            "device_pool": ops_overrides.get("device_pool", base_cfg.device_pool),
            "loading_stations": ops_overrides.get("loading_stations", base_cfg.loading_stations),
            "offload_stations": ops_overrides.get("offload_stations", base_cfg.offload_stations),
            "ports_per_vehicle": ops_overrides.get("ports_per_vehicle", base_cfg.ports_per_vehicle),
        }

        params = OpsParameters(
            vehicles=int(merged_ops["vehicles"]),
            missions_per_vehicle_per_day=float(merged_ops["missions_per_vehicle_per_day"]),
            mission_duration_hours=base_cfg.mission_duration_hours,
            process_time_hours=base_cfg.process_time_hours,
            ports_per_vehicle=int(merged_ops["ports_per_vehicle"]),
            loading_stations=int(merged_ops["loading_stations"]),
            offload_stations=int(merged_ops["offload_stations"]),
            device_pool=int(merged_ops["device_pool"]),
            operating_hours_per_day=base_cfg.operating_hours_per_day,
            utilization_target=base_cfg.utilization_target,
            device_buffer_fraction=base_cfg.device_buffer_fraction,
        )

        sim_cfg = shared_to_sim_config(base_cfg, {**merged_ops, **sim_overrides})
        tph = float(timing.get("ticks_per_hour", base_cfg.ticks_per_hour))

        cases.append(
            RegressionCase(
                name=name,
                params=params,
                sim=sim_cfg,
                ticks_per_hour=tph,
                max_ticks=int(entry.get("max_ticks", 4000)),
            )
        )
    return cases


def run_all(cases_path: str | Path) -> list[RegressionOutcome]:
    return [run_case(c) for c in load_regression_cases(cases_path)]


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Run analysis vs sim regression")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("fixtures/regression_scenarios.yaml"),
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    outcomes = run_all(args.cases)
    failed = [o for o in outcomes if not o.aligned]

    if args.format == "json":
        print(json.dumps([asdict(o) for o in outcomes], indent=2))
    else:
        for o in outcomes:
            status = "OK" if o.aligned else "FAIL"
            print(
                f"[{status}] {o.name}: predicted={o.predicted_bottleneck} "
                f"observed={o.observed_bottleneck} "
                f"(L={o.loading_queue} O={o.offload_queue} W={o.waiting_vehicles})"
            )
        print(f"\n{len(outcomes) - len(failed)}/{len(outcomes)} aligned")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
