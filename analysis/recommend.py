"""Score buy-devices vs use-2nd-slot vs cut-T_O packages."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import replace
from pathlib import Path

from analysis.capacity_model import OpsParameters, analyze, resolve_topology_path
from analysis.config_loader import load_shared_config, to_ops_parameters
from analysis.wait_report import COLOR_OFFLOAD


def _stable(result) -> bool:
    if result.cabinet_rho is not None:
        return bool(result.cabinet_stable and math.isfinite(result.cycle_time_hours))
    return bool(result.loading_stable and result.offload_stable and math.isfinite(result.cycle_time_hours))


def _score_package(
    name: str,
    base: OpsParameters,
    trial: OpsParameters,
    *,
    cycles: int,
    config_path: Path | None,
) -> dict:
    result = analyze(trial)
    wait_off = ""
    if config_path is not None and cycles > 0:
        try:
            # Apply trial overrides into a fresh sim via temporary params on engine path
            from analysis.config_loader import hours_to_ticks, sim_config_from_shared

            cfg = load_shared_config(config_path)
            sim_cfg = sim_config_from_shared(cfg)
            sim_cfg.total_devices = trial.device_pool
            sim_cfg.num_vehicles = trial.vehicles
            if trial.shared_station:
                sim_cfg.shared_station = True
                sim_cfg.num_loading_stations = trial.slots_in_use
                sim_cfg.num_offload_stations = trial.slots_in_use
            else:
                sim_cfg.num_loading_stations = trial.loading_stations
                sim_cfg.num_offload_stations = trial.offload_stations
            sim_cfg.load_time = hours_to_ticks(trial.effective_load_hours(), cfg.ticks_per_hour)
            sim_cfg.offload_time = hours_to_ticks(trial.effective_offload_hours(), cfg.ticks_per_hour)
            sim_cfg.high_data_volume_mode = False
            from analysis.sim_engine import SimEngine

            eng = SimEngine(sim_cfg)
            eng.run_until_missions(cycles)
            wait_off = round(eng.wait_totals_hours()["wait_offload_hours_total"], 4)
        except Exception:
            wait_off = ""

    pulse = result.shift_pulse
    stable = _stable(result)
    return {
        "package": name,
        "bottleneck_after": result.bottleneck,
        "rho_load": result.loading_utilization,
        "rho_offload": result.offload_utilization,
        "cabinet_rho": result.cabinet_rho if result.cabinet_rho is not None else "",
        "D_recommended": result.devices_recommended,
        "D_actual": trial.device_pool,
        "T_cycle": result.cycle_time_hours if stable else "unstable",
        "T_clear_shift": pulse.t_clear_hours if pulse else "",
        "W_last": pulse.w_last_hours if pulse else "",
        "wait_offload_hours_total": wait_off,
        "stable": "yes" if stable else "no",
    }


def build_packages(base: OpsParameters) -> list[tuple[str, OpsParameters]]:
    packages: list[tuple[str, OpsParameters]] = []
    packages.append(("baseline", base))

    # Buy devices
    target = max(base.device_pool, analyze(base).devices_recommended)
    if target <= base.device_pool:
        target = base.device_pool + 2
    packages.append(("buy_devices", replace(base, device_pool=target)))
    packages.append(("buy_devices_+4", replace(base, device_pool=base.device_pool + 4)))

    # Use 2nd slot / +1 station
    if base.shared_station:
        new_slots = min(base.cabinet_slots, base.slots_in_use + 1)
        packages.append(
            (
                "use_2nd_slot",
                replace(base, slots_in_use=new_slots, loading_stations=new_slots, offload_stations=new_slots),
            )
        )
    else:
        packages.append(
            (
                "plus_one_offload_station",
                replace(base, offload_stations=base.offload_stations + 1),
            )
        )

    # Cut T_O (proxy for protocol and/or compression)
    base_to = base.effective_offload_hours()
    for pct, label in ((0.75, "cut_T_O_25pct"), (0.50, "cut_T_O_50pct")):
        packages.append(
            (
                label,
                replace(
                    base,
                    offload_time_hours=base_to * pct,
                    high_data_volume_mode=False,
                    process=None,
                ),
            )
        )
    return packages


def format_table(rows: list[dict]) -> str:
    cols = [
        "package",
        "stable",
        "bottleneck_after",
        "cabinet_rho",
        "rho_load",
        "rho_offload",
        "D_actual",
        "D_recommended",
        "T_cycle",
        "W_last",
        "wait_offload_hours_total",
    ]
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    lines = ["MSD Ops Recommend", "=" * len(header), header, "-" * len(header)]
    for r in rows:
        lines.append("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Recommend buy vs slot vs cut-T_O")
    parser.add_argument("--config", type=Path, default=Path("fixtures/shared-cabinet.yaml"))
    parser.add_argument("--topology", type=str, default="")
    parser.add_argument("--cycles", type=int, default=100)
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--png", type=Path, default=None)
    parser.add_argument("--arrival", choices=("smooth", "shift"), default=None)
    args = parser.parse_args()

    config_path = resolve_topology_path(args.topology) if args.topology else args.config
    base = to_ops_parameters(load_shared_config(config_path))
    if args.arrival:
        base = replace(base, arrival_mode=args.arrival)

    rows = [
        _score_package(name, base, trial, cycles=args.cycles, config_path=config_path)
        for name, trial in build_packages(base)
    ]

    print(format_table(rows))

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"Wrote {args.csv}")

    if args.png:
        import matplotlib.pyplot as plt

        labels = [r["package"] for r in rows]
        vals = []
        for r in rows:
            v = r["wait_offload_hours_total"]
            vals.append(float(v) if v != "" else 0.0)
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.bar(labels, vals, color=COLOR_OFFLOAD)
        ax.set_ylabel("wait_offload_hours_total")
        ax.set_title("Package comparison — offload wait after cycles")
        ax.tick_params(axis="x", rotation=30)
        fig.tight_layout()
        args.png.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.png, dpi=120)
        plt.close(fig)
        print(f"Wrote {args.png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
