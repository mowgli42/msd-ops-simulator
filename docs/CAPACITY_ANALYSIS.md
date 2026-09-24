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

Loading and offload are **separate queues** with different service rates **when
`shared_station` is false** (demo factory / legacy fixtures):

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

### Shared cabinet (site model)

Real sites often share one Linux cabinet for load and offload. Config:

```yaml
operations:
  shared_station: true
  cabinet_slots: 2      # physical slots
  slots_in_use: 1       # current policy
```

When `shared_station` is true, load and offload **compete** for `c = slots_in_use`
servers. If a slot cannot overlap load∥offload:

```text
ρ_cabinet = λ × (T_L + T_O) / c
```

Example: λ=1, T_L=T_O=0.5, c=1 → ρ_cabinet=1.0; c=2 → 0.5.

Independent `ρ_L` / `ρ_O` **understate** occupancy on a shared cabinet — the CLI
prints `cabinet_rho` and a warning. Bottleneck labels include `shared_station`,
`offload_time` (long dwell with idle physical slots), `offload`, `devices`,
`loading`, and `balanced`.

Site fixture: `fixtures/shared-cabinet.yaml`. Demo factory remains
`fixtures/baseline.yaml` (8V / 2L / 3O / 20D).

Topology codes `V-S-D` (platforms-stations-devices): see
`fixtures/topologies/README.md`. When shared, **S = slots_in_use**.

### Process-time decomposition

Optional `process:` block derives:

```text
T_O = T_mount + B_raw × (1 − r) / R_proto + T_sanitize
T_L = T_write + B_preload / R_write + T_verify
```

Compression reduces bytes on the wire; it does **not** help sanitize-bound
offload. If `process` is absent, sliders / high-data mode apply as before.

### High data volume mode

Continuous video recording can make offload ≈ mission duration. Enable in `fixtures/baseline.yaml`:

```yaml
modes:
  high_data_volume: true
  offload_factor: 0.9   # T_O = T_m × 0.9
```

When enabled, analysis and the sim use `T_O = T_m × offload_factor` instead of the fixed offload slider.

### Shift-pulse arrivals

Daily mean λ understates last-device wait when everyone lands together:

```text
N = devices returning in the window  (≈ vehicles if 1 MSD per platform)
T_clear = ceil(N / c) × T_O
W_last  = T_clear − T_O
```

Worked example: 8 returns, c=1, T_O=0.5 h → T_clear=4.0 h, W_last=3.5 h;
c=2 → T_clear=2.0 h, W_last=1.5 h.

```bash
python -m analysis.capacity_model --config fixtures/shared-cabinet.yaml \
  --arrival shift --window-hours 2
```

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
- Cost dollars in the recommend table (v1 is physical packages only)

Shift-pulse and Monte Carlo are available as optional modes; default analysis
remains smooth Poisson M/M/c.

## Process-vs-inventory tooling

```bash
# Site cabinet
python -m analysis.capacity_model --config fixtures/shared-cabinet.yaml

# Topology shorthand
python -m analysis.capacity_model --topology 1-1-1

# Wait report (100 mission cycles)
python -m analysis.wait_report --topology 1-1-1 --missions 100 \
  -o output/wait-1-1-1.png --csv output/wait-1-1-1.csv

# Compare 1-1-1 / 2-3-2 / 5-3-5
python -m analysis.compare_topologies --cycles 100 --outdir output/compare-100/

# Recommend buy vs 2nd slot vs cut T_O
python -m analysis.recommend --config fixtures/shared-cabinet.yaml --cycles 100
```

OpenSpec + Gherkin: `openspec/specs/process-vs-inventory/spec.md`,
`openspec/features/*.feature`.
