# Process-vs-inventory analysis (GitHub #15–#22)

## Purpose

Extend the capacity analysis stack so planners can compare **buy devices** vs
**use 2nd slot** vs **cut T_O**, using a shared-cabinet model, topology codes
`1-1-1` / `2-3-2` / `5-3-5`, wait accounting over 100 mission cycles, optional
shift-pulse arrivals, comparison plots, and a recommend table.

Gherkin sources of truth live in `openspec/features/*.feature`.

## Requirements

### Requirement: Shared load/offload cabinet model (GitHub #16)

`OpsParameters` SHALL accept `shared_station`, `cabinet_slots`, and
`slots_in_use`. When `shared_station` is omitted or false, today's independent
`loading_stations` / `offload_stations` M/M/c behavior SHALL be preserved.

When `shared_station` is true:

- Concurrent servers `c` SHALL equal `slots_in_use` (not independent load+offload counts).
- Cabinet utilization SHALL be `ρ_cabinet = λ × (T_L + T_O) / c` when load and
  offload cannot overlap on one slot.
- `analyze()` SHALL emit `cabinet_rho` and notes when `slots_in_use < cabinet_slots`.
- Bottleneck labels SHALL include `shared_station`, `offload_time`, `offload`,
  `devices`, `loading`, and `balanced`.
- The CLI SHALL print `slots_available`, `slots_in_use`, `cabinet_rho`, and
  warn when YAML station counts disagree with `cabinet_slots` or when
  independent-queue ρ understates a shared cabinet.
- The sim engine SHALL represent usable slots that both queues compete for
  (or document the approximation).

#### Scenario: Cabinet ρ with one slot equals combined service

- **GIVEN** λ=1 device/hour, T_L=T_O=0.5 h, `slots_in_use=1`, `shared_station=true`
- **WHEN** `analyze()` runs
- **THEN** `cabinet_rho` SHALL equal 1.0
- **AND** with `slots_in_use=2`, `cabinet_rho` SHALL equal 0.5

#### Scenario: High-data offload unstable on one slot

- **GIVEN** high-data T_O=1.8 h and `slots_in_use=1`
- **WHEN** `analyze()` runs
- **THEN** the offload/cabinet path SHALL be marked unstable

### Requirement: Topology fixtures and V-S-D codes (GitHub #17)

The repo SHALL provide:

- `fixtures/shared-cabinet.yaml` — site: `shared_station: true`,
  `cabinet_slots: 2`, `slots_in_use: 1`, `ports_per_vehicle: 1`
- `fixtures/topologies/1-1-1.yaml`, `2-3-2.yaml`, `5-3-5.yaml`
- `fixtures/topologies/README.md` documenting V-S-D and the 100-cycle horizon

Each topology file SHALL load through `config_loader.to_ops_parameters`.
CLI SHALL accept `--topology 1-1-1` or `--config fixtures/topologies/1-1-1.yaml`.
Tests SHALL freeze the V/S/D mapping. README / AGENTS.md SHALL cite
`shared-cabinet.yaml` for site analysis and keep `baseline.yaml` as the demo factory.

#### Scenario: Load topology 1-1-1

- **GIVEN** `fixtures/topologies/1-1-1.yaml`
- **WHEN** loaded via `to_ops_parameters`
- **THEN** vehicles=1, device_pool=1, and station mapping matches the fixture header

### Requirement: Process-time decomposition (GitHub #18)

Optional YAML `process:` block SHALL derive effective times:

```text
T_O = T_mount + B_raw × (1 − r) / R_proto + T_sanitize
T_L = T_write + B_preload / R_write + T_verify
```

If `process` is absent, `effective_offload_hours()` SHALL keep today's slider /
high-data behavior. Sensitivity SHALL add `--mode process` (compression × rate)
and `--mode buy` (pool × slots_in_use × offload_time). CAPACITY_ANALYSIS.md
SHALL document that compression does not help sanitize-bound offload.

#### Scenario: Double protocol rate halves extract time

- **GIVEN** a process block with fixed bytes and sanitize
- **WHEN** `protocol_rate_MBps` is doubled
- **THEN** the extract (bytes/rate) component SHALL halve
- **AND** sanitize hours SHALL be unchanged

### Requirement: Per-device wait accounting and wait_report (GitHub #19)

`sim_engine.Device` SHALL accumulate tick counters for wait-load, wait-assign,
wait-offload, and service/mission times without changing AGENTS.md tick order.
Service time SHALL NOT count as wait.

`python -m analysis.wait_report` SHALL stop at N completed missions (default 100),
write CSV + PNG, and keep existing `SimMetrics` stable.

#### Scenario: Offload-saturated fixture shows offload wait dominance

- **GIVEN** an offload-saturated topology
- **WHEN** `wait_report` runs for 100 missions
- **THEN** total offload wait SHALL greatly exceed assign wait

### Requirement: Shift-pulse arrival mode (GitHub #20)

Config SHALL support:

```yaml
arrival:
  mode: smooth   # default — regression-identical
  # mode: shift
  preload_window_hours: 2
  offload_window_hours: 2
```

Analytic pulse SHALL report `T_clear = ceil(N/c)×T_O`, `W_last = T_clear − T_O`,
and `λ_window`. Smooth mode SHALL remain default. Worked example: 8 returns,
c=1, T_O=0.5 → T_clear=4.0, W_last=3.5; c=2 → T_clear=2.0, W_last=1.5.

#### Scenario: Shift clear time with one slot

- **GIVEN** N=8 returning devices, c=1, T_O=0.5 h, arrival mode shift
- **WHEN** capacity analysis computes the pulse
- **THEN** T_clear SHALL be 4.0 h and W_last SHALL be 3.5 h

### Requirement: Topology comparison over 100 cycles (GitHub #21)

`python -m analysis.compare_topologies` SHALL run topologies
`1-1-1,2-3-2,5-3-5` for 100 completed cycles and emit CSV plus four core PNGs
(wait-by-stage, per-device wait small-multiples, utilization, cycle time /
recommended pool). Chart colors: load=steel, assign=grey, offload=amber.
Reuse `wait_report` counters; do not fork a second sim.

#### Scenario: One command emits compare artifacts

- **GIVEN** topology fixtures and wait accounting
- **WHEN** `compare_topologies --cycles 100` runs
- **THEN** `--outdir` SHALL contain the long CSV and four core PNGs

### Requirement: Recommend buy vs slot vs cut-T_O (GitHub #22)

`python -m analysis.recommend` SHALL score:

1. Buy devices (raise pool to recommended or +2/+4)
2. Use 2nd slot / +1 station
3. Cut T_O by 25% and by 50%

Output SHALL include bottleneck_after, ρ fields, D_recommended/D_actual,
T_cycle, optional shift metrics, wait totals when available, and stable yes/no.
Unstable packages SHALL be marked unstable (no fake finite cycle time).

#### Scenario: Long T_O on one bay prefers cut T_O or 2nd slot

- **GIVEN** 1 bay and T_O=1.8 h
- **WHEN** recommend runs
- **THEN** cut-T_O or 2nd-slot packages SHALL beat +devices on cabinet stability / wait
