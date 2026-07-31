"""Multi-parameter scenario explorer with preferred-combination ranking.

Supports declarative sweep YAML (see fixtures/sweep_briefing.yaml):
grid search or Latin Hypercube sampling over any OpsParameters field.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import random
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from analysis.capacity_model import (
    KNOWN_PARAM_NAMES,
    CapacityResult,
    OpsParameters,
    analyze,
    replace_params,
)
from analysis.config_loader import load_shared_config, to_ops_parameters


RESULT_METRIC_KEYS = frozenset(
    {
        "arrival_rate_per_hour",
        "loading_utilization",
        "offload_utilization",
        "loading_wait_prob",
        "offload_wait_prob",
        "mean_load_wait_hours",
        "mean_offload_wait_hours",
        "cycle_time_hours",
        "devices_required",
        "devices_recommended",
        "loading_stations_min",
        "offload_stations_min",
        "bottleneck",
        "loading_stable",
        "offload_stable",
        "vehicle_utilization",
        "port_utilization",
        "max_missions_per_vehicle_day",
        "device_reuse_rate",
        "mission_start_delay_hours",
        "vehicle_tempo_feasible",
        "ports_feasible",
    }
)


@dataclass(frozen=True)
class ParameterRange:
    name: str
    values: tuple[float | int | bool, ...]

    @staticmethod
    def from_spec(name: str, spec: Any) -> ParameterRange:
        if name not in KNOWN_PARAM_NAMES:
            raise ValueError(f"Unknown parameter '{name}' (not in OpsParameters)")
        if isinstance(spec, dict):
            if "values" in spec:
                values = tuple(spec["values"])
            elif "min" in spec and "max" in spec:
                step = float(spec.get("step", 1))
                lo = float(spec["min"])
                hi = float(spec["max"])
                if step <= 0:
                    raise ValueError(f"step must be > 0 for {name}")
                vals: list[float | int] = []
                x = lo
                # Inclusive upper bound with float-safe loop
                while x <= hi + step * 1e-9:
                    vals.append(int(round(x)) if float(x).is_integer() else round(x, 6))
                    x += step
                values = tuple(vals)
            else:
                raise ValueError(f"Range for {name} needs 'values' or 'min'/'max'")
        elif isinstance(spec, (list, tuple)):
            values = tuple(spec)
        else:
            values = (spec,)
        if not values:
            raise ValueError(f"Empty range for {name}")
        return ParameterRange(name=name, values=values)


@dataclass
class SweepConfig:
    scenario_id: str
    description: str
    base: OpsParameters
    ranges: list[ParameterRange]
    method: str = "grid"
    constraints: dict[str, Any] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    pareto_objectives: list[str] = field(default_factory=list)
    top_n: int = 10
    lhs_samples: int = 64
    seed: int = 42


@dataclass
class ScenarioRow:
    params: OpsParameters
    result: CapacityResult
    score: float
    feasible: bool
    pareto: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {**asdict(self.params)}
        for k in RESULT_METRIC_KEYS:
            d[k] = getattr(self.result, k)
        d["score"] = self.score
        d["feasible"] = self.feasible
        d["pareto"] = self.pareto
        return d


def load_sweep_config(path: str | Path, *, repo_root: Path | None = None) -> SweepConfig:
    root = repo_root or Path.cwd()
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    base_path = data.get("base_config") or data.get("base")
    if base_path:
        bp = Path(base_path)
        if not bp.is_absolute():
            # Resolve relative to sweep file, then repo root
            candidates = [Path(path).resolve().parent / bp, root / bp]
            for c in candidates:
                if c.exists():
                    bp = c
                    break
        base = to_ops_parameters(load_shared_config(bp))
    else:
        base = OpsParameters()
        if isinstance(data.get("base_parameters"), dict):
            base = replace_params(base, **{k: v for k, v in data["base_parameters"].items() if k in KNOWN_PARAM_NAMES})

    params_spec = data.get("parameters") or {}
    ranges = [ParameterRange.from_spec(name, spec) for name, spec in params_spec.items()]
    ranking = data.get("ranking") or {}
    return SweepConfig(
        scenario_id=str(data.get("scenario_id", Path(path).stem)),
        description=str(data.get("description", "")).strip(),
        base=base,
        ranges=ranges,
        method=str(data.get("method", "grid")).lower(),
        constraints=dict(data.get("constraints") or {}),
        weights={str(k): float(v) for k, v in (ranking.get("weights") or {}).items()},
        pareto_objectives=[str(x) for x in (ranking.get("pareto_objectives") or [])],
        top_n=int(ranking.get("top_n", data.get("top_n", 10))),
        lhs_samples=int(data.get("lhs_samples", 64)),
        seed=int(data.get("seed", 42)),
    )


def _latin_hypercube_indices(n_samples: int, dim_sizes: list[int], rng: random.Random) -> list[tuple[int, ...]]:
    """Simple LHS over discrete axes: one stratified sample index per dimension."""
    if n_samples < 1 or not dim_sizes:
        return []
    cols: list[list[int]] = []
    for size in dim_sizes:
        # Stratify [0,1) into n_samples bins, map to discrete index
        picks = []
        for i in range(n_samples):
            u = (i + rng.random()) / n_samples
            picks.append(min(size - 1, int(u * size)))
        rng.shuffle(picks)
        cols.append(picks)
    return [tuple(cols[d][i] for d in range(len(dim_sizes))) for i in range(n_samples)]


def iter_combinations(cfg: SweepConfig) -> Iterable[OpsParameters]:
    if not cfg.ranges:
        yield cfg.base
        return

    if cfg.method == "lhs":
        rng = random.Random(cfg.seed)
        sizes = [len(r.values) for r in cfg.ranges]
        full = 1
        for s in sizes:
            full *= s
        n = min(cfg.lhs_samples, full)
        for idxs in _latin_hypercube_indices(n, sizes, rng):
            overrides = {cfg.ranges[i].name: cfg.ranges[i].values[idxs[i]] for i in range(len(cfg.ranges))}
            yield replace_params(cfg.base, **overrides)
        return

    # Default: full grid
    axes = [r.values for r in cfg.ranges]
    names = [r.name for r in cfg.ranges]
    for combo in itertools.product(*axes):
        overrides = dict(zip(names, combo))
        yield replace_params(cfg.base, **overrides)


def _metric_value(params: OpsParameters, result: CapacityResult, key: str) -> float | str | bool:
    if hasattr(result, key):
        return getattr(result, key)
    if hasattr(params, key):
        return getattr(params, key)
    raise KeyError(f"Unknown metric/parameter '{key}'")


def passes_constraints(params: OpsParameters, result: CapacityResult, constraints: dict[str, Any]) -> bool:
    for key, rule in constraints.items():
        val = _metric_value(params, result, key)
        if isinstance(rule, bool):
            if bool(val) != rule:
                return False
        elif isinstance(rule, dict):
            if "eq" in rule and val != rule["eq"]:
                return False
            if "ne" in rule and val == rule["ne"]:
                return False
            if "in" in rule and val not in rule["in"]:
                return False
            if "not_in" in rule and val in rule["not_in"]:
                return False
            num = float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else None
            if num is not None:
                if "max" in rule and not (num <= float(rule["max"]) + 1e-12):
                    return False
                if "min" in rule and not (num >= float(rule["min"]) - 1e-12):
                    return False
                if not math.isfinite(num) and rule.get("finite", False):
                    return False
        else:
            if val != rule:
                return False
    return True


def score_scenario(
    params: OpsParameters,
    result: CapacityResult,
    weights: dict[str, float],
) -> float:
    if not weights:
        # Default: prefer low waits and lean capital
        weights = {
            "mean_offload_wait_hours": -2.0,
            "mean_load_wait_hours": -1.0,
            "device_pool": -0.1,
            "loading_stations": -0.3,
            "offload_stations": -0.3,
        }
    total = 0.0
    for key, w in weights.items():
        val = _metric_value(params, result, key)
        if isinstance(val, bool):
            num = 1.0 if val else 0.0
        elif isinstance(val, (int, float)):
            num = float(val)
            if not math.isfinite(num):
                num = 1e6
        else:
            continue
        total += w * num
    return total


def _dominates(a: dict[str, float], b: dict[str, float], objectives: list[str]) -> bool:
    """True if a Pareto-dominates b for minimize-all objectives."""
    better_or_eq = True
    strictly_better = False
    for obj in objectives:
        if a[obj] > b[obj] + 1e-12:
            better_or_eq = False
            break
        if a[obj] < b[obj] - 1e-12:
            strictly_better = True
    return better_or_eq and strictly_better


def mark_pareto_front(rows: list[ScenarioRow], objectives: list[str]) -> None:
    if not objectives or not rows:
        return
    vectors = []
    for row in rows:
        vec = {}
        for obj in objectives:
            val = _metric_value(row.params, row.result, obj)
            num = float(val) if isinstance(val, (int, float)) else 0.0
            if not math.isfinite(num):
                num = 1e9
            vec[obj] = num
        vectors.append(vec)
    for i, row in enumerate(rows):
        dominated = False
        for j, other in enumerate(rows):
            if i == j or not other.feasible:
                continue
            if _dominates(vectors[j], vectors[i], objectives):
                dominated = True
                break
        row.pareto = row.feasible and not dominated


def explore(cfg: SweepConfig) -> list[ScenarioRow]:
    rows: list[ScenarioRow] = []
    for params in iter_combinations(cfg):
        result = analyze(params)
        feasible = passes_constraints(params, result, cfg.constraints)
        score = score_scenario(params, result, cfg.weights)
        # Penalize infeasible so they sort last when ranking
        if not feasible:
            score -= 1e9
        rows.append(ScenarioRow(params=params, result=result, score=score, feasible=feasible))
    mark_pareto_front(rows, cfg.pareto_objectives)
    rows.sort(key=lambda r: (-r.feasible, -r.score, r.params.device_pool, r.params.offload_stations))
    return rows


def preferred_summary(rows: list[ScenarioRow], *, top_n: int = 8) -> str:
    feasible = [r for r in rows if r.feasible]
    pareto = [r for r in feasible if r.pareto]
    lines = [
        "Scenario explorer — preferred combinations",
        "==========================================",
        f"Evaluated: {len(rows)}  Feasible: {len(feasible)}  Pareto: {len(pareto)}",
        "",
    ]
    if not feasible:
        lines.append("No combinations satisfied constraints.")
        if rows:
            best = rows[0]
            lines.append(
                f"Closest (infeasible): stations L={best.params.loading_stations}/"
                f"O={best.params.offload_stations} pool={best.params.device_pool} "
                f"bottleneck={best.result.bottleneck} score={best.score:.3f}"
            )
        return "\n".join(lines)

    lines.append(f"Top {min(top_n, len(feasible))} by weighted score:")
    for i, row in enumerate(feasible[:top_n], 1):
        p, r = row.params, row.result
        tag = " [Pareto]" if row.pareto else ""
        lines.append(
            f"{i:2d}. L={p.loading_stations} O={p.offload_stations} D={p.device_pool} "
            f"ρL={r.loading_utilization:.3f} ρO={r.offload_utilization:.3f} "
            f"WqO={r.mean_offload_wait_hours} bottleneck={r.bottleneck} "
            f"score={row.score:.3f}{tag}"
        )
    return "\n".join(lines)


def write_csv(rows: list[ScenarioRow], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    dicts = [r.to_dict() for r in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(dicts[0].keys()))
        writer.writeheader()
        writer.writerows(dicts)


def main() -> int:
    parser = argparse.ArgumentParser(description="MSD multi-parameter scenario explorer")
    parser.add_argument("--config", type=Path, required=True, help="Sweep YAML (ranges + ranking)")
    parser.add_argument("--base", type=Path, default=None, help="Override base scenario YAML")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Write full CSV")
    parser.add_argument("--json", type=Path, default=None, help="Write JSON summary")
    parser.add_argument("--top", type=int, default=None, help="Override top_n for summary")
    parser.add_argument("--method", choices=("grid", "lhs"), default=None)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    cfg = load_sweep_config(args.config, repo_root=root)
    if args.base:
        cfg.base = to_ops_parameters(load_shared_config(args.base))
    if args.method:
        cfg.method = args.method
    if args.top is not None:
        cfg.top_n = args.top

    rows = explore(cfg)
    print(preferred_summary(rows, top_n=cfg.top_n))
    if cfg.description:
        print()
        print(cfg.description)

    if args.output:
        write_csv(rows, args.output)
        print(f"\nWrote {len(rows)} rows to {args.output}", file=sys.stderr)

    if args.json:
        payload = {
            "scenario_id": cfg.scenario_id,
            "description": cfg.description,
            "method": cfg.method,
            "evaluated": len(rows),
            "feasible": sum(1 for r in rows if r.feasible),
            "pareto": sum(1 for r in rows if r.pareto),
            "top": [r.to_dict() for r in rows if r.feasible][: cfg.top_n],
            "pareto_set": [r.to_dict() for r in rows if r.pareto],
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote JSON summary to {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
