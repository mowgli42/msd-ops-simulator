# Agent Instructions — MSD Ops Simulator

This project uses **bd (beads)** for issue tracking. Run `bd prime` for full workflow context.

## Project context

**Mission Storage Device (MSD) Operations Simulator** — a prototype decision-support tool for reusable storage device logistics in vehicle operations.

The codebase is structured to be **easy for Cursor and other AI agents to understand, extend, and maintain**: clear states, timer-driven logic, explicit queues, minimal magic.

| Asset | Purpose |
|-------|---------|
| `index.html` | Timer-driven 11-state discrete simulator (main UI) |
| `docs/WORKFLOW.md` | State machine reference — read before changing sim logic |
| `fixtures/baseline.yaml` | Shared scenario — hours + tick mapping (`ticks_per_hour: 20`) |
| `fixtures/regression_scenarios.yaml` | Analysis vs sim alignment cases |
| `scripts/sync-config.py` | Regenerates `js/shared-config.js` after YAML edits |
| `js/capacity-model.js` | Browser port of `analysis/capacity_model.py` |
| `js/shared-config.js` | Auto-generated sim defaults from YAML |
| `analysis/capacity_model.py` | M/M/c queue sizing and bottleneck detection (`--monte-carlo N`) |
| `analysis/monte_carlo.py` | Poisson M/M/c offload wait distribution (validation) |
| `analysis/config_loader.py` | YAML loader + tick ↔ hour conversion |
| `analysis/sim_engine.py` | Python discrete sim (regression harness) |
| `analysis/regression.py` | Analysis vs sim steady-state checks |
| `analysis/sensitivity.py` | CSV sweep for investment tables |
| `docs/CAPACITY_ANALYSIS.md` | Formula reference for the analysis module |
| `docs/INVESTMENT_FRAMEWORK.md` | Which lever to pull when a bottleneck appears |
| `docs/WALKTHROUGH.md` | Operator walkthrough with screenshots |
| `docs/ROADMAP.md` | Phased program plan |

**Design principles:** Correct over flashy. Timer-driven state changes only. Explicit `loadingQueue` and `offloadQueue`. Ground truth = device/vehicle arrays.

## Recommended agent workflow

When asked to improve this project:

1. Read `README.md` for user-facing scope, then this file.
2. Read `docs/WORKFLOW.md` for the state machine.
3. Inspect `config` / sliders in `index.html` and `fixtures/baseline.yaml`.
4. Make small, well-commented changes.
5. Run `./scripts/run-tests.sh` and update docs if behavior changes.
6. Regenerate screenshots when UI layout changes: `python scripts/capture-screenshots.py`.

## Critical design decisions (preserve these)

- Devices only change state when their **timer expires** (not from DOM/animation).
- Two explicit queues (`loadingQueue`, `offloadQueue`) — devices must not get lost.
- Vehicles need **at least 1 device** installed to start a mission.
- After sanitization, devices return to `READY` to keep the cycle running.
- Python `analysis/sim_engine.py` uses a **missions/day throttle** so regression matches analysis λ.

## Extending the simulator (`index.html`)

### Tick order (do not reorder)

```text
processLoadingStations → processOffloadStations → queueReadyForLoading
→ assignLoadedToVehicles → startMissions → endMissions → queueForOffload → updateUI
```

### Adding a new state

1. Add to `STATES` constant.
2. Add handling in the appropriate `processXxx()` or tick step.
3. Update state summary renderer.
4. Document in `docs/WORKFLOW.md`.

### Changing vehicle port limit (default 2)

Search for `slots: [null, null]` and `vehicle.slots`. Keep configurable via YAML in a future phase if requested.

### Adding metrics or alerts

- Add calculations in `updateUI()` and `refreshAnalysisBanner()`.
- Extend `addLog()` for important transitions.
- Mirror observable logic in `analysis/observed.py` for regression tests.

### Multi-file refactor (future)

- `js/state-machine.js` — sim logic
- `js/ui.js` — rendering
- Keep `index.html` as thin orchestrator; run `scripts/sync-config.py` after YAML edits.

## Extending capacity analysis

1. Read `docs/CAPACITY_ANALYSIS.md` first.
2. Keep formulas in sync: `analysis/capacity_model.py` ↔ `js/capacity-model.js`.
3. Add unit tests in `tests/`; add regression cases to `fixtures/regression_scenarios.yaml`.
4. Bottleneck labels must match simulator observables (queue growth, vehicles waiting).

## Local setup

```bash
xdg-open index.html
python scripts/sync-config.py
python -m analysis.capacity_model --config fixtures/baseline.yaml
./scripts/run-tests.sh
python -m analysis.regression
./scripts/export-sensitivity.sh stations output/sensitivity-stations.csv
```

## Future roadmap (agent backlog)

See `docs/ROADMAP.md` and `bd ready`. Ideas not yet scheduled:

- Cost modeling in simulator UI
- Vehicle classes with varying port counts
- Optional FastAPI backend for scenario persistence
- SvelteKit UI split (only if explicitly requested)

## Beads

```bash
bd ready
bd show msd-ops-simulator-<id>
bd update <id> --claim
```

Epic: **MSD Ops — capacity analysis & walkthrough** (`.beads/msd-ops-plan.json`).

## Agent rules

- Use `bd` for task tracking — not markdown TODO lists.
- Prefer small, documented diffs; match existing naming and layout.
- Update `docs/WALKTHROUGH.md` screenshots when UI changes materially.
- Run `./scripts/run-tests.sh` after changing `analysis/` or sim tick order.
- Keep Cursor/agent instructions in this file, not `README.md`.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
