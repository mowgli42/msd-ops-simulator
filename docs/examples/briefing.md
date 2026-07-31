# MSD Ops Capacity Briefing

_Generated 2026-07-31 10:15 UTC_

## Executive snapshot

- **Primary constraint:** `balanced`
- **Arrival rate:** 1.0 devices/hour
- **Loading / offload utilization:** 0.25 / 0.1667
- **Devices recommended vs pool:** 8 / 20
- **Max vehicles (stable / @85%):** 20 / 20

## Configuration

| Parameter | Value |
|-----------|-------|
| `vehicles` | 8 |
| `missions_per_vehicle_per_day` | 3.0 |
| `mission_duration_hours` | 2.0 |
| `load_time_hours` | 0.5 |
| `offload_time_hours` | 0.5 |
| `install_time_hours` | 0.0 |
| `sanitize_time_hours` | 0.0 |
| `loading_stations` | 2 |
| `offload_stations` | 3 |
| `device_pool` | 20 |
| `ports_per_vehicle` | 2 |
| `devices_per_mission` | 1 |
| `min_devices_per_vehicle` | 1 |
| `preload_all_ports` | False |
| `high_data_volume_mode` | False |
| `utilization_target` | 0.85 |

## Workflow constraints

| Resource | Utilization |
|----------|-------------|
| loading | 0.25 |
| offload | 0.1667 |
| devices | 0.1518 |
| vehicle_tempo | 0.25 |
| ports | 0.125 |

## Capacity narrative

```
MSD Ops Capacity Analysis
========================
Vehicles:              8
Missions/vehicle/day:  3.0 (max feasible ≈ 12.0)
Devices/mission:       1
Ports/vehicle:         2 (min installed 1)
Arrival rate:          1.0 devices/hour

Loading  ρ=0.25  P(wait)=0.1  stations=2 (min 1)
Offload  ρ=0.1667  P(wait)=0.0152  stations=3 (min 1)
Vehicle  ρ=0.25  Port ρ=0.125

Cycle time:            3.0364 h (+install 0.0 h, +sanitize 0.0 h)
Devices required:      3.04
Devices recommended:   8 (pool=20)
Device reuse rate:     1.0
Mission start delay:   0.0 h (approx)

Primary constraint:    balanced
Constraint ρ map:      devices=0.1518, loading=0.25, offload=0.1667, ports=0.125, vehicle_tempo=0.25

Max vehicles (stable): 20 (limit: devices)
Max vehicles (@ 85% ρ): 20 (limit: devices)
```

## Preferred scenarios (from sweep)

Explore loading/offload station counts and device pool size around the baseline fleet. Prefer stable, below-target utilization with lean capital.

Evaluated 100 combinations; 100 feasible; 20 on Pareto front.

| Rank | L | O | Pool | ρL | ρO | Wq offload | Bottleneck | Score | Pareto |
|------|---|---|------|----|----|------------|------------|-------|--------|
| 1 | 2 | 2 | 12 | 0.25 | 0.25 | 0.0333 | balanced | -3.750 | yes |
| 2 | 1 | 2 | 12 | 0.5 | 0.25 | 0.0333 | balanced | -3.942 | yes |
| 3 | 2 | 3 | 12 | 0.25 | 0.1667 | 0.003 | balanced | -4.048 | yes |
| 4 | 3 | 2 | 12 | 0.1667 | 0.25 | 0.0333 | balanced | -4.078 | yes |
| 5 | 1 | 3 | 12 | 0.5 | 0.1667 | 0.003 | balanced | -4.239 | yes |
| 6 | 2 | 2 | 16 | 0.25 | 0.25 | 0.0333 | balanced | -4.350 |  |
| 7 | 3 | 3 | 12 | 0.1667 | 0.1667 | 0.003 | balanced | -4.376 | yes |
| 8 | 2 | 1 | 12 | 0.25 | 0.5 | 0.5 | balanced | -4.408 | yes |

_Update configuration by editing the base YAML / sweep ranges and re-running `python -m analysis.generate_briefing`._

## How to refresh this briefing

```bash
python -m analysis.generate_briefing \
  --config fixtures/baseline.yaml \
  --sweep fixtures/sweep_briefing.yaml \
  -o output/briefing.html --markdown output/briefing.md
```
