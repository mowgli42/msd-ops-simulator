"""CLI: generate briefing-quality HTML / Markdown artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from analysis.config_loader import load_shared_config, to_ops_parameters
from analysis.reporting import write_briefing
from analysis.scenario_explorer import explore, load_sweep_config


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate MSD ops briefing HTML/Markdown from config (+ optional sweep)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("fixtures/baseline.yaml"),
        help="Base scenario YAML",
    )
    parser.add_argument(
        "--sweep",
        type=Path,
        default=None,
        help="Optional sweep YAML for preferred-scenario ranking",
    )
    parser.add_argument("-o", "--output", type=Path, default=Path("output/briefing.html"))
    parser.add_argument("--markdown", type=Path, default=None, help="Also write Markdown")
    parser.add_argument("--title", type=str, default="MSD Ops Capacity Briefing")
    parser.add_argument(
        "--fragment",
        action="store_true",
        help="Emit embeddable HTML fragment instead of full document",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    params = to_ops_parameters(load_shared_config(args.config))

    sweep_rows = None
    sweep_cfg = None
    if args.sweep:
        sweep_cfg = load_sweep_config(args.sweep, repo_root=root)
        # Keep base fleet from --config when exploring station/pool options
        sweep_cfg.base = params
        sweep_rows = explore(sweep_cfg)

    md_path = args.markdown
    if md_path is None and args.output.suffix.lower() in {".html", ".htm"}:
        md_path = args.output.with_suffix(".md")

    write_briefing(
        params,
        html_path=args.output,
        markdown_path=md_path,
        sweep_rows=sweep_rows,
        sweep_cfg=sweep_cfg,
        title=args.title,
        fragment=args.fragment,
    )
    print(f"Wrote {args.output}")
    if md_path:
        print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
