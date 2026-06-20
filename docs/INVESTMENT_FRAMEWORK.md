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
