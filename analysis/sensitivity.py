"""Sensitivity sweep → CSV for investment trade-off tables."""

from __future__ import annotations

import csv
import io
import sys
from dataclasses import asdict
from pathlib import Path

from dataclasses import replace

from analysis.capacity_model import OpsParameters, ProcessConfig, analyze
from analysis.config_loader import load_shared_config, to_ops_parameters


def _row_from(params: OpsParameters, result) -> dict:
    return {
        "vehicles": params.vehicles,
        "missions_per_vehicle_per_day": params.missions_per_vehicle_per_day,
        "mission_duration_hours": params.mission_duration_hours,
        "load_time_hours": params.effective_load_hours(),
        "offload_time_hours": params.effective_offload_hours(),
        "high_data_volume_mode": params.high_data_volume_mode,
        "offload_factor": params.offload_factor,
        "loading_stations": params.loading_stations,
        "offload_stations": params.offload_stations,
        "device_pool": params.device_pool,
        "shared_station": params.shared_station,
        "slots_in_use": params.slots_in_use,
        "cabinet_rho": result.cabinet_rho if result.cabinet_rho is not None else "",
        "arrival_rate_per_hour": result.arrival_rate_per_hour,
        "loading_utilization": result.loading_utilization,
        "offload_utilization": result.offload_utilization,
        "devices_recommended": result.devices_recommended,
        "loading_stations_min": result.loading_stations_min,
        "offload_stations_min": result.offload_stations_min,
        "bottleneck": result.bottleneck,
        "loading_stable": result.loading_stable,
        "offload_stable": result.offload_stable,
        "compression_ratio": params.process.compression_ratio if params.process else "",
        "protocol_rate_MBps": params.process.protocol_rate_MBps if params.process else "",
    }


CSV_COLUMNS = [
    "vehicles",
    "missions_per_vehicle_per_day",
    "mission_duration_hours",
    "load_time_hours",
    "offload_time_hours",
    "high_data_volume_mode",
    "offload_factor",
    "loading_stations",
    "offload_stations",
    "device_pool",
    "shared_station",
    "slots_in_use",
    "cabinet_rho",
    "arrival_rate_per_hour",
    "loading_utilization",
    "offload_utilization",
    "devices_recommended",
    "loading_stations_min",
    "offload_stations_min",
    "bottleneck",
    "loading_stable",
    "offload_stable",
    "compression_ratio",
    "protocol_rate_MBps",
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
                    params = replace(
                        base,
                        missions_per_vehicle_per_day=missions,
                        loading_stations=loading,
                        offload_stations=offload,
                        device_pool=pool,
                    )
                    result = analyze(params)
                    rows.append(_row_from(params, result))
    return rows


def iter_process_sensitivity(base: OpsParameters) -> list[dict]:
    """Sweep compression_ratio × protocol_rate_MBps."""
    rates = [40.0, 80.0, 160.0]
    ratios = [0.0, 0.25, 0.5, 0.75]
    seed = base.process or ProcessConfig()
    rows: list[dict] = []
    for rate in rates:
        for ratio in ratios:
            params = replace(
                base,
                process=ProcessConfig(
                    bytes_per_mission_gb=seed.bytes_per_mission_gb,
                    compression_ratio=ratio,
                    protocol_rate_MBps=rate,
                    mount_overhead_hours=seed.mount_overhead_hours,
                    sanitize_hours=seed.sanitize_hours,
                    preload_gb=seed.preload_gb,
                    write_rate_MBps=seed.write_rate_MBps,
                    write_overhead_hours=seed.write_overhead_hours,
                    verify_hours=seed.verify_hours,
                ),
                high_data_volume_mode=False,
            )
            rows.append(_row_from(params, analyze(params)))
    return rows


def iter_buy_sensitivity(base: OpsParameters) -> list[dict]:
    """Sweep device_pool × slots_in_use × offload_time_hours."""
    pools = sorted({base.device_pool, base.device_pool + 2, base.device_pool + 4, max(1, base.vehicles)})
    slots = sorted({1, 2, base.slots_in_use, base.cabinet_slots})
    offloads = [
        base.offload_time_hours,
        max(0.1, base.offload_time_hours * 0.75),
        max(0.1, base.offload_time_hours * 0.5),
        base.mission_duration_hours * 0.9,
    ]
    rows: list[dict] = []
    for pool in pools:
        for slot in slots:
            for to in offloads:
                params = replace(
                    base,
                    device_pool=pool,
                    slots_in_use=slot,
                    loading_stations=slot if base.shared_station else base.loading_stations,
                    offload_stations=slot if base.shared_station else base.offload_stations,
                    offload_time_hours=to,
                    high_data_volume_mode=False,
                    process=None,
                )
                rows.append(_row_from(params, analyze(params)))
    return rows


def iter_offload_time_sensitivity(
    base: OpsParameters,
    *,
    offload_station_range: range | None = None,
    offload_pct_values: list[float] | None = None,
) -> list[dict]:
    """Sweep offload stations × offload time as % of mission duration."""
    offload_station_range = offload_station_range or range(1, 7)
    offload_pct_values = offload_pct_values or [0.5, 0.7, 0.9, 1.0, 1.2]

    rows: list[dict] = []
    for stations in offload_station_range:
        for pct in offload_pct_values:
            params = replace(
                base,
                offload_time_hours=base.mission_duration_hours * pct,
                offload_stations=stations,
                high_data_volume_mode=False,
                process=None,
            )
            result = analyze(params)
            rows.append(
                {
                    "offload_stations": stations,
                    "offload_pct_of_mission": pct,
                    "offload_time_hours": params.offload_time_hours,
                    "loading_utilization": result.loading_utilization,
                    "offload_utilization": result.offload_utilization,
                    "cabinet_rho": result.cabinet_rho if result.cabinet_rho is not None else "",
                    "bottleneck": result.bottleneck,
                    "devices_recommended": result.devices_recommended,
                    "offload_stations_min": result.offload_stations_min,
                }
            )
    return rows


def write_csv(rows: list[dict], out: io.TextIO) -> None:
    if not rows:
        return
    writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="MSD ops sensitivity sweep → CSV")
    parser.add_argument("--config", type=Path, default=Path("fixtures/baseline.yaml"))
    parser.add_argument("-o", "--output", type=Path, default=None, help="Write CSV file (default stdout)")
    parser.add_argument(
        "--mode",
        choices=("full", "stations", "missions", "offload_time", "process", "buy"),
        default="stations",
        help="full|stations|missions|offload_time|process (compression×rate)|buy (pool×slots×T_O)",
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
    elif args.mode == "offload_time":
        rows = iter_offload_time_sensitivity(base)
    elif args.mode == "process":
        rows = iter_process_sensitivity(base)
    elif args.mode == "buy":
        rows = iter_buy_sensitivity(base)
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
