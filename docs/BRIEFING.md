# Briefing artifacts — MSD Ops

Generate presentation-ready HTML and Markdown from the same capacity model used by the CLI and simulator.

## One-command refresh

Edit configuration, then regenerate:

```bash
# 1) Update base scenario knobs
$EDITOR fixtures/baseline.yaml

# 2) Update which ranges to explore (any OpsParameters field)
$EDITOR fixtures/sweep_briefing.yaml

# 3) Produce briefing pack
python -m analysis.generate_briefing \
  --config fixtures/baseline.yaml \
  --sweep fixtures/sweep_briefing.yaml \
  -o docs/examples/briefing.html \
  --markdown docs/examples/briefing.md
```

Open `docs/examples/briefing.html` in a browser (Chart.js loaded from CDN).

## What you get

| Section | Content |
|---------|---------|
| Snapshot cards | Primary constraint, λ, ρL/ρO, devices, max fleet |
| Bottleneck callout | Hard vs soft constraints, reuse rate, start delay |
| Configuration table | Current YAML/CLI parameters (easy to re-brief after edits) |
| Constraint chart | Utilization bars vs 85% target |
| Preferred scenarios | Ranked + Pareto-filtered combinations from the sweep |
| Trade-off scatter | Device pool vs mean offload wait |
| Capacity narrative | Full `format_summary()` text |

Embeddable fragment (no full HTML chrome):

```bash
python -m analysis.generate_briefing --config fixtures/baseline.yaml --fragment -o output/fragment.html
```

## Updating configuration options mid-discussion

| Question | What to change |
|----------|----------------|
| More vehicles? | `operations.vehicles` in baseline YAML or `--vehicles` |
| Faster/slower offload? | `durations_hours.offload` or high-data mode |
| Station investment? | Sweep `loading_stations` / `offload_stations` ranges |
| Pool sizing? | Sweep `device_pool` values |
| Two devices per mission? | `operations.devices_per_mission` |
| Preload both USB ports? | `operations.preload_all_ports: true` |
| Install / sanitize overhead? | `durations_hours.install` / `sanitize` |

Re-run `generate_briefing` after each change. Preferred scenarios and charts update automatically.

## Scenario explorer only

```bash
python -m analysis.scenario_explorer \
  --config fixtures/sweep_briefing.yaml \
  -o output/sweep.csv --json output/sweep-summary.json
```

Methods: `grid` (full cartesian) or `lhs` (Latin Hypercube sample). Constraints and ranking weights live in the sweep YAML.

## Example pack in-repo

Committed samples (regenerate anytime):

| Artifact | Scenario |
|----------|----------|
| [docs/examples/briefing.html](examples/briefing.html) / [.md](examples/briefing.md) | Baseline (balanced) |
| [docs/examples/briefing-stress.html](examples/briefing-stress.html) / [.md](examples/briefing-stress.md) | High-tempo offload stress + preferred fixes |

Stress refresh:

```bash
python -m analysis.generate_briefing \
  --config fixtures/stress_offload.yaml \
  --sweep fixtures/sweep_stress.yaml \
  -o docs/examples/briefing-stress.html \
  --markdown docs/examples/briefing-stress.md \
  --title "MSD Ops Capacity Briefing — Offload Stress"
```
