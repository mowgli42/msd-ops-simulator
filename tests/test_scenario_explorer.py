"""Scenario explorer multi-parameter sweeps (#9)."""

from pathlib import Path

from analysis.capacity_model import OpsParameters
from analysis.config_loader import load_shared_config, to_ops_parameters
from analysis.scenario_explorer import (
    explore,
    load_sweep_config,
    preferred_summary,
    write_csv,
)

ROOT = Path(__file__).resolve().parents[1]


def test_load_sweep_briefing_fixture():
    cfg = load_sweep_config(ROOT / "fixtures" / "sweep_briefing.yaml", repo_root=ROOT)
    assert cfg.method == "grid"
    assert len(cfg.ranges) == 3
    assert cfg.base.vehicles == 8


def test_explore_finds_feasible_preferred():
    cfg = load_sweep_config(ROOT / "fixtures" / "sweep_briefing.yaml", repo_root=ROOT)
    rows = explore(cfg)
    assert len(rows) == 4 * 5 * 5  # L 1-4 × O 1-5 × pool 5 values
    feasible = [r for r in rows if r.feasible]
    assert len(feasible) >= 1
    assert feasible[0].score >= feasible[-1].score or not feasible[-1].feasible
    summary = preferred_summary(rows, top_n=3)
    assert "preferred combinations" in summary.lower() or "Top" in summary


def test_lhs_method_respects_sample_cap():
    cfg = load_sweep_config(ROOT / "fixtures" / "sweep_briefing.yaml", repo_root=ROOT)
    cfg.method = "lhs"
    cfg.lhs_samples = 12
    rows = explore(cfg)
    assert len(rows) == 12


def test_pareto_marks_non_dominated(tmp_path):
    cfg = load_sweep_config(ROOT / "fixtures" / "sweep_briefing.yaml", repo_root=ROOT)
    rows = explore(cfg)
    pareto = [r for r in rows if r.pareto]
    assert len(pareto) >= 1
    out = tmp_path / "sweep.csv"
    write_csv(rows, out)
    text = out.read_text(encoding="utf-8")
    assert "score" in text
    assert "pareto" in text


def test_cli_runs(tmp_path):
    import subprocess
    import sys

    out = tmp_path / "out.csv"
    js = tmp_path / "out.json"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "analysis.scenario_explorer",
            "--config",
            str(ROOT / "fixtures" / "sweep_briefing.yaml"),
            "-o",
            str(out),
            "--json",
            str(js),
            "--top",
            "5",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert out.exists()
    assert js.exists()
