# Spec v2.1 — Offload separation & sensitivity analysis

Source: [Grok review](https://grok.com/share/c2hhcmQtMg_d867fef8-3c6e-480d-a036-958eb82215ba) (June 2026).

## Problem

1. **Single process time** — Loading (maps/threats) and offload (video/sensor extract + sanitize) are different operations. When offload ≈ mission duration, the model underestimates stations and pool size.
2. **Unstructured sensitivity** — Sliders explore one point at a time; leadership needs trade-offs: stations vs offload duration vs devices.

## Fixed vs decision variables

| Fixed (ops planning) | Decision (investment) |
|----------------------|------------------------|
| Vehicle count | Loading station count |
| Mission duration / tempo | Offload station count |
| Missions per vehicle per day | MSD pool size |
| | Load time (process improvement) |
| | Offload time (bandwidth, tooling) |

## Feature 1: Offload time separation

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `load_time` | 0.5 h (10 ticks) | Load maps/threats/procedures |
| `offload_time` | 0.5 h | Extract mission data + sanitize |
| `high_data_volume_mode` | false | Offload time = mission × factor |
| `offload_factor` | 0.9 | Multiplier in high-data mode (0.8–1.2) |

### Queueing model

- **Loading:** M/M/c with `c = loading_stations`, `μ = 1/load_time`
- **Offload:** M/M/c with `c = offload_stations`, `μ = 1/offload_time_effective`
- Cycle time: `W_load + mission + W_offload` (Little's Law for devices)

High-data mode: `offload_time_effective = mission_duration × offload_factor`

### Sim

- `processLoadingStations` uses `config.loadTime`
- `processOffloadStations` uses `effectiveOffloadTicks()`

## Feature 2: Sensitivity analysis

### Tiered methods (adopted)

| Level | Method | Status |
|-------|--------|--------|
| 1 | Manual sliders | Done |
| 2 | M/M/c analytical (`capacity_model.py`) | Done |
| 3 | Discrete-event sim (`sim_engine.py`) | Done |
| 4 | Sensitivity table + CSV | v2.1 UI + `analysis/sensitivity.py` |
| 5 | Monte Carlo | Beads backlog |

### UI panel

2D table: **offload time (% of mission)** × **offload station count**

Cell output: `ρ_offload`, bottleneck label (color).

Presets: Baseline, High video (100%), Constrained offload (1 station).

## Acceptance

- [ ] Load and offload times independent in sim, analysis, YAML
- [ ] High-data mode sets offload from mission × factor
- [ ] Sensitivity table in UI updates with config
- [ ] Regression case: offload = mission → predicted offload bottleneck
- [ ] `docs/CAPACITY_ANALYSIS.md` documents split queues
