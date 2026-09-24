"""Compare topologies 1-1-1 / 2-3-2 / 5-3-5 over N mission cycles."""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from pathlib import Path

from analysis.capacity_model import analyze, resolve_topology_path
from analysis.config_loader import load_shared_config, to_ops_parameters
from analysis.wait_report import (
    COLOR_ASSIGN,
    COLOR_LOAD,
    COLOR_OFFLOAD,
    run_wait_report,
)


def _collect_row(
    topology: str,
    *,
    missions: int,
    high_data: bool,
    arrival: str,
    root: Path,
) -> dict:
    path = resolve_topology_path(topology, root=root)
    cfg = load_shared_config(path)
    params = to_ops_parameters(cfg)
    if high_data:
        params = replace(params, high_data_volume_mode=True)
    if arrival:
        params = replace(params, arrival_mode=arrival)
    result = analyze(params)
    engine, wait_rows = run_wait_report(path, missions=missions, high_data_volume=high_data)
    device_rows = [r for r in wait_rows if isinstance(r["device_id"], int)]
    totals = engine.wait_totals_hours()
    mode = "high-data" if high_data else "baseline"
    if arrival == "shift":
        mode = f"{mode}+shift"
    stations = params.slots_in_use if params.shared_station else params.offload_stations
    row = {
        "topology": topology,
        "vehicles": params.vehicles,
        "stations": stations,
        "devices": params.device_pool,
        "mode": mode,
        "lambda": result.arrival_rate_per_hour,
        "rho_load": result.loading_utilization,
        "rho_offload": result.offload_utilization,
        "cabinet_rho": result.cabinet_rho if result.cabinet_rho is not None else "",
        "bottleneck": result.bottleneck,
        "devices_required": result.devices_required,
        "devices_recommended": result.devices_recommended,
        "Wq_load": result.mean_load_wait_hours,
        "Wq_offload": result.mean_offload_wait_hours,
        "T_cycle": result.cycle_time_hours,
        "missions": engine.missions_completed,
        "hours": round(engine.sim_tick / engine.config.ticks_per_hour, 4),
        "wait_load_hours_total": round(totals["wait_load_hours_total"], 4),
        "wait_assign_hours_total": round(totals["wait_assign_hours_total"], 4),
        "wait_offload_hours_total": round(totals["wait_offload_hours_total"], 4),
        "mean_wait_load": round(totals["mean_wait_load"], 4),
        "mean_wait_assign": round(totals["mean_wait_assign"], 4),
        "mean_wait_offload": round(totals["mean_wait_offload"], 4),
        "peak_load_queue": engine.peak_load_queue,
        "peak_offload_queue": engine.peak_offload_queue,
        "waiting_vehicles_max": engine.waiting_vehicles_max,
        "_device_rows": device_rows,
        "_shared": params.shared_station,
    }
    return row


def _write_csv(rows: list[dict], path: Path) -> None:
    skip = {"_device_rows", "_shared"}
    fields = [k for k in rows[0].keys() if k not in skip]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in fields})


def _plot_wait_by_stage(rows: list[dict], path: Path) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    baseline = [r for r in rows if r["mode"] == "baseline"]
    labels = [r["topology"] for r in baseline]
    x = np.arange(len(labels))
    width = 0.25
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x - width, [r["wait_load_hours_total"] for r in baseline], width, label="load-wait", color=COLOR_LOAD)
    ax.bar(x, [r["wait_assign_hours_total"] for r in baseline], width, label="assign-wait", color=COLOR_ASSIGN)
    ax.bar(x + width, [r["wait_offload_hours_total"] for r in baseline], width, label="offload-wait", color=COLOR_OFFLOAD)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    title = "Wait by stage after 100 cycles"
    if baseline and baseline[0].get("_shared"):
        title += " (S = shared cabinet slots)"
    ax.set_title(title)
    ax.set_ylabel("hours")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_per_device(rows: list[dict], path: Path) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    baseline = [r for r in rows if r["mode"] == "baseline"]
    fig, axes = plt.subplots(1, len(baseline), figsize=(4 * max(1, len(baseline)), 4), squeeze=False)
    for ax, r in zip(axes[0], baseline):
        devices = r["_device_rows"]
        ids = [str(d["device_id"]) for d in devices]
        x = np.arange(len(ids))
        width = 0.25
        ax.bar(x - width, [d["wait_load_hours"] for d in devices], width, color=COLOR_LOAD, label="load")
        ax.bar(x, [d["wait_assign_hours"] for d in devices], width, color=COLOR_ASSIGN, label="assign")
        ax.bar(x + width, [d["wait_offload_hours"] for d in devices], width, color=COLOR_OFFLOAD, label="offload")
        ax.set_xticks(x)
        ax.set_xticklabels(ids)
        ax.set_title(r["topology"])
        ax.set_xlabel("device")
    axes[0][0].legend(fontsize=7)
    fig.suptitle("Per-device wait (small multiples)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_utilization(rows: list[dict], path: Path) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    baseline = [r for r in rows if r["mode"] == "baseline"]
    labels = [r["topology"] for r in baseline]
    x = np.arange(len(labels))
    width = 0.25
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x - width, [r["rho_load"] for r in baseline], width, label="ρ_load", color=COLOR_LOAD)
    ax.bar(x, [r["rho_offload"] for r in baseline], width, label="ρ_offload", color=COLOR_OFFLOAD)
    cab = [r["cabinet_rho"] if r["cabinet_rho"] != "" else 0 for r in baseline]
    ax.bar(x + width, cab, width, label="cabinet ρ", color="#2F4F4F")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_title("Utilization comparison (analytic)")
    ax.set_ylabel("ρ")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_cycle_pool(rows: list[dict], path: Path) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    baseline = [r for r in rows if r["mode"] == "baseline"]
    labels = [r["topology"] for r in baseline]
    x = np.arange(len(labels))
    width = 0.35
    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax1.bar(x - width / 2, [r["T_cycle"] if r["T_cycle"] != float("inf") else 0 for r in baseline], width, label="T_cycle", color="#5F9EA0")
    ax1.set_ylabel("T_cycle (h)")
    ax2 = ax1.twinx()
    ax2.bar(x + width / 2, [r["devices_recommended"] for r in baseline], width, label="D_recommended", color="#8B4513", alpha=0.7)
    ax2.plot(x, [r["devices"] for r in baseline], "ko-", label="D_actual")
    ax2.set_ylabel("devices")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.set_title("Cycle time / recommended pool vs actual")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare MSD topologies over mission cycles")
    parser.add_argument("--topologies", type=str, default="1-1-1,2-3-2,5-3-5")
    parser.add_argument("--cycles", type=int, default=100)
    parser.add_argument("--outdir", type=Path, default=Path("output/compare-100"))
    parser.add_argument("--arrival", choices=("smooth", "shift"), default="smooth")
    parser.add_argument("--include-high-data", action="store_true", default=True)
    parser.add_argument("--no-high-data", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    codes = [c.strip() for c in args.topologies.split(",") if c.strip()]
    include_hd = args.include_high_data and not args.no_high_data

    rows: list[dict] = []
    for code in codes:
        rows.append(
            _collect_row(code, missions=args.cycles, high_data=False, arrival=args.arrival, root=root)
        )
        if include_hd:
            rows.append(
                _collect_row(code, missions=args.cycles, high_data=True, arrival=args.arrival, root=root)
            )

    out = args.outdir
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(rows, out / "compare.csv")
    _plot_wait_by_stage(rows, out / "wait-by-stage.png")
    _plot_per_device(rows, out / "per-device-wait.png")
    _plot_utilization(rows, out / "utilization.png")
    _plot_cycle_pool(rows, out / "cycle-time-pool.png")

    readme = out / "README.md"
    readme.write_text(
        f"""# Topology comparison ({args.cycles} cycles)

Notation: **platforms-stations-devices** (V-S-D). When `shared_station` is on,
S is usable cabinet slots.

```bash
python -m analysis.compare_topologies --topologies {args.topologies} --cycles {args.cycles} --outdir {out}
```

Artifacts: `compare.csv`, `wait-by-stage.png`, `per-device-wait.png`,
`utilization.png`, `cycle-time-pool.png`.

Colors: load=steel, assign=grey, offload=amber.
""",
        encoding="utf-8",
    )
    print(f"Wrote comparison artifacts to {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
