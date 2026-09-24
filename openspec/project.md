# MSD Ops Simulator — OpenSpec Project Context

## Purpose

Decision-support tool for reusable Mission Storage Device (MSD) logistics.
Planners must answer: **make the process faster vs buy more devices**, under
real site constraints (shared load/offload cabinet, shift pulses), with
plottable comparison runs across fleet topologies.

## Decision packages the tools must score

1. Buy more MSDs  
2. Use more station concurrency (2nd cabinet slot / extra bays)  
3. Cut process time (protocol, compression, sanitize tooling)

## Topology notation

`V-S-D` = **platforms-stations-devices**.

| Code  | Platforms | Stations                         | Devices |
|-------|-----------|----------------------------------|---------|
| 1-1-1 | 1         | 1 shared cabinet / 1 slot in use | 1       |
| 2-3-2 | 2         | 3                                | 2       |
| 5-3-5 | 5         | 3                                | 5       |

Default comparison horizon: **100 completed mission cycles** (not 100 ticks).

`fixtures/baseline.yaml` (8V / 2L / 3O / 20D) is the **demo factory**, not the
site cabinet. Site analysis defaults to `fixtures/shared-cabinet.yaml`.

## Spec index

| Capability | Spec | Gherkin | GitHub |
|------------|------|---------|--------|
| Process-vs-inventory epic | `specs/process-vs-inventory/spec.md` | `features/*.feature` | #15–#22 |
| Shared cabinet model | same | `features/shared-cabinet.feature` | #16 |
| Topology fixtures | same | `features/topology-fixtures.feature` | #17 |
| Process-time decomposition | same | `features/process-decomposition.feature` | #18 |
| Wait report | same | `features/wait-report.feature` | #19 |
| Shift-pulse arrivals | same | `features/shift-pulse.feature` | #20 |
| Topology comparison plots | same | `features/compare-topologies.feature` | #21 |
| Recommend packages | same | `features/recommend.feature` | #22 |

## Build order (beads)

1. Shared-station + slots-in-use model (#16)  
2. Site + topology fixtures (#17)  
3. Process-time decomposition (#18)  
4. Wait accounting + `wait_report` (#19)  
5. Shift-pulse arrival mode (#20)  
6. Comparison plots 1-1-1 / 2-3-2 / 5-3-5 (#21)  
7. `analysis.recommend` (#22)

Track with `bd ready`. Epic bead links GitHub #15.
