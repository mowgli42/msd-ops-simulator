"""Briefing-quality HTML and Markdown report generation.

Produces self-contained artifacts for technical discussions and leadership
updates. Charts use Chart.js from CDN (works offline if the CDN is cached;
for fully air-gapped use, pass --embed-charts false and print tables only).
"""

from __future__ import annotations

import argparse
import html
import json
import math
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analysis.capacity_model import OpsParameters, analyze, format_summary, max_sustainable_vehicles
from analysis.config_loader import load_shared_config, to_ops_parameters
from analysis.scenario_explorer import ScenarioRow, SweepConfig, explore, load_sweep_config, preferred_summary


def _finite(x: float, default: float = 0.0) -> float:
    return float(x) if isinstance(x, (int, float)) and math.isfinite(x) else default


def _esc(s: object) -> str:
    return html.escape(str(s))


def build_briefing_context(
    params: OpsParameters,
    *,
    sweep_rows: list[ScenarioRow] | None = None,
    sweep_cfg: SweepConfig | None = None,
    title: str = "MSD Ops Capacity Briefing",
) -> dict[str, Any]:
    result = analyze(params)
    fleet = max_sustainable_vehicles(params)
    feasible = [r for r in (sweep_rows or []) if r.feasible]
    pareto = [r for r in feasible if r.pareto]
    top = feasible[: (sweep_cfg.top_n if sweep_cfg else 8)]

    constraint_map = result.constraint_utilizations or {}
    return {
        "title": title,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "params": asdict(params),
        "result": asdict(result),
        "fleet": asdict(fleet),
        "text_summary": format_summary(params, result),
        "constraint_labels": list(constraint_map.keys()),
        "constraint_values": [_finite(constraint_map[k]) for k in constraint_map],
        "sweep_id": sweep_cfg.scenario_id if sweep_cfg else None,
        "sweep_description": sweep_cfg.description if sweep_cfg else "",
        "evaluated": len(sweep_rows or []),
        "feasible_count": len(feasible),
        "pareto_count": len(pareto),
        "top_scenarios": [r.to_dict() for r in top],
        "pareto_scenarios": [r.to_dict() for r in pareto],
        "preferred_text": preferred_summary(sweep_rows or [], top_n=sweep_cfg.top_n if sweep_cfg else 8)
        if sweep_rows
        else "",
    }


def render_markdown(ctx: dict[str, Any]) -> str:
    p, r, f = ctx["params"], ctx["result"], ctx["fleet"]
    lines = [
        f"# {ctx['title']}",
        "",
        f"_Generated {ctx['generated_at']}_",
        "",
        "## Executive snapshot",
        "",
        f"- **Primary constraint:** `{r['bottleneck']}`",
        f"- **Arrival rate:** {r['arrival_rate_per_hour']} devices/hour",
        f"- **Loading / offload utilization:** {r['loading_utilization']} / {r['offload_utilization']}",
        f"- **Devices recommended vs pool:** {r['devices_recommended']} / {p['device_pool']}",
        f"- **Max vehicles (stable / @{p['utilization_target']:.0%}):** "
        f"{f['max_vehicles_stable']} / {f['max_vehicles_at_target']}",
        "",
        "## Configuration",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
    ]
    for key in (
        "vehicles",
        "missions_per_vehicle_per_day",
        "mission_duration_hours",
        "load_time_hours",
        "offload_time_hours",
        "install_time_hours",
        "sanitize_time_hours",
        "loading_stations",
        "offload_stations",
        "device_pool",
        "ports_per_vehicle",
        "devices_per_mission",
        "min_devices_per_vehicle",
        "preload_all_ports",
        "high_data_volume_mode",
        "utilization_target",
    ):
        lines.append(f"| `{key}` | {p[key]} |")

    lines += [
        "",
        "## Workflow constraints",
        "",
        "| Resource | Utilization |",
        "|----------|-------------|",
    ]
    for k, v in (r.get("constraint_utilizations") or {}).items():
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "## Capacity narrative",
        "",
        "```",
        ctx["text_summary"],
        "```",
        "",
    ]

    if ctx.get("top_scenarios"):
        lines += [
            "## Preferred scenarios (from sweep)",
            "",
            ctx.get("sweep_description") or "",
            "",
            f"Evaluated {ctx['evaluated']} combinations; "
            f"{ctx['feasible_count']} feasible; {ctx['pareto_count']} on Pareto front.",
            "",
            "| Rank | L | O | Pool | ρL | ρO | Wq offload | Bottleneck | Score | Pareto |",
            "|------|---|---|------|----|----|------------|------------|-------|--------|",
        ]
        for i, s in enumerate(ctx["top_scenarios"], 1):
            lines.append(
                f"| {i} | {s['loading_stations']} | {s['offload_stations']} | {s['device_pool']} | "
                f"{s['loading_utilization']} | {s['offload_utilization']} | "
                f"{s['mean_offload_wait_hours']} | {s['bottleneck']} | {s['score']:.3f} | "
                f"{'yes' if s['pareto'] else ''} |"
            )
        lines.append("")
        lines.append(
            "_Update configuration by editing the base YAML / sweep ranges and re-running "
            "`python -m analysis.generate_briefing`._"
        )
        lines.append("")

    lines += [
        "## How to refresh this briefing",
        "",
        "```bash",
        "python -m analysis.generate_briefing \\",
        "  --config fixtures/baseline.yaml \\",
        "  --sweep fixtures/sweep_briefing.yaml \\",
        "  -o output/briefing.html --markdown output/briefing.md",
        "```",
        "",
    ]
    return "\n".join(lines)


def render_html(ctx: dict[str, Any], *, fragment: bool = False) -> str:
    p, r, f = ctx["params"], ctx["result"], ctx["fleet"]
    bottleneck = r["bottleneck"]
    severity = "ok" if bottleneck == "balanced" else "warn"
    if bottleneck in ("loading", "offload") and (
        not r["loading_stable"] or not r["offload_stable"]
    ):
        severity = "critical"

    chart_payload = {
        "constraintLabels": ctx["constraint_labels"],
        "constraintValues": ctx["constraint_values"],
        "top": ctx.get("top_scenarios") or [],
        "utilizationTarget": p["utilization_target"],
    }

    cards = [
        ("Primary constraint", bottleneck.upper(), severity),
        ("Arrival λ", f"{r['arrival_rate_per_hour']} /h", "neutral"),
        ("ρ loading", str(r["loading_utilization"]), "neutral"),
        ("ρ offload", str(r["offload_utilization"]), "neutral"),
        ("Devices rec.", f"{r['devices_recommended']} / {p['device_pool']}", "neutral"),
        (
            "Max fleet @ target",
            str(f["max_vehicles_at_target"]),
            "neutral",
        ),
    ]

    cards_html = "".join(
        f'<div class="card {sev}"><div class="label">{_esc(lab)}</div>'
        f'<div class="value">{_esc(val)}</div></div>'
        for lab, val, sev in cards
    )

    config_rows = "".join(
        f"<tr><td><code>{_esc(k)}</code></td><td>{_esc(p[k])}</td></tr>"
        for k in (
            "vehicles",
            "missions_per_vehicle_per_day",
            "mission_duration_hours",
            "load_time_hours",
            "offload_time_hours",
            "install_time_hours",
            "sanitize_time_hours",
            "loading_stations",
            "offload_stations",
            "device_pool",
            "ports_per_vehicle",
            "devices_per_mission",
            "min_devices_per_vehicle",
            "preload_all_ports",
            "utilization_target",
        )
    )

    top_rows = ""
    for i, s in enumerate(ctx.get("top_scenarios") or [], 1):
        top_rows += (
            f"<tr><td>{i}</td><td>{s['loading_stations']}</td><td>{s['offload_stations']}</td>"
            f"<td>{s['device_pool']}</td><td>{s['loading_utilization']}</td>"
            f"<td>{s['offload_utilization']}</td><td>{s['mean_offload_wait_hours']}</td>"
            f"<td><span class='pill'>{_esc(s['bottleneck'])}</span></td>"
            f"<td>{s['score']:.3f}</td><td>{'●' if s['pareto'] else ''}</td></tr>"
        )
    if not top_rows:
        top_rows = "<tr><td colspan='10'>No sweep attached — pass --sweep to rank configurations.</td></tr>"

    body = f"""
<header class="hero">
  <p class="eyebrow">MSD Ops Simulator · Decision support</p>
  <h1>{_esc(ctx['title'])}</h1>
  <p class="sub">Generated {_esc(ctx['generated_at'])}. Edit YAML config / sweep ranges and regenerate to update.</p>
</header>

<section>
  <h2>Snapshot</h2>
  <div class="cards">{cards_html}</div>
  <div class="callout {severity}">
    <strong>Bottleneck callout:</strong>
    Primary constraint is <code>{_esc(bottleneck)}</code>.
    Vehicle tempo feasible={_esc(r['vehicle_tempo_feasible'])};
    ports feasible={_esc(r['ports_feasible'])};
    device reuse={_esc(r['device_reuse_rate'])};
    approx. mission-start delay={_esc(r['mission_start_delay_hours'])} h.
  </div>
</section>

<section class="grid-2">
  <div>
    <h2>Configuration</h2>
    <table>
      <thead><tr><th>Parameter</th><th>Value</th></tr></thead>
      <tbody>{config_rows}</tbody>
    </table>
  </div>
  <div>
    <h2>Constraint utilization</h2>
    <canvas id="constraintChart" height="220"></canvas>
  </div>
</section>

<section>
  <h2>Preferred scenarios</h2>
  <p class="muted">{_esc(ctx.get('sweep_description') or 'Attach a sweep YAML to populate ranked options.')}</p>
  <p class="muted">Evaluated {_esc(ctx['evaluated'])} · Feasible {_esc(ctx['feasible_count'])} · Pareto {_esc(ctx['pareto_count'])}</p>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>#</th><th>Load st.</th><th>Offload st.</th><th>Pool</th>
          <th>ρL</th><th>ρO</th><th>Wq offload</th><th>Bottleneck</th><th>Score</th><th>Pareto</th>
        </tr>
      </thead>
      <tbody>{top_rows}</tbody>
    </table>
  </div>
  <canvas id="tradeoffChart" height="200"></canvas>
</section>

<section>
  <h2>Capacity narrative</h2>
  <pre class="narrative">{_esc(ctx['text_summary'])}</pre>
</section>

<section>
  <h2>Refresh</h2>
  <pre class="narrative">python -m analysis.generate_briefing \\
  --config fixtures/baseline.yaml \\
  --sweep fixtures/sweep_briefing.yaml \\
  -o output/briefing.html --markdown output/briefing.md</pre>
</section>
"""

    script = f"""
const DATA = {json.dumps(chart_payload)};
(function() {{
  const ctxBar = document.getElementById('constraintChart');
  if (ctxBar && window.Chart) {{
    new Chart(ctxBar, {{
      type: 'bar',
      data: {{
        labels: DATA.constraintLabels,
        datasets: [
          {{
            label: 'Utilization',
            data: DATA.constraintValues,
            backgroundColor: DATA.constraintValues.map(v =>
              v >= 1 ? '#b33a3a' : (v >= DATA.utilizationTarget ? '#c9852a' : '#2f6f4e')),
          }},
          {{
            label: 'Target',
            data: DATA.constraintLabels.map(() => DATA.utilizationTarget),
            type: 'line',
            borderColor: '#1a1a1a',
            borderDash: [4, 4],
            pointRadius: 0,
            fill: false,
          }},
        ],
      }},
      options: {{
        responsive: true,
        plugins: {{ legend: {{ position: 'bottom' }} }},
        scales: {{ y: {{ beginAtZero: true, suggestedMax: 1.2 }} }},
      }},
    }});
  }}
  const ctxScatter = document.getElementById('tradeoffChart');
  if (ctxScatter && window.Chart && DATA.top.length) {{
    new Chart(ctxScatter, {{
      type: 'scatter',
      data: {{
        datasets: [{{
          label: 'Top scenarios (pool vs offload wait)',
          data: DATA.top.map(s => ({{
            x: s.device_pool,
            y: Number.isFinite(s.mean_offload_wait_hours) ? s.mean_offload_wait_hours : 0,
            label: `L${{s.loading_stations}}/O${{s.offload_stations}}`,
          }})),
          backgroundColor: '#1f4b7a',
          pointRadius: 6,
        }}],
      }},
      options: {{
        responsive: true,
        plugins: {{
          tooltip: {{
            callbacks: {{
              label: (c) => `${{c.raw.label}}: pool=${{c.raw.x}}, WqO=${{c.raw.y}}`,
            }},
          }},
          legend: {{ display: false }},
        }},
        scales: {{
          x: {{ title: {{ display: true, text: 'Device pool' }} }},
          y: {{ title: {{ display: true, text: 'Mean offload wait (h)' }}, beginAtZero: true }},
        }},
      }},
    }});
  }}
}})();
"""

    styles = """
:root {
  --bg: #f3efe6;
  --ink: #1c1a16;
  --muted: #5c564c;
  --panel: #fffdf8;
  --line: #d9d0c0;
  --ok: #2f6f4e;
  --warn: #c9852a;
  --critical: #b33a3a;
  --accent: #1f4b7a;
  --font-display: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  --font-body: "Source Sans 3", "Segoe UI", "Helvetica Neue", sans-serif;
  --font-mono: "IBM Plex Mono", "Consolas", monospace;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--ink);
  background:
    radial-gradient(ellipse at top left, rgba(31,75,122,0.08), transparent 40%),
    linear-gradient(180deg, #ebe4d6 0%, var(--bg) 40%, #e7e1d4 100%);
  font-family: var(--font-body);
  line-height: 1.45;
}
.page { max-width: 1080px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }
.hero { margin-bottom: 1.75rem; }
.eyebrow { text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.75rem; color: var(--accent); margin: 0 0 0.4rem; }
h1 { font-family: var(--font-display); font-size: clamp(1.8rem, 3vw, 2.4rem); margin: 0 0 0.4rem; }
h2 { font-family: var(--font-display); font-size: 1.35rem; margin: 0 0 0.75rem; }
.sub, .muted { color: var(--muted); }
section { background: var(--panel); border: 1px solid var(--line); padding: 1.1rem 1.2rem 1.3rem; margin-bottom: 1rem; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem; margin-bottom: 1rem; }
.card { border: 1px solid var(--line); padding: 0.7rem 0.8rem; background: #faf7f0; }
.card .label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
.card .value { font-family: var(--font-display); font-size: 1.25rem; margin-top: 0.2rem; }
.card.ok .value { color: var(--ok); }
.card.warn .value { color: var(--warn); }
.card.critical .value { color: var(--critical); }
.callout { padding: 0.75rem 0.9rem; border-left: 4px solid var(--accent); background: #f7f3ea; }
.callout.warn { border-left-color: var(--warn); }
.callout.critical { border-left-color: var(--critical); }
.callout.ok { border-left-color: var(--ok); }
.grid-2 { display: grid; grid-template-columns: 1.1fr 1fr; gap: 1rem; }
@media (max-width: 800px) { .grid-2 { grid-template-columns: 1fr; } }
table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
th, td { text-align: left; padding: 0.4rem 0.45rem; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
.table-wrap { overflow-x: auto; margin-bottom: 1rem; }
.pill { display: inline-block; padding: 0.1rem 0.4rem; background: #e8e0d2; font-size: 0.8rem; }
.narrative {
  white-space: pre-wrap;
  font-family: var(--font-mono);
  font-size: 0.82rem;
  background: #1c1a16;
  color: #f3efe6;
  padding: 1rem;
  overflow-x: auto;
}
code { font-family: var(--font-mono); font-size: 0.88em; }
"""

    if fragment:
        return f"<div class='msd-briefing-fragment'>\n<style>{styles}</style>\n{body}\n<script>{script}</script>\n</div>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(ctx['title'])}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>{styles}</style>
</head>
<body>
  <div class="page">
    {body}
  </div>
  <script>{script}</script>
</body>
</html>
"""


def write_briefing(
    params: OpsParameters,
    *,
    html_path: Path | None = None,
    markdown_path: Path | None = None,
    sweep_rows: list[ScenarioRow] | None = None,
    sweep_cfg: SweepConfig | None = None,
    title: str = "MSD Ops Capacity Briefing",
    fragment: bool = False,
) -> dict[str, Any]:
    ctx = build_briefing_context(params, sweep_rows=sweep_rows, sweep_cfg=sweep_cfg, title=title)
    if html_path:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(render_html(ctx, fragment=fragment), encoding="utf-8")
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown(ctx), encoding="utf-8")
    return ctx
