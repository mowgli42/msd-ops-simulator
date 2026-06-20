"""Sensitivity sweep → CSV for investment trade-off tables."""

from __future__ import annotations

import csv
import io
import sys
from dataclasses import asdict
from pathlib import Path

from analysis.capacity_model import OpsParameters, analyze
from analysis.config_loader import load_shared_config, to_ops_parameters


CSV_COLUMNS = [
    "vehicles",
    "missions_per_vehicle_per_day",
    "mission_duration_hours",
    "process_time_hours",
    "loading_stations",
    "offload_stations",
    "device_pool",
    "arrival_rate_per_hour",
    "loading_utilization",
    "offload_utilization",
    "devices_recommended",
    "loading_stations_min",
    "offload_stations_min",
    "bottleneck",
    "loading_stable",
    "offload_stable",
]


def iter_sensitivity_rows(
    base: OpsParameters,
    *,
    offload_range: range | None = None,
    loading_range: range | None = None,
    pool_range: range | None = None,
    missions_values: list[float] | None = None,
) -> list[dict]:
    offload_range = offload_range or range(1, 7)
    loading_range = loading_range or range(1, 6)
    pool_range = pool_range or range(8, 41, 4)
    missions_values = missions_values or [base.missions_per_vehicle_per_day]

    rows: list[dict] = []
    for missions in missions_values:
        for offload in offload_range:
            for loading in loading_range:
                for pool in pool_range:
                    params = OpsParameters(
                        vehicles=base.vehicles,
                        missions_per_vehicle_per_day=missions,
                        mission_duration_hours=base.mission_duration_hours,
                        process_time_hours=base.process_time_hours,
                        ports_per_vehicle=base.ports_per_vehicle,
                        loading_stations=loading,
                        offload_stations=offload,
                        device_pool=pool,
                        operating_hours_per_day=base.operating_hours_per_day,
                        utilization_target=base.utilization_target,
                        device_buffer_fraction=base.device_buffer_fraction,
                    )
                    result = analyze(params)
                    rows.append(
                        {
                            "vehicles": params.vehicles,
                            "missions_per_vehicle_per_day": params.missions_per_vehicle_per_day,
                            "mission_duration_hours": params.mission_duration_hours,
                            "process_time_hours": params.process_time_hours,
                            "loading_stations": params.loading_stations,
                            "offload_stations": params.offload_stations,
                            "device_pool": params.device_pool,
                            "arrival_rate_per_hour": result.arrival_rate_per_hour,
                            "loading_utilization": result.loading_utilization,
                            "offload_utilization": result.offload_utilization,
                            "devices_recommended": result.devices_recommended,
                            "loading_stations_min": result.loading_stations_min,
                            "offload_stations_min": result.offload_stations_min,
                            "bottleneck": result.bottleneck,
                            "loading_stable": result.loading_stable,
                            "offload_stable": result.offload_stable,
                        }
                    )
    return rows


def write_csv(rows: list[dict], out: io.TextIO) -> None:
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="MSD ops sensitivity sweep → CSV")
    parser.add_argument("--config", type=Path, default=Path("fixtures/baseline.yaml"))
    parser.add_argument("-o", "--output", type=Path, default=None, help="Write CSV file (default stdout)")
    parser.add_argument(
        "--mode",
        choices=("full", "stations", "missions"),
        default="stations",
        help="full=all combos; stations=offload×loading; missions=missions/day sweep",
    )
    args = parser.parse_args()

    base = to_ops_parameters(load_shared_config(args.config))

    if args.mode == "stations":
        rows = iter_sensitivity_rows(
            base,
            pool_range=range(base.device_pool, base.device_pool + 1),
            missions_values=[base.missions_per_vehicle_per_day],
        )
    elif args.mode == "missions":
        rows = iter_sensitivity_rows(
            base,
            offload_range=range(base.offload_stations, base.offload_stations + 1),
            loading_range=range(base.loading_stations, base.loading_stations + 1),
            pool_range=range(base.device_pool, base.device_pool + 1),
            missions_values=[1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0],
        )
    else:
        rows = iter_sensitivity_rows(base)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="") as f:
            write_csv(rows, f)
        print(f"Wrote {len(rows)} rows to {args.output}", file=sys.stderr)
    else:
        buf = io.StringIO()
        write_csv(rows, buf)
        sys.stdout.write(buf.getvalue())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
