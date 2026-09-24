"""Per-device wait accounting report — PNG + CSV over N completed missions."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from analysis.capacity_model import resolve_topology_path
from analysis.config_loader import load_shared_config, sim_config_from_shared
from analysis.sim_engine import SimEngine

# Chart colors (compare brief): load=steel, assign=grey, offload=amber
COLOR_LOAD = "#4682B4"
COLOR_ASSIGN = "#808080"
COLOR_OFFLOAD = "#FFBF00"


def run_wait_report(
    config_path: Path,
    *,
    missions: int = 100,
    high_data_volume: bool = False,
) -> tuple[SimEngine, list[dict]]:
    cfg = load_shared_config(config_path)
    sim_cfg = sim_config_from_shared(cfg)
    if high_data_volume:
        from analysis.config_loader import hours_to_ticks

        offload_h = cfg.mission_duration_hours * cfg.offload_factor
        sim_cfg.offload_time = hours_to_ticks(offload_h, cfg.ticks_per_hour)
        sim_cfg.high_data_volume_mode = False
    engine = SimEngine(sim_cfg)
    engine.run_until_missions(missions)
    tph = sim_cfg.ticks_per_hour or 1.0
    rows: list[dict] = []
    topology = cfg.topology_code or cfg.scenario_id
    for d in engine.devices:
        rows.append(
            {
                "topology": topology,
                "device_id": d.id,
                "wait_load_hours": round(d.wait_load_ticks / tph, 4),
                "wait_assign_hours": round(d.wait_assign_ticks / tph, 4),
                "wait_offload_hours": round(d.wait_offload_ticks / tph, 4),
                "service_load_hours": round(d.service_load_ticks / tph, 4),
                "service_offload_hours": round(d.service_offload_ticks / tph, 4),
                "mission_hours": round(d.mission_ticks / tph, 4),
                "missions_seen": d.missions_seen,
            }
        )
    summary = {
        "topology": topology,
        "device_id": "SUMMARY",
        "wait_load_hours": round(sum(r["wait_load_hours"] for r in rows), 4),
        "wait_assign_hours": round(sum(r["wait_assign_hours"] for r in rows), 4),
        "wait_offload_hours": round(sum(r["wait_offload_hours"] for r in rows), 4),
        "service_load_hours": round(sum(r["service_load_hours"] for r in rows), 4),
        "service_offload_hours": round(sum(r["service_offload_hours"] for r in rows), 4),
        "mission_hours": round(sum(r["mission_hours"] for r in rows), 4),
        "missions_seen": engine.missions_completed,
    }
    # Means in summary row via negative sentinel fields reused as totals; add mean note
    n = max(1, len(rows))
    summary_means = {
        **summary,
        "device_id": "MEANS",
        "wait_load_hours": round(summary["wait_load_hours"] / n, 4),
        "wait_assign_hours": round(summary["wait_assign_hours"] / n, 4),
        "wait_offload_hours": round(summary["wait_offload_hours"] / n, 4),
        "service_load_hours": round(summary["service_load_hours"] / n, 4),
        "service_offload_hours": round(summary["service_offload_hours"] / n, 4),
        "mission_hours": round(summary["mission_hours"] / n, 4),
    }
    return engine, rows + [summary, summary_means]


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "topology",
        "device_id",
        "wait_load_hours",
        "wait_assign_hours",
        "wait_offload_hours",
        "service_load_hours",
        "service_offload_hours",
        "mission_hours",
        "missions_seen",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_png(rows: list[dict], path: Path, *, title: str) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    device_rows = [r for r in rows if isinstance(r["device_id"], int)]
    if not device_rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    ids = [str(r["device_id"]) for r in device_rows]
    x = np.arange(len(ids))
    width = 0.25
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    ax = axes[0]
    ax.bar(x - width, [r["wait_load_hours"] for r in device_rows], width, label="wait-load", color=COLOR_LOAD)
    ax.bar(x, [r["wait_assign_hours"] for r in device_rows], width, label="wait-assign", color=COLOR_ASSIGN)
    ax.bar(x + width, [r["wait_offload_hours"] for r in device_rows], width, label="wait-offload", color=COLOR_OFFLOAD)
    ax.set_xticks(x)
    ax.set_xticklabels(ids)
    ax.set_xlabel("device_id")
    ax.set_ylabel("hours")
    ax.set_title("Per-device wait by stage")
    ax.legend(fontsize=8)

    ax2 = axes[1]
    totals = {
        "load": sum(r["wait_load_hours"] for r in device_rows),
        "assign": sum(r["wait_assign_hours"] for r in device_rows),
        "offload": sum(r["wait_offload_hours"] for r in device_rows),
    }
    ax2.bar(
        list(totals.keys()),
        list(totals.values()),
        color=[COLOR_LOAD, COLOR_ASSIGN, COLOR_OFFLOAD],
    )
    ax2.set_ylabel("hours")
    ax2.set_title("Where wait grows (totals)")

    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="MSD wait_report — per-device wait hours")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--topology", type=str, default="")
    parser.add_argument("--missions", type=int, default=100)
    parser.add_argument("-o", "--output", type=Path, default=Path("output/wait-report.png"))
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--format", choices=("png", "csv", "both"), default="both")
    parser.add_argument("--high-data-volume", action="store_true")
    args = parser.parse_args()

    if args.topology:
        config_path = resolve_topology_path(args.topology)
    elif args.config:
        config_path = args.config
    else:
        config_path = Path("fixtures/topologies/1-1-1.yaml")

    engine, rows = run_wait_report(
        config_path, missions=args.missions, high_data_volume=args.high_data_volume
    )
    csv_path = args.csv or args.output.with_suffix(".csv")
    if args.format in ("csv", "both"):
        write_csv(rows, csv_path)
        print(f"Wrote {csv_path} ({engine.missions_completed} missions, {engine.sim_tick} ticks)")
    if args.format in ("png", "both"):
        write_png(rows, args.output, title=f"wait_report — {config_path.name} ({args.missions} cycles)")
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
