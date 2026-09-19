# Detailed Workflow & State Machine Documentation

This document explains the complete operational workflow modeled by the simulator. It is the single source of truth for the state machine.

## Philosophy

The simulator deliberately uses a **strict, explicit, timer-driven state machine** rather than event-driven or animation-driven logic. This makes behavior predictable, debuggable, and easy for AI agents (like Cursor) to reason about and extend.

## The 11 States

| State                | Meaning                                      | How It Enters This State                  | How It Leaves This State                  | Typical Duration          | Notes for Cursor |
|----------------------|----------------------------------------------|-------------------------------------------|-------------------------------------------|---------------------------|------------------|
| `READY`              | Device is sanitized and available in the pool | End of sanitization or initial state     | Enters `QUEUED_LOADING` when there is capacity | Indefinite               | Starting state for most devices |
| `QUEUED_LOADING`     | Waiting in line for a loading station        | `READY` devices are periodically moved here | Loading station pulls it                  | Variable (queue length)  | Explicit queue prevents devices getting lost |
| `LOADING`            | Being loaded with maps + threats + procedures at a loading station | Pulled from loading queue by a free station | Timer expires (per-device `loadDuration`) | `loadDuration(d) = max(1, round(d.loadTicks * d.dataQty))`; defaults from `config.loadTime` | This represents "prep with current intel" |
| `LOADED`             | Has valid current mission data               | Finished `LOADING`                        | Assigned to a vehicle with a free port    | Until assigned           | Only `LOADED` devices can be assigned |
| `ASSIGNED`           | Temporarily assigned to a vehicle            | Matched to a free vehicle slot            | Immediately transitions to `INSTALLED`    | Instant (in v2)          | Kept for future animation extensibility |
| `INSTALLED`          | Physically in one of the vehicle's 2 USB ports | Arrived at vehicle                        | Vehicle starts mission                    | Until mission starts     | Vehicle can have max 2 |
| `ON_MISSION`         | Vehicle is operating with this device        | Vehicle decides to start a mission        | Mission timer expires                     | `config.missionDuration` | Vehicle must have ≥1 device to start |
| `MISSION_DONE`       | Mission finished, device released            | Vehicle mission timer expires             | Moved to offload queue                    | Instant                  | Device is now "dirty" with recorded data |
| `QUEUED_OFFLOAD`     | Waiting for an offload station               | Moved from `MISSION_DONE`                 | Offload station pulls it                  | Variable                 | Second major queue in the system |
| `OFFLOADING`         | Data being extracted + device being sanitized | Pulled by offload station                 | Timer expires (per-device `offloadDuration`) | See per-device fields below | Critical bottleneck in high-tempo / video ops |
| `SANITIZED`          | Offload + security/compliance complete       | Finished `OFFLOADING`                     | Immediately returns to `READY`            | Very short               | Cycle complete — repeatable |

## Key Rules Enforced by the Simulator

1. **USB Hub Limit**: A vehicle can never have more than 2 devices installed at once (`slots: [null, null]`). A device with `portsNeeded === 2` occupies two free slots on the same vehicle.
2. **Minimum to Operate**: A vehicle will only start a mission if it has at least 1 device (`hasDevices` check).
3. **No Teleporting States**: Devices only change state when a timer expires or they are explicitly pulled by a station. The pipeline board animates tokens as a **view layer only** — CSS transforms must not drive `tick()` or mutate `devices[].state`.
4. **Explicit Queues**: `loadingQueue` and `offloadQueue` arrays ensure fair ordering and make bottlenecks visible in the metrics.

## Per-device game fields (v2.2)

Each device object carries overrides that win over global sliders after spawn:

| Field | Default | Effect |
|-------|---------|--------|
| `loadTicks` | `config.loadTime` | Base loading station occupancy |
| `offloadTicks` | `config.offloadTime` | Base offload occupancy (also floor in high-data mode) |
| `dataQty` | `1.0` (range ~0.5–2.0) | Scales load/offload duration; shown as `×N` on the token |
| `portsNeeded` | `1` (or `2`) | USB slots required on one vehicle |

**Formulas (browser sim):**

```text
loadDuration(d)    = max(1, round(d.loadTicks * d.dataQty))
offloadDuration(d) = highData
  ? max(d.offloadTicks, round(missionDuration * offloadFactor * d.dataQty))
  : max(1, round(d.offloadTicks * d.dataQty))
```

Global sliders set defaults for **new / reset** devices only. Editing a selected token mid-`LOADING` / `OFFLOADING` scales the remaining station timer proportionally. The capacity banner shows a **Live mix** note when mean per-device times diverge from globals. Python `analysis/sim_engine.py` still uses homogeneous times for regression.

## Pipeline board (visualization)

Zones left-to-right: `READY pool → LOAD stations (+ queue / loaded) → VEHICLE ports → ON MISSION → OFFLOAD stations (+ queue)`.

Tokens are persistent DOM nodes (`data-device-id`) positioned with CSS `transform` toward slot wells. Animation duration scales with the speed slider but never blocks the next tick.

## Bottleneck report

While the sim runs, observed bottlenecks (`loading` / `offload` / `devices` / `balanced` from `inferObservedBottleneck`) accumulate:

- tick counts and hours per kind
- episodes with start/end tick, duration, and peak queue depths

Export via **Export report** or inside **Export metrics** JSON (`bottleneckReport`).

## Main Simulation Loop (in `index.html`)

The heart of the simulator is the `simulationStep()` function (driven by `tick()` when running, or **Step** once while paused). Every tick it calls (in order):

```js
processLoadingStations();
processOffloadStations();
queueReadyDevicesForLoading();
assignLoadedDevicesToVehicles();
startMissionsWherePossible();
endFinishedMissions();
queueFinishedDevicesForOffload();
updateUI();
```

This ordering is important. Changing the order can create subtle bugs (e.g. assigning devices before they finish loading).

## Configuration Object

All tunable parameters live in the `config` object at the top of the script. This makes it very easy for Cursor to add new parameters later (e.g. `vehiclePortCount`, `failureRate`, `costPerDevice`). Global load/offload sliders remain the defaults for newly spawned devices; per-device fields are edited in the Device Inspector.

## Metrics & Observability

All metrics shown on the dashboard are derived live from the current state of `devices[]` and `vehicles[]`. There is no separate "simulation state" — the arrays *are* the state.

This design makes the system easy to inspect and debug.

## Common Extension Points

- **Add failure modes**: Add a small random chance in `endCompletedMissions()` to move a device to a new `FAILED` state.
- **Add cost modeling**: Add properties to `config` and calculate running cost in `updateUI()`.
- **Support different vehicle types**: Turn `vehicles` into an array of objects with a `portCount` property.
- **Scenario saving**: Serialize the `config` object + current device/vehicle states to JSON.

## Why This Design Is Good for AI Agents

- Single source of truth for state (`devices` and `vehicles` arrays).
- All transitions are explicit and documented.
- No hidden side effects from DOM or animation.
- Clear separation between "what should happen" (state machine) and "what the user sees" (UI rendering).
- Minimal dependencies (just Tailwind CDN + Font Awesome).

This makes the codebase much easier for Cursor to modify correctly on the first try.