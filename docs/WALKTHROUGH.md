# MSD Ops Simulator — Walkthrough

This walkthrough shows how to run the **interactive simulator** and use the **capacity model** to size MSD devices and loading/offload stations. Allow about 5 minutes.

## Prerequisites

- Any modern browser (no build step)
- Python 3.11+ for capacity analysis (stdlib only; pytest optional for tests)

```bash
# Optional
pip install pytest playwright
python -m playwright install chromium
```

---

## Part 1 — Open the simulator

1. Open `index.html` in your browser.
2. You should see **v2.1** with a **Capacity analysis** banner above the config panel.

![Initial configuration with analysis banner](images/01-initial-config.png)

### Shared config

Defaults come from `fixtures/baseline.yaml` (synced to `js/shared-config.js`):

- **20 ticks = 1 hour** (mission 40 ticks = 2 h, process 10 ticks = 0.5 h)
- Edit YAML, then run `python scripts/sync-config.py` and reload the page

### Configuration sliders (left panel)

| Slider | Meaning |
|--------|---------|
| **Vehicles** | Platforms that fly/drive missions (each has a 2-port USB hub) |
| **Pool Size (MSDs)** | Total reusable devices in the system |
| **Loading Stations** | Where devices receive maps/threats/procedures |
| **Offload Stations** | Where mission data is extracted and devices sanitized |
| **Mission Duration** | Ticks the vehicle spends on mission |
| **Process Time** | Ticks for load **or** offload at a station |
| **Missions / vehicle / day** | Drives analysis arrival rate λ (not a hard sim throttle) |

All simulation logic reads from the `config` object — sliders update it live.

---

## Part 2 — Capacity banner & Apply recommendation

The banner shows **predicted bottleneck** from the same M/M/c math as `analysis/capacity_model.py`:

- **ρ_load**, **ρ_offload**, recommended device pool, minimum station counts
- If sim queues disagree (e.g. offload backing up), the banner notes `(sim queues suggest …)`

Click **Apply recommendation** to set sliders to analysis minimums and reset the sim.

Click **Export metrics** to download JSON (`config`, `analysis`, live queue depths, missions/hour) for regression.

---

## Part 3 — Run a baseline scenario

1. Leave defaults: **8 vehicles**, **20 MSDs**, **2 loading**, **3 offload** stations.
2. Click **Start**.
3. Watch the metrics row:
   - **MISSIONS COMPLETED** should climb.
   - **OFFLOAD QUEUE** and **LOADING QUEUE** should stay moderate.
   - **VEHICLES WAITING** should stay near zero if the pool is sized correctly.

![Running steady state](images/02-running-steady-state.png)

### Event log

The log shows timer-driven transitions: `LOADING`, `INSTALLED`, `MISSION`, `OFFLOADING`, `READY`.  
States only change when timers expire — not from animation.

### Device state summary

The pills at the bottom count devices in each of the **11 states** (see `docs/WORKFLOW.md`).

---

## Part 4 — Find a bottleneck (offload)

1. Click **Pause**.
2. Increase **Vehicles** to **12**.
3. Reduce **Offload Stations** to **1**.
4. Click **Reset**, then **Start** again.
5. Observe **OFFLOAD QUEUE** grow and missions slow — offload is the constraint.

![Offload bottleneck](images/03-offload-bottleneck.png)

This matches the analysis model: when `ρ_offload = λ / (S_O × μ) → 1`, the queue backs up.

---

## Part 5 — Size investments with the capacity model

Before buying more stations or devices, run the analysis CLI:

```bash
python -m analysis.capacity_model --config fixtures/baseline.yaml
```

![Capacity analysis CLI](images/04-capacity-analysis-cli.png)

Read the output:

- **ρ** (utilization) for loading and offload — keep below ~0.85 for headroom
- **Devices recommended** — from Little's Law (λ × cycle time + buffer)
- **stations min** — inverse sizing at target utilization
- **Bottleneck** — where to invest first

Full formulas: `docs/CAPACITY_ANALYSIS.md`  
Decision rules: `docs/INVESTMENT_FRAMEWORK.md`

### JSON export (for scripts)

```bash
python -m analysis.capacity_model --format json --vehicles 12 --missions-per-day 6 \
  --offload-stations 1 --process-hours 1.0
```

---

## Part 6 — Regenerate screenshots

```bash
python scripts/capture-screenshots.py
```

Writes PNGs to `docs/images/` for this walkthrough.

---

## Quick reference — 11 states

| State | Plain English |
|-------|----------------|
| READY | Sanitized, available in pool |
| QUEUED_LOADING | Waiting for a loading station |
| LOADING | Being loaded with mission data |
| LOADED | Ready to install in a vehicle |
| ASSIGNED → INSTALLED | In a vehicle USB port |
| ON_MISSION | Vehicle operating |
| MISSION_DONE → QUEUED_OFFLOAD | Waiting for offload |
| OFFLOADING | Data extract + sanitize |
| SANITIZED → READY | Cycle complete |

---

## Next steps (beads)

```bash
bd ready    # Phase 1+ tasks: sim/analysis alignment, investment CSV, validation
```

See `docs/ROADMAP.md` for the full program.
