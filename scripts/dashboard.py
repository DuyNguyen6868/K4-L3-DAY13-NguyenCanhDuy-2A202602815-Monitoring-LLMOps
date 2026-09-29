from __future__ import annotations

import argparse
import html
import json
import math
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

LOCAL_TZ = timezone(timedelta(hours=7), "Asia/Ho_Chi_Minh")


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def percentile(values: list[float], percent: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(percent / 100 * len(ordered)))
    return float(ordered[rank - 1])


def _numeric_values(records: list[dict], field: str) -> list[float]:
    return [
        float(record[field])
        for record in records
        if isinstance(record.get(field), (int, float))
        and not isinstance(record.get(field), bool)
    ]


def build_dashboard_data(
    log_path: Path,
    config_path: Path,
    now: datetime | None = None,
) -> dict:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    dashboard = payload["dashboard"]
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_utc = now_utc.astimezone(timezone.utc)
    window_minutes = dashboard["time_range_minutes"]
    start_utc = now_utc - timedelta(minutes=window_minutes)

    records = []
    for record in load_records(log_path):
        timestamp = parse_timestamp(record.get("ts"))
        if timestamp is not None and start_utc <= timestamp < now_utc:
            records.append((timestamp, record))

    request_records = [record for _, record in records if record.get("event") == "request_received"]
    response_records = [record for _, record in records if record.get("event") == "response_sent"]
    failed_records = [record for _, record in records if record.get("event") == "request_failed"]
    tool_records = [
        record
        for _, record in records
        if isinstance(record.get("tool_success"), bool)
    ]
    latencies = _numeric_values(response_records, "latency_ms")
    ttft_values = _numeric_values(response_records, "ttft_ms")
    costs = _numeric_values(response_records, "cost_usd")
    tokens_in = _numeric_values(response_records, "tokens_in")
    tokens_out = _numeric_values(response_records, "tokens_out")
    quality = _numeric_values(response_records, "quality_score")

    first_minute = start_utc.replace(second=0, microsecond=0)
    minute_starts = [first_minute + timedelta(minutes=index) for index in range(window_minutes + 1)]
    minute_labels = [moment.astimezone(LOCAL_TZ).strftime("%H:%M") for moment in minute_starts]
    request_counts: Counter[datetime] = Counter()
    minute_costs: Counter[datetime] = Counter()
    for timestamp, record in records:
        minute = timestamp.replace(second=0, microsecond=0)
        if record.get("event") == "request_received":
            request_counts[minute] += 1
        elif record.get("event") == "response_sent" and isinstance(record.get("cost_usd"), (int, float)):
            minute_costs[minute] += float(record["cost_usd"])

    minute_keys = [moment.replace(second=0, microsecond=0) for moment in minute_starts]
    cumulative_costs = []
    cumulative_cost = 0.0
    for key in minute_keys:
        cumulative_cost += minute_costs[key]
        cumulative_costs.append(round(cumulative_cost, 6))
    error_rate = 100 * len(failed_records) / len(request_records) if request_records else 0.0
    retrieval_success = (
        100 * sum(record["tool_success"] is True for record in tool_records) / len(tool_records)
        if tool_records
        else 0.0
    )

    stats = {
        "request_count": len(request_records),
        "failure_count": len(failed_records),
        "error_rate_pct": error_rate,
        "retrieval_success_pct": retrieval_success,
        "latency_p50": percentile(latencies, 50),
        "latency_p95": percentile(latencies, 95),
        "latency_p99": percentile(latencies, 99),
        "ttft_p95": percentile(ttft_values, 95),
        "cost_total_usd": sum(costs),
        "tokens_in_total": sum(tokens_in),
        "tokens_out_total": sum(tokens_out),
        "quality_avg": sum(quality) / len(quality) if quality else 0.0,
        "tool_success_count": sum(record["tool_success"] is True for record in tool_records),
        "tool_result_count": len(tool_records),
        "error_breakdown": dict(Counter(
            str(record.get("error_type", "unknown")) for record in failed_records
        )),
    }
    panel_data = {
        "latency": {
            "labels": ["P50", "P95", "P99", "TTFT P95"],
            "values": [stats["latency_p50"], stats["latency_p95"], stats["latency_p99"], stats["ttft_p95"]],
        },
        "traffic": {
            "labels": minute_labels,
            "values": [request_counts[key] for key in minute_keys],
        },
        "errors": {
            "labels": ["Error rate", "Retrieval success"],
            "values": [error_rate, retrieval_success],
            "error_breakdown": stats["error_breakdown"],
        },
        "cost": {
            "labels": minute_labels,
            "values": cumulative_costs,
        },
        "tokens": {
            "labels": ["Input", "Output"],
            "values": [stats["tokens_in_total"], stats["tokens_out_total"]],
        },
        "quality": {"labels": ["Mean quality"], "values": [stats["quality_avg"]]},
    }
    return {
        "title": dashboard["title"],
        "window_minutes": window_minutes,
        "refresh_seconds": dashboard["refresh_seconds"],
        "generated_at": now_utc.astimezone(LOCAL_TZ).isoformat(timespec="seconds"),
        "window_start": start_utc.astimezone(LOCAL_TZ).isoformat(timespec="minutes"),
        "window_end": now_utc.astimezone(LOCAL_TZ).isoformat(timespec="minutes"),
        "stats": stats,
        "panels": [
            {
                "id": panel["id"],
                "title": panel["title"],
                "unit": panel["unit"],
                "threshold": panel["threshold"],
                "data": panel_data[panel["id"]],
            }
            for panel in dashboard["panels"]
        ],
    }


def build_dashboard_html(data: dict) -> str:
    panels_markup = "\n".join(
        f'<section class="panel" data-panel="{html.escape(panel["id"])}">'
        f'<div class="panel-head"><h2>{html.escape(panel["title"])}</h2>'
        f'<span class="unit">{html.escape(panel["unit"])}</span></div>'
        f'<div class="summary" id="summary-{html.escape(panel["id"])}"></div>'
        f'<div class="chart-box"><canvas id="chart-{html.escape(panel["id"])}" aria-label="{html.escape(panel["title"])}"></canvas></div>'
        f'<div class="detail" id="detail-{html.escape(panel["id"])}"></div></section>'
        for panel in data["panels"]
    )
    encoded_data = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="{int(data["refresh_seconds"])}">
  <title>{html.escape(data["title"])}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {{ color-scheme: light; --ink: #172a3a; --muted: #627384; --line: #d9e2e8; --paper: #f5f8f8; --green: #167c68; --blue: #3478a5; --orange: #d97832; --red: #c64d4d; --teal: #168f9a; --gold: #b78a22; }}
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; }}
    body {{ margin: 0; display: flex; flex-direction: column; background: var(--paper); color: var(--ink); font: 14px/1.45 "Segoe UI", sans-serif; }}
    header {{ flex: none; padding: 14px 24px 12px; background: #fff; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; gap: 16px; align-items: end; }}
    h1 {{ margin: 0; font-size: 20px; font-weight: 650; }}
    .stamp {{ color: var(--muted); text-align: right; font-size: 12px; }}
    main {{ flex: 1; min-height: 0; width: 100%; max-width: 1680px; margin: 0 auto; padding: 14px 20px 18px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); grid-template-rows: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .panel {{ display: flex; flex-direction: column; min-width: 0; min-height: 0; background: #fff; border: 1px solid var(--line); border-radius: 6px; padding: 13px 16px 11px; box-shadow: 0 2px 8px #17354a0a; }}
    .panel-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 10px; }}
    h2 {{ margin: 0 0 6px; font-size: 15px; font-weight: 650; }}
    .unit {{ color: var(--muted); font-size: 11px; white-space: nowrap; }}
    .summary {{ min-height: 23px; margin-bottom: 6px; color: var(--green); font-size: 13px; font-weight: 600; }}
    /* Chart.js with maintainAspectRatio: false fills its parent, so the parent holds only the
       canvas and takes its size from the layout. Sized by the panel instead, every resize made
       the panel taller and the page grew without end. */
    .chart-box {{ position: relative; flex: 1 1 0; min-height: 0; }}
    .chart-box canvas {{ position: absolute; left: 0; top: 0; }}
    .detail {{ min-height: 18px; padding-top: 5px; color: var(--muted); font-size: 11px; }}
    @media (max-width: 1100px), (max-height: 620px) {{ html, body {{ height: auto; }} main {{ grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-rows: none; }} .chart-box {{ flex: none; height: 200px; }} }}
    @media (max-width: 760px) {{ header {{ align-items: start; flex-direction: column; }} .stamp {{ text-align: left; }} main {{ grid-template-columns: 1fr; padding: 12px; }} .chart-box {{ height: 180px; }} }}
  </style>
</head>
<body>
  <header><h1>{html.escape(data["title"])}</h1><div class="stamp">Last {data["window_minutes"]} minutes · Asia/Ho_Chi_Minh<br>{html.escape(data["window_start"])} to {html.escape(data["window_end"])} · Updated {html.escape(data["generated_at"])}</div></header>
  <main>{panels_markup}</main>
  <script>
    const snapshot = {encoded_data};
    const colors = {{ latency: '#3478a5', traffic: '#167c68', errors: '#c64d4d', cost: '#d97832', tokens: '#168f9a', quality: '#b78a22' }};
    const fmt = (value, digits = 1) => Number(value || 0).toLocaleString(undefined, {{ maximumFractionDigits: digits }});
    for (const panel of snapshot.panels) {{
      const values = panel.data.values;
      const threshold = panel.threshold.value;
      let summary = '';
      let details = `Threshold ${{panel.threshold.operator}} ${{fmt(threshold)}} ${{panel.unit}}`;
      let datasets;
      let options = {{ responsive: true, maintainAspectRatio: false, animation: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, grid: {{ color: '#edf1f3' }} }}, x: {{ grid: {{ display: false }} }} }} }};
      if (panel.id === 'latency') {{
        summary = `P50 ${{fmt(values[0], 0)}} · P95 ${{fmt(values[1], 0)}} · P99 ${{fmt(values[2], 0)}} · TTFT P95 ${{fmt(values[3], 0)}} ms`;
        datasets = [{{ type: 'bar', label: 'Latency', data: values, backgroundColor: ['#85b9d3', '#3478a5', '#c64d4d', '#65a59e'], borderRadius: 3 }}, {{ type: 'line', label: 'P95 threshold', data: values.map(() => threshold), borderColor: '#d97832', borderDash: [6, 4], pointRadius: 0 }}];
      }} else if (panel.id === 'traffic') {{
        const total = values.reduce((sum, value) => sum + value, 0);
        summary = `${{fmt(total, 0)}} requests · peak ${{fmt(Math.max(0, ...values), 0)}}/min`;
        datasets = [{{ label: 'Requests/min', data: values, borderColor: colors.traffic, backgroundColor: '#167c6824', fill: true, tension: .22, pointRadius: 0 }}];
        datasets.push({{ label: 'Minimum rate', data: values.map(() => threshold), borderColor: '#d97832', borderDash: [6, 4], pointRadius: 0 }});
      }} else if (panel.id === 'errors') {{
        summary = `Error ${{fmt(values[0])}}% · Retrieval success ${{fmt(values[1])}}%`;
        details = `Threshold: error rate ≤ ${{fmt(threshold)}}% · Results: ${{panel.data.error_breakdown ? Object.entries(panel.data.error_breakdown).map(([name, count]) => `${{name}} ${{count}}`).join(' · ') || 'no errors' : 'no errors' }}`;
                datasets = [{{ type: 'bar', label: 'Rate', data: values, backgroundColor: ['#c64d4d', '#167c68'], borderRadius: 3 }}, {{ type: 'line', label: 'Error threshold', data: values.map(() => threshold), borderColor: '#d97832', borderDash: [6, 4], pointRadius: 0 }}];
        options.scales.y.max = 100;
      }} else if (panel.id === 'cost') {{
                summary = `Window total $${{fmt(snapshot.stats.cost_total_usd, 4)}}`;
                datasets = [{{ label: 'Cumulative USD', data: values, borderColor: colors.cost, backgroundColor: '#d9783226', fill: true, tension: .2, pointRadius: 0 }}];
        datasets.push({{ label: 'Budget threshold', data: values.map(() => threshold), borderColor: '#c64d4d', borderDash: [6, 4], pointRadius: 0 }});
      }} else if (panel.id === 'tokens') {{
        summary = `Input ${{fmt(values[0], 0)}} · Output ${{fmt(values[1], 0)}} tokens`;
                datasets = [{{ type: 'bar', label: 'Tokens', data: values, backgroundColor: ['#3478a5', '#168f9a'], borderRadius: 3 }}, {{ type: 'line', label: 'Token threshold', data: values.map(() => threshold), borderColor: '#d97832', borderDash: [6, 4], pointRadius: 0 }}];
      }} else {{
        summary = `Mean quality ${{fmt(values[0], 2)}} / 1.00`;
        datasets = [{{ type: 'bar', label: 'Quality', data: values, backgroundColor: colors.quality, borderRadius: 3 }}, {{ type: 'line', label: 'Quality threshold', data: values.map(() => threshold), borderColor: '#167c68', borderDash: [6, 4], pointRadius: 0 }}];
        options.scales.y.max = 1;
      }}
      document.getElementById(`summary-${{panel.id}}`).textContent = summary;
      document.getElementById(`detail-${{panel.id}}`).textContent = details;
      new Chart(document.getElementById(`chart-${{panel.id}}`), {{ type: 'line', data: {{ labels: panel.data.labels, datasets }}, options }});
    }}
  </script>
</body>
</html>
'''


def write_dashboard(log_path: Path, config_path: Path, output_path: Path) -> dict:
    data = build_dashboard_data(log_path, config_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(build_dashboard_html(data), encoding="utf-8")
    temporary_path.replace(output_path)
    return data


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Generate the Day 13 local observability dashboard")
    parser.add_argument("--logs", type=Path, default=REPO_ROOT / "data" / "logs.jsonl")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "config" / "dashboard.yaml")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "data" / "dashboard.html")
    parser.add_argument("--watch", action="store_true", help="Regenerate the HTML at the configured refresh interval")
    args = parser.parse_args()

    while True:
        try:
            data = write_dashboard(args.logs, args.config, args.output)
        except (OSError, KeyError, TypeError, yaml.YAMLError) as exc:
            print(f"Dashboard generation failed: {exc}", file=sys.stderr)
            return 1
        print(
            f"Updated {args.output} | {data['stats']['request_count']} requests | "
            f"{data['window_minutes']}m window | {data['generated_at']}"
        )
        if not args.watch:
            return 0
        try:
            time.sleep(data["refresh_seconds"])
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())