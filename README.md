# MSD Ops Simulator

**Mission Storage Device Operations Simulator** — a decision-support tool for reusable storage device logistics in vehicle operations (aircraft, ground vehicles, etc.).

Use the interactive simulator to see bottlenecks, then the capacity model to size MSD pools and loading/offload stations.

## Screenshots

### Configuration and capacity analysis

The v2.1 UI links live sliders to the same M/M/c queueing math as the Python CLI.

| Initial setup | Steady-state run |
|---------------|------------------|
| ![Configuration and analysis banner](docs/images/01-initial-config.png) | ![Simulator running](docs/images/02-running-steady-state.png) |

| Offload bottleneck (stress case) | Capacity CLI |
|----------------------------------|--------------|
| ![Offload queue backing up](docs/images/03-offload-bottleneck.png) | ![Analysis output](docs/images/04-capacity-analysis-cli.png) |

Full walkthrough: [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md)

## What it does

- Makes the **full MSD operational workflow** visible and interactive.
- Shows the **2-port USB hub constraint** per vehicle.
- Highlights where **loading vs offloading** becomes the bottleneck.
- Supports investment decisions: more devices, more stations, or faster process time.

## State machine

Eleven timer-driven states (see [docs/WORKFLOW.md](docs/WORKFLOW.md)):

```mermaid
stateDiagram-v2
    [*] --> READY
    READY --> QUEUED_LOADING
    QUEUED_LOADING --> LOADING
    LOADING --> LOADED
    LOADED --> ASSIGNED
    ASSIGNED --> INSTALLED
    INSTALLED --> ON_MISSION
    ON_MISSION --> MISSION_DONE
    MISSION_DONE --> QUEUED_OFFLOAD
    QUEUED_OFFLOAD --> OFFLOADING
    OFFLOADING --> SANITIZED
    SANITIZED --> READY
```

## Quick start

**Simulator** — open in any browser, no build step:

```bash
xdg-open index.html
```

**Analysis and tests:**

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
python scripts/sync-config.py
./scripts/run-tests.sh
python -m analysis.capacity_model --config fixtures/baseline.yaml
python -m analysis.capacity_model --config fixtures/baseline.yaml --monte-carlo 200
python -m analysis.regression
./scripts/export-sensitivity.sh stations output/sensitivity-stations.csv
```

Refresh screenshots: `python scripts/capture-screenshots.py` (requires Playwright).

## Repository map

| Path | Purpose |
|------|---------|
| `index.html` | Interactive simulator + analysis banner |
| `fixtures/baseline.yaml` | Shared scenario (20 ticks = 1 hour) |
| `analysis/capacity_model.py` | M/M/c sizing CLI (`--monte-carlo N` for Poisson validation) |
| `analysis/monte_carlo.py` | Optional offload wait distribution sampler |
| `analysis/regression.py` | Analysis vs sim alignment checks |
| `analysis/sensitivity.py` | CSV investment sweeps |
| `docs/CAPACITY_ANALYSIS.md` | Queueing formulas |
| `docs/INVESTMENT_FRAMEWORK.md` | Which lever to pull when constrained |
| `docs/ROADMAP.md` | Program phases |
| `AGENTS.md` | Guide for AI coding agents |

## Investment analysis

Use the simulator to find your bottleneck, then:

```bash
./scripts/export-sensitivity.sh stations output/sensitivity-stations.csv
```

Open the CSV in Excel or LibreOffice. See [docs/INVESTMENT_FRAMEWORK.md](docs/INVESTMENT_FRAMEWORK.md).

## Issue tracking

This project uses [beads](https://github.com/gastownhall/beads) (`bd`):

```bash
bd ready
bd prime
```

## License

Internal engineering decision-support tool. See [LICENSE](LICENSE).
