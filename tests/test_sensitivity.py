"""Sensitivity CSV export tests."""

import csv
import io
from pathlib import Path

from analysis.config_loader import load_shared_config, to_ops_parameters
from analysis.sensitivity import CSV_COLUMNS, iter_sensitivity_rows, write_csv

ROOT = Path(__file__).resolve().parents[1]


def test_sensitivity_rows_have_expected_columns():
    base = to_ops_parameters(load_shared_config(ROOT / "fixtures" / "baseline.yaml"))
    rows = iter_sensitivity_rows(
        base,
        offload_range=range(1, 3),
        loading_range=range(1, 3),
        pool_range=range(20, 21),
        missions_values=[3.0],
    )
    assert len(rows) == 4
    assert set(rows[0].keys()) == set(CSV_COLUMNS)


def test_write_csv_header_and_rows():
    base = to_ops_parameters(load_shared_config(ROOT / "fixtures" / "baseline.yaml"))
    rows = iter_sensitivity_rows(
        base,
        offload_range=range(1, 2),
        loading_range=range(2, 3),
        pool_range=range(20, 21),
        missions_values=[3.0],
    )
    buf = io.StringIO()
    write_csv(rows, buf)
    parsed = list(csv.DictReader(io.StringIO(buf.getvalue())))
    assert len(parsed) == 1
    assert parsed[0]["bottleneck"] in ("balanced", "loading", "offload", "devices")


def test_sensitivity_cli_writes_file(tmp_path):
    import subprocess
    import sys

    out = tmp_path / "sweep.csv"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "analysis.sensitivity",
            "--config",
            str(ROOT / "fixtures" / "baseline.yaml"),
            "--mode",
            "stations",
            "-o",
            str(out),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert out.exists()
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 31  # 6 offload × 5 loading + header
