# Agent Instructions — MSD Ops Simulator

This project uses **bd (beads)** for issue tracking. Run `bd prime` for full workflow context.

## Project context

**Mission Storage Device (MSD) Operations Simulator** — a prototype decision-support tool for reusable storage device logistics in vehicle operations.

| Asset | Purpose |
|-------|---------|
| `index.html` | Timer-driven 11-state discrete simulator (main UI) |
| `docs/WORKFLOW.md` | State machine reference — read before changing sim logic |
| `fixtures/baseline.yaml` | Shared scenario — hours + tick mapping (`ticks_per_hour: 20`) |
| `scripts/sync-config.py` | Regenerates `js/shared-config.js` after YAML edits |
| `js/capacity-model.js` | Browser port of `analysis/capacity_model.py` |
| `js/shared-config.js` | Auto-generated sim defaults from YAML |
| `analysis/capacity_model.py` | M/M/c queue sizing and bottleneck detection |
| `analysis/config_loader.py` | YAML loader + tick ↔ hour conversion |
| `docs/CAPACITY_ANALYSIS.md` | Formula reference for the analysis module |
| `docs/INVESTMENT_FRAMEWORK.md` | Which lever to pull when a bottleneck appears |
| `docs/WALKTHROUGH.md` | Operator walkthrough with screenshots |
| `docs/ROADMAP.md` | Phased program plan |

**Design principles:** Correct over flashy. Timer-driven state changes only. Explicit `loadingQueue` and `offloadQueue`. Ground truth = device/vehicle arrays.

## Local setup

```bash
# Simulator — open in browser (loads js/shared-config.js from fixtures/baseline.yaml)
xdg-open index.html

# After editing fixtures/baseline.yaml:
python scripts/sync-config.py

# Analysis CLI
python -m analysis.capacity_model --config fixtures/baseline.yaml
python -m analysis.capacity_model --vehicles 8 --missions-per-day 3

# Tests (syncs config + pytest + regression)
./scripts/run-tests.sh

# Regression: analysis vs sim
python -m analysis.regression

# Sensitivity CSV
./scripts/export-sensitivity.sh stations output/sensitivity-stations.csv
python -m analysis.sensitivity --mode missions -o output/sensitivity-missions.csv
```

## Extending the simulator (`index.html`)

1. Read `docs/WORKFLOW.md` and the `STATES` constant.
2. Preserve tick order in `tick()`: stations → queues → assign → missions → offload queue.
3. Do not drive state from DOM/animation.
4. Document new states in `docs/WORKFLOW.md`.

## Extending capacity analysis

1. Read `docs/CAPACITY_ANALYSIS.md` first.
2. Keep `analysis/capacity_model.py` stdlib-only unless tests need pytest.
3. Add unit tests in `tests/` for any new formula.
4. Bottleneck labels must match simulator observables (queue growth, vehicles waiting).

## Beads

```bash
bd ready                              # next unblocked task
bd show msd-ops-simulator-<id>        # issue detail
bd update <id> --claim              # claim work
```

Epic: **MSD Ops — capacity analysis & walkthrough** (`.beads/msd-ops-plan.json`).

## Agent rules

- Use `bd` for task tracking — not markdown TODO lists.
- Prefer small, documented changes to `index.html`; extract to `js/` only when a phase calls for it.
- Update `docs/WALKTHROUGH.md` screenshots when UI layout changes materially.
- Run `./scripts/run-tests.sh` after changing `analysis/`.

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
