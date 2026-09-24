# Agent Instructions — MSD Ops Simulator

This project uses **bd (beads)** for issue tracking. Run `bd prime` for full workflow context.

## Project context

**Mission Storage Device (MSD) Operations Simulator** — a prototype decision-support tool for reusable storage device logistics in vehicle operations.

The codebase is structured to be **easy for Cursor and other AI agents to understand, extend, and maintain**: clear states, timer-driven logic, explicit queues, minimal magic.

| Asset | Purpose |
|-------|---------|
| `index.html` | Timer-driven 11-state discrete simulator (main UI) |
| `docs/WORKFLOW.md` | State machine reference — read before changing sim logic |
| `fixtures/baseline.yaml` | Demo factory — hours + tick mapping (`ticks_per_hour: 20`) |
| `fixtures/shared-cabinet.yaml` | Site cabinet minimal cell (shared station, 1 of 2 slots) |
| `fixtures/site-eight.yaml` | Live fleet: 8 platforms on one shared cabinet |
| `fixtures/topologies/` | Comparison series `1-1-1` / `2-3-2` / `5-3-5` |
| `fixtures/regression_scenarios.yaml` | Analysis vs sim alignment cases |
| `scripts/sync-config.py` | Regenerates `js/shared-config.js` after YAML edits |
| `js/capacity-model.js` | Browser port of `analysis/capacity_model.py` |
| `js/shared-config.js` | Auto-generated sim defaults from YAML |
| `analysis/capacity_model.py` | M/M/c queue sizing and bottleneck detection (`--monte-carlo N`) |
| `analysis/wait_report.py` | Per-device wait hours over N completed missions |
| `analysis/compare_topologies.py` | Topology comparison CSV + PNGs |
| `analysis/recommend.py` | Buy-devices vs 2nd-slot vs cut-T_O |
| `openspec/` | OpenSpec + Gherkin (process-vs-inventory) |
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

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:46cd31e7 -->
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

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   bd dolt push
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->

<!-- BEGIN BEADS CODEX SETUP: generated by bd setup codex -->
## Beads Issue Tracker

Use Beads (`bd`) for durable task tracking in repositories that include it. Use the `beads` skill at `.agents/skills/beads/SKILL.md` (project install) or `~/.agents/skills/beads/SKILL.md` (global install) for Beads workflow guidance, then use the `bd` CLI for issue operations.

### Quick Reference

```bash
bd ready                # Find available work
bd show <id>            # View issue details
bd update <id> --claim  # Claim work
bd close <id>           # Complete work
bd prime                # Refresh Beads context
```

### Rules

- Use `bd` for all task tracking; do not create markdown TODO lists.
- Run `bd prime` when Beads context is missing or stale. Codex 0.129.0+ can load Beads context automatically through native hooks; use `/hooks` to inspect or toggle them.
- Keep persistent project memory in Beads via `bd remember`; do not create ad hoc memory files.

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.
<!-- END BEADS CODEX SETUP -->
