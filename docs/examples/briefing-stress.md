# MSD Ops Capacity Briefing — Offload Stress

_Generated 2026-07-31 10:16 UTC_

## Executive snapshot

- **Primary constraint:** `offload`
- **Arrival rate:** 3.0 devices/hour
- **Loading / offload utilization:** 0.75 / 1.5
- **Devices recommended vs pool:** 12 / 24
- **Max vehicles (stable / @85%):** 7 / 6

## Configuration

| Parameter | Value |
|-----------|-------|
| `vehicles` | 12 |
| `missions_per_vehicle_per_day` | 6.0 |
| `mission_duration_hours` | 2.0 |
| `load_time_hours` | 0.5 |
| `offload_time_hours` | 1.0 |
| `install_time_hours` | 0.0 |
| `sanitize_time_hours` | 0.0 |
| `loading_stations` | 2 |
| `offload_stations` | 2 |
| `device_pool` | 24 |
| `ports_per_vehicle` | 2 |
| `devices_per_mission` | 1 |
| `min_devices_per_vehicle` | 1 |
| `preload_all_ports` | False |
| `high_data_volume_mode` | False |
| `utilization_target` | 0.85 |

## Workflow constraints

| Resource | Utilization |
|----------|-------------|
| loading | 0.75 |
| offload | 1.5 |
| devices | inf |
| vehicle_tempo | 0.5 |
| ports | 0.25 |

## Capacity narrative

```
MSD Ops Capacity Analysis
========================
Vehicles:              12
Missions/vehicle/day:  6.0 (max feasible ≈ 12.0)
Devices/mission:       1
Ports/vehicle:         2 (min installed 1)
Arrival rate:          3.0 devices/hour

Loading  ρ=0.75  P(wait)=0.6429  stations=2 (min 2)
Offload  ρ=1.5  P(wait)=1.0  stations=2 (min 4)
Vehicle  ρ=0.5  Port ρ=0.25

Cycle time:            inf h (+install 0.0 h, +sanitize 0.0 h)
Devices required:      inf
Devices recommended:   12 (pool=24)
Device reuse rate:     0.0
Mission start delay:   0.0 h (approx)

Primary constraint:    offload
Constraint ρ map:      devices=inf, loading=0.75, offload=1.5, ports=0.25, vehicle_tempo=0.5

Max vehicles (stable): 7 (limit: offload)
Max vehicles (@ 85% ρ): 6 (limit: offload)
Notes: offload queue unstable (rho >= 1)
Warning: 12 vehicles exceeds safe operating point (6 @ 85% utilization)
```

## Preferred scenarios (from sweep)

High-tempo offload stress. Prefer combinations that restore stability under 85% utilization with minimal added stations/devices.

Evaluated 80 combinations; 48 feasible; 12 on Pareto front.

| Rank | L | O | Pool | ρL | ρO | Wq offload | Bottleneck | Score | Pareto |
|------|---|---|------|----|----|------------|------------|-------|--------|
| 1 | 3 | 5 | 24 | 0.5 | 0.6 | 0.1181 | balanced | -8.245 | yes |
| 2 | 2 | 5 | 24 | 0.75 | 0.6 | 0.1181 | balanced | -8.434 | yes |
| 3 | 3 | 4 | 24 | 0.5 | 0.75 | 0.5094 | balanced | -8.503 | yes |
| 4 | 4 | 5 | 24 | 0.375 | 0.6 | 0.1181 | balanced | -8.619 | yes |
| 5 | 3 | 6 | 24 | 0.5 | 0.5 | 0.033 | balanced | -8.625 | yes |
| 6 | 2 | 4 | 24 | 0.75 | 0.75 | 0.5094 | balanced | -8.692 | yes |
| 7 | 2 | 6 | 24 | 0.75 | 0.5 | 0.033 | balanced | -8.814 | yes |
| 8 | 4 | 4 | 24 | 0.375 | 0.75 | 0.5094 | balanced | -8.876 | yes |

_Update configuration by editing the base YAML / sweep ranges and re-running `python -m analysis.generate_briefing`._

## How to refresh this briefing

```bash
python -m analysis.generate_briefing \
  --config fixtures/baseline.yaml \
  --sweep fixtures/sweep_briefing.yaml \
  -o output/briefing.html --markdown output/briefing.md
```
