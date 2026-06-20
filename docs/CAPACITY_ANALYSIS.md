# Capacity Analysis — MSD Device & Station Sizing

This document defines the **queueing model** behind `analysis/capacity_model.py`. The goal is investment-grade **directional correctness**, not a flashy dashboard.

## Problem statement

Each **Mission Storage Device (MSD)** cycles through:

1. **Load** — maps, threats, procedures written at a loading station  
2. **Mission** — installed in a vehicle (max 2 ports per vehicle via USB hub)  
3. **Offload** — data extracted and device sanitized at an offload station  
4. **Ready** — returns to the pool

Given:

- `V` — number of vehicles  
- `M` — missions per vehicle per day  
- `T_m` — mission duration (hours)  
- `T_L` — load time (maps/threats, hours)  
- `T_O` — offload + sanitize time (hours)  
- `P` — ports per vehicle (default 2)  
- `S_L`, `S_O` — loading and offload station counts  
- `D` — MSD pool size  

Determine whether the system is constrained by **loading**, **offload**, **device pool**, or **vehicle count**, and compute minimum `D`, `S_L`, `S_O`.

## Arrival rates

Total mission completions per day:

```text
λ_mission = V × M   (missions/day)
λ_mission_per_hour = λ_mission / H   where H = operating hours/day (default 24)
```

Each completed mission returns **one device** to offload (one device per mission in v2).  
Each device reload also hits the loading queue once per cycle.

For steady-state sizing, treat both queues as Poisson with rate:

```text
λ = λ_mission_per_hour   (devices/hour through load and offload)
```

## Service rates (split M/M/c queues)

Loading and offload are **separate queues** with different service rates:

```text
μ_L = 1 / T_L   (devices/hour per loading station)
μ_O = 1 / T_O   (devices/hour per offload station)
c_L = S_L,  c_O = S_O
```

Offered load (traffic intensity):

```text
ρ_L = λ / (S_L × μ_L)   must be < 1 for stability
ρ_O = λ / (S_O × μ_O)   must be < 1 for stability
```

If `ρ ≥ 1` on either side, that queue is **saturated** — the bottleneck.

### High data volume mode

Continuous video recording can make offload ≈ mission duration. Enable in `fixtures/baseline.yaml`:

```yaml
modes:
  high_data_volume: true
  offload_factor: 0.9   # T_O = T_m × 0.9
```

When enabled, analysis and the sim use `T_O = T_m × offload_factor` instead of the fixed offload slider.

## Erlang C (wait probability)

For an M/M/c queue with `ρ < 1`, the probability an arriving device must wait:

```text
P(wait) = ErlangC(λ, μ, c)
```

Implemented in `capacity_model.erlang_c`. Mean wait in queue:

```text
W_q = P(wait) / (c × μ - λ)
```

Mean time in system for load or offload:

```text
W_load = W_q,L + T_L
W_offload = W_q,O + T_O
```

## Device pool — Little's Law

A device is "in the system" from load queue entry until it returns to READY.  
Cycle time (approximate, steady state):

```text
T_cycle ≈ W_load + T_m + W_offload
```

Required devices in circulation:

```text
D_required = λ × T_cycle
```

Add a small buffer (default 10%) for variability:

```text
D_recommended = ceil(D_required × (1 + buffer))
```

Also enforce a **floor**: vehicles need at least one device to start; with `P` ports, planning floor is often `V` (not `2V` unless you preload both ports).

## Bottleneck classification

Compute utilization for each resource:

| Resource | Utilization |
|----------|-------------|
| Loading | `ρ_L = λ / (S_L × μ_L)` |
| Offload | `ρ_O = λ / (S_O × μ_O)` |
| Devices | `D / D_required` (inverted: shortage if `D < D_required`) |
| Vehicles | Missions limited if insufficient loaded devices → sim shows "waiting" |

**Bottleneck** = highest `ρ` above target (default 85%), else `devices` if pool short, else `balanced`.

## Station sizing (inverse problem)

Given target utilization `ρ*` (default 0.85):

```text
S_L_min = ceil(λ / (μ × ρ*))
S_O_min = ceil(λ / (μ × ρ*))
```

Offload is often the binding constraint in high-tempo ops because every mission must offload before reuse.

## Worked example

| Parameter | Value |
|-----------|-------|
| Vehicles | 8 |
| Missions/vehicle/day | 3 |
| Mission duration | 2.0 h |
| Process time (load & offload) | 0.5 h |
| Loading stations | 2 |
| Offload stations | 3 |
| MSD pool | 20 |

```text
λ = 8 × 3 / 24 = 1.0 devices/hour
μ = 1 / 0.5 = 2.0 devices/hour/station

ρ_L = 1 / (2 × 2) = 0.25
ρ_O = 1 / (3 × 2) = 0.167
```

Queues are stable with headroom. If `T_p` rises to 1.0 h with 2 offload stations:

```text
μ = 1.0, ρ_O = 1 / (2 × 1) = 0.5   still stable
```

With 1 offload station: `ρ_O = 1.0` → **saturated** → bottleneck = `offload`.

Run the numbers:

```bash
python -m analysis.capacity_model --vehicles 8 --missions-per-day 3 \
  --mission-hours 2 --process-hours 0.5 --loading-stations 2 --offload-stations 1
```

## Relationship to the simulator

`index.html` uses **ticks** instead of hours. For validation:

```text
tick_duration_hours = operating_hours / ticks_per_day   (calibrate in Phase 2)
```

The sim exposes queue depths and "vehicles waiting" — if analysis says offload-bound, `OFFLOAD QUEUE` should grow under matched parameters.

## What we deliberately omit (for now)

- Bulk failure / re-sanitize paths  
- Non-Poisson burst ATO windows (Phase 4 Monte Carlo)  
- Cost optimization (Phase 3 investment framework)  

Keep the model simple; extend only when a requirement forces it.
