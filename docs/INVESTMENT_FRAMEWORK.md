# Investment Framework — MSD Ops

Use the **simulator** to observe behavior, then the **capacity model** to size investments. This framework ranks the five levers when a bottleneck appears.

## Five investment levers

| Lever | What it buys | When to prioritize |
|-------|----------------|-------------------|
| **More MSD devices** | Larger circulating pool; reduces vehicle wait for loaded devices | `bottleneck = devices` or high "vehicles waiting" in sim |
| **More loading stations** | Higher load throughput `S_L × μ` | `ρ_L` ≥ target or loading queue grows without bound |
| **More offload stations** | Higher offload throughput; often critical at high tempo | `ρ_O` ≥ target or offload queue backs up (common case) |
| **Faster process time** | Increases `μ` for both stations (training, tooling, automation) | Both queues tight but capital for stations is constrained |
| **More vehicles** | More missions only if devices and stations already have headroom | Never first — adds `λ` and worsens queueing |

## Decision flow

```text
1. Run analysis/capacity_model with planned V and M
2. Read bottleneck label
3. Apply the matching row below
4. Re-run analysis until ρ_L, ρ_O < target and D ≥ D_required
5. Confirm in index.html simulator (queues stable, waiting ≈ 0)
```

## Bottleneck → action

| Bottleneck | Primary action | Secondary action |
|------------|----------------|------------------|
| `offload` | Add offload stations | Reduce process time; add devices only if vehicles starved |
| `loading` | Add loading stations | Reduce process time |
| `devices` | Increase MSD pool | Check if offload/load are actually slow (devices may be stuck in queue) |
| `balanced` | No capacity change | Tune for cost; optional buffer on devices |
| `vehicles` | N/A (input) | Lower M or add capacity before adding vehicles |

## Sizing targets

- **Utilization target:** 85% (`ρ* = 0.85`) — headroom for variability  
- **Device buffer:** 10% above Little's Law `D_required`  
- **Ports:** 2 per vehicle (v2 default); preloading both ports increases peak device demand  

## Reporting template

When presenting to leadership, include:

1. Inputs: `V`, `M`, `T_m`, `T_p`, operating hours  
2. Current: `S_L`, `S_O`, `D`  
3. Recommended: `S_L_min`, `S_O_min`, `D_recommended`  
4. Bottleneck and `ρ_L`, `ρ_O`  
5. One simulator screenshot with queues at steady state  

## Spreadsheet note

`MSD_Investment_Analysis.xlsx` is referenced in README but not in repo. Until restored, use:

```bash
./scripts/export-sensitivity.sh stations output/sensitivity-stations.csv
python -m analysis.sensitivity --mode missions -o output/sensitivity-missions.csv
```

Phase 3 may add a checked-in CSV template or xlsx export.

## Worked leadership examples

Each example uses `fixtures/baseline.yaml` defaults unless noted. Reproduce with:

```bash
python -m analysis.capacity_model --config fixtures/baseline.yaml [flags]
```

### Example 1 — Baseline (no investment needed)

**Scenario:** 8 vehicles, 3 missions/vehicle/day, 2 loading + 3 offload stations, pool of 20 devices.

| Field | Value |
|-------|-------|
| Arrival rate λ | 1.0 devices/hour |
| ρ_L / ρ_O | 0.25 / 0.17 |
| Cycle time | 3.04 h |
| Devices required | 3.04 → recommended **8** (pool 20) |
| Bottleneck | `balanced` |

**Leadership takeaway:** Current capacity has headroom. Optional Monte Carlo confirms low offload waits (P95 ≈ 0 h at baseline tempo):

```bash
python -m analysis.capacity_model --config fixtures/baseline.yaml --monte-carlo 200
```

**Action:** No station or device purchase. Use sensitivity CSV to plan growth before tempo increases.

---

### Example 2 — Offload saturation (add offload stations)

**Scenario:** Tempo increases to 10 vehicles × 8 missions/day with only **1** offload station.

| Field | Before | After (+1 offload station) |
|-------|--------|----------------------------|
| Arrival rate λ | 3.33 devices/hour | 3.33 devices/hour |
| ρ_O | **1.67** (unstable) | 0.83 |
| Offload stations | 1 (min **2**) | 2 |
| Cycle time | ∞ | 5.27 h |
| Devices recommended | 10 (pool 20) | **20** (pool 20) |
| Bottleneck | `offload` | `balanced` |

```bash
# Before — queue blows up
python -m analysis.capacity_model --config fixtures/baseline.yaml \
  --vehicles 10 --missions-per-day 8 --offload-stations 1

# After — add one offload station
python -m analysis.capacity_model --config fixtures/baseline.yaml \
  --vehicles 10 --missions-per-day 8 --offload-stations 2
```

**Leadership takeaway:** Offload is the binding constraint at high tempo. Adding one station restores stability but raises device demand to the full pool — budget for **+1 offload station** and verify the MSD pool can support ~18 devices in circulation.

**Action:** Primary lever = **more offload stations**. Confirm in `index.html` (offload queue drains, vehicles not waiting).

---

### Example 3 — Device pool shortfall (grow MSD inventory)

**Scenario:** Fleet grows to 12 vehicles at baseline tempo; device pool stays at **10**.

| Field | Before | After (pool → 12) |
|-------|--------|-------------------|
| Arrival rate λ | 1.5 devices/hour | 1.5 devices/hour |
| ρ_L / ρ_O | 0.38 / 0.25 | 0.38 / 0.25 |
| Stations | 2 load / 3 offload (adequate) | same |
| Devices recommended | **12** (pool 10) | 12 (pool 12) |
| Bottleneck | `devices` | `balanced` |

```bash
# Before — pool too small
python -m analysis.capacity_model --config fixtures/baseline.yaml \
  --vehicles 12 --device-pool 10

# After — add 2 devices to pool
python -m analysis.capacity_model --config fixtures/baseline.yaml \
  --vehicles 12 --device-pool 12
```

**Leadership takeaway:** Queues are stable but vehicles starve for loaded devices when the pool is below Little's Law + 10% buffer. Stations are not the fix — **more MSD devices** are.

**Action:** Increase pool to recommended count before adding vehicles or missions. Re-run analysis after any tempo change.
