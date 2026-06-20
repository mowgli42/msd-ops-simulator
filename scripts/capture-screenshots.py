#!/usr/bin/env python3
"""Capture MSD Ops Simulator screenshots for docs/WALKTHROUGH.md."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)
INDEX = ROOT / "index.html"


def capture_with_playwright() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(INDEX.as_uri(), wait_until="networkidle")

        # Initial state
        page.screenshot(path=str(OUT / "01-initial-config.png"))

        # Start simulation
        page.click("#play-btn")
        page.wait_for_timeout(2500)
        page.screenshot(path=str(OUT / "02-running-steady-state.png"))

        # Stress: more vehicles, fewer offload stations
        page.click("#play-btn")  # pause
        page.fill("#vehicles", "12")
        page.fill("#offload-stations", "1")
        page.dispatch_event("#vehicles", "input")
        page.dispatch_event("#offload-stations", "input")
        page.evaluate("updateConfig(); resetSimulation();")
        page.click("#play-btn")
        page.wait_for_timeout(3500)
        page.screenshot(path=str(OUT / "03-offload-bottleneck.png"))

        browser.close()
    return True


def capture_cli_fallback() -> None:
    """Render analysis CLI output as PNG via minimal HTML if Playwright missing."""
    r = subprocess.run(
        [sys.executable, "-m", "analysis.capacity_model"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    text = (r.stdout or r.stderr or "analysis unavailable").strip()
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"/>
<style>body{{background:#0f172a;color:#e2e8f0;font-family:monospace;padding:24px;font-size:13px}}
pre{{white-space:pre-wrap}}</style></head><body><pre>{text}</pre></body></html>"""
    path = OUT / "_cli.html"
    path.write_text(html, encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 900, "height": 500})
            page.goto(path.as_uri())
            page.screenshot(path=str(OUT / "04-capacity-analysis-cli.png"))
            browser.close()
    finally:
        path.unlink(missing_ok=True)


def main() -> int:
    if not INDEX.exists():
        print(f"Missing {INDEX}", file=sys.stderr)
        return 1
    if not capture_with_playwright():
        print("Install: pip install playwright && python -m playwright install chromium", file=sys.stderr)
        return 1
    capture_cli_fallback()
    print(f"Wrote screenshots under {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
