"""Briefing report generation (#10)."""

from pathlib import Path

from analysis.config_loader import load_shared_config, to_ops_parameters
from analysis.generate_briefing import main as briefing_main
from analysis.reporting import render_html, render_markdown, write_briefing
from analysis.scenario_explorer import explore, load_sweep_config

ROOT = Path(__file__).resolve().parents[1]


def test_write_briefing_html_and_markdown(tmp_path):
    params = to_ops_parameters(load_shared_config(ROOT / "fixtures" / "baseline.yaml"))
    cfg = load_sweep_config(ROOT / "fixtures" / "sweep_briefing.yaml", repo_root=ROOT)
    cfg.base = params
    rows = explore(cfg)
    html_path = tmp_path / "briefing.html"
    md_path = tmp_path / "briefing.md"
    ctx = write_briefing(
        params,
        html_path=html_path,
        markdown_path=md_path,
        sweep_rows=rows,
        sweep_cfg=cfg,
    )
    html = html_path.read_text(encoding="utf-8")
    md = md_path.read_text(encoding="utf-8")
    assert "Primary constraint" in html or "Bottleneck" in html
    assert "chart.js" in html.lower()
    assert ctx["result"]["bottleneck"]
    assert "Executive snapshot" in md
    assert "Preferred scenarios" in md


def test_fragment_mode():
    params = to_ops_parameters(load_shared_config(ROOT / "fixtures" / "baseline.yaml"))
    from analysis.reporting import build_briefing_context

    ctx = build_briefing_context(params)
    frag = render_html(ctx, fragment=True)
    assert "msd-briefing-fragment" in frag
    assert "<!DOCTYPE html>" not in frag
    assert "MSD Ops Capacity" in render_markdown(ctx)


def test_generate_briefing_cli(tmp_path, monkeypatch):
    import sys

    out = tmp_path / "briefing.html"
    md = tmp_path / "briefing.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_briefing",
            "--config",
            str(ROOT / "fixtures" / "baseline.yaml"),
            "--sweep",
            str(ROOT / "fixtures" / "sweep_briefing.yaml"),
            "-o",
            str(out),
            "--markdown",
            str(md),
        ],
    )
    # Run from repo root for relative fixture resolution inside modules
    monkeypatch.chdir(ROOT)
    assert briefing_main() == 0
    assert out.exists() and md.exists()
    assert "constraintChart" in out.read_text(encoding="utf-8")
