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
- `T_O` — offload time (hours); optional `T_S` sanitize added at station  
- `T_I` — install/assign overhead (hours, default 0)  
- `P` — ports per vehicle (default 2)  
- `d` — devices per mission (default 1)  
- `d_min` — min devices installed to start a mission (default 1)  
- `S_L`, `S_O` — loading and offload station counts  
- `D` — MSD pool size  

Determine whether the system is constrained by **loading**, **offload**, **device pool**, **vehicle tempo**, or **ports**, and compute minimum `D`, `S_L`, `S_O`.

YAML / CLI can set any `OpsParameters` field (see `fixtures/baseline.yaml`). Use `replace_params()` in Python when scripting overrides.

## Arrival rates

Total mission completions per day:

```text
λ_mission = V × M   (missions/day)
λ_mission_per_hour = λ_mission / H   where H = operating hours/day (default 24)
```

Each completed mission returns `d` devices to offload (`devices_per_mission`, default 1).  
Each device reload also hits the loading queue once per cycle.

For steady-state sizing, treat both queues as Poisson with rate:

```text
λ = λ_mission_per_hour × d   (devices/hour through load and offload)
```

## Service rates (split M/M/c queues)

Loading and offload are **separate queues** with different service rates:

```text
μ_L = 1 / T_L   (devices/hour per loading station)
T_O_eff = T_O + T_S   (sanitize adds station occupancy)
μ_O = 1 / T_O_eff
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
T_cycle ≈ W_load + T_I + T_m + W_offload
```

Required devices in circulation:

```text
D_required = λ × T_cycle
```

Add a small buffer (default 10%) for variability:

```text
D_recommended = ceil(D_required × (1 + buffer))
```

Also enforce a **floor**: `V × d_min`, or `V × P` when `preload_all_ports: true`.

## Full-workflow constraints

| Resource | Metric | Infeasible when |
|----------|--------|-----------------|
| Loading | `ρ_L = λ / (S_L × μ_L)` | `ρ_L ≥ 1` |
| Offload | `ρ_O = λ / (S_O × μ_O)` | `ρ_O ≥ 1` |
| Devices | `D_required` vs pool `D` | `D_recommended > D` |
| Vehicle tempo | `ρ_V = M / (H / T_m)` | `M > H / T_m` |
| Ports | onboard occupancy vs `V × P`; also `d_min ≤ P` | `d_min > P` or soft `ρ_ports` above target |

Additional derived metrics:

- **Device reuse rate** ≈ `min(1, D / D_required)` — feedback from offload back into READY  
- **Mission start delay** ≈ `(D_recommended − D) / λ` when the pool is short  

## Bottleneck classification

Priority order (hard failures first):

1. `loading` unstable  
2. `offload` unstable  
3. `vehicle_tempo` infeasible  
4. `ports` infeasible  
5. `devices` pool short of recommended  
6. Soft: highest utilization vs target among `{loading, offload, devices, vehicle_tempo, ports}`  
7. else `balanced`

`format_summary()` prints the full constraint ρ map for briefings.

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

## Related tooling

| Command | Purpose |
|---------|---------|
| `python -m analysis.capacity_model --config …` | Single-scenario analysis |
| `python -m analysis.scenario_explorer --config fixtures/sweep_briefing.yaml` | Multi-parameter sweeps + preferred ranking |
| `python -m analysis.generate_briefing --config … --sweep …` | HTML/Markdown briefing artifacts |

See [BRIEFING.md](BRIEFING.md) and [INVESTMENT_FRAMEWORK.md](INVESTMENT_FRAMEWORK.md).

## What we deliberately omit (for now)

- Bulk failure / re-sanitize paths  
- Non-Poisson burst ATO windows (Monte Carlo optional via `--monte-carlo`)  
- Explicit dollar cost optimization (use weighted score proxies in scenario explorer)  

Keep the model simple; extend only when a requirement forces it.
