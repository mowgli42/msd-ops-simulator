# Topology fixtures (V-S-D)

Notation is **platforms-stations-devices**:

| Code  | Vehicles | Stations (S)                         | Devices |
|-------|----------|--------------------------------------|---------|
| 1-1-1 | 1        | 1 usable shared-cabinet slot         | 1       |
| 2-3-2 | 2        | 3 usable shared slots                | 2       |
| 5-3-5 | 5        | 3 usable shared slots                | 5       |

When `shared_station: true`, **S = `slots_in_use`** (cabinet concurrency), not
independent `loading_stations + offload_stations`.

Site reference: `../shared-cabinet.yaml` (2 physical slots, 1 in use).
Demo factory: `../baseline.yaml` (8V / 2L / 3O / 20D) — **not** the site cabinet.

Default comparison horizon: **100 completed mission cycles**.

```bash
python -m analysis.capacity_model --topology 1-1-1
python -m analysis.compare_topologies --cycles 100 --outdir output/compare-100/
```
