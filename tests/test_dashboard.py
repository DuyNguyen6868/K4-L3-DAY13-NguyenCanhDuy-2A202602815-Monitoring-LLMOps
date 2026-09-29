from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.dashboard import build_dashboard_data, build_dashboard_html


def write_log(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_dashboard_aggregates_six_panels_from_recent_logs_without_emitting_payload(
    tmp_path: Path,
) -> None:
    logs = tmp_path / "logs.jsonl"
    now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    for record in (
        {"ts": "2026-09-29T11:58:00Z", "event": "request_received"},
        {
            "ts": "2026-09-29T11:58:01Z",
            "event": "response_sent",
            "latency_ms": 100,
            "ttft_ms": 30,
            "cost_usd": 0.001,
            "tokens_in": 10,
            "tokens_out": 15,
            "quality_score": 0.8,
            "tool_name": "retrieval",
            "tool_success": True,
            "payload": {"answer_preview": "private@example.com"},
        },
        {"ts": "2026-09-29T11:59:00Z", "event": "request_received"},
        {
            "ts": "2026-09-29T11:59:02Z",
            "event": "response_sent",
            "latency_ms": 800,
            "ttft_ms": 50,
            "cost_usd": 0.003,
            "tokens_in": 25,
            "tokens_out": 10,
            "quality_score": 0.6,
            "tool_name": "retrieval",
            "tool_success": True,
        },
        {"ts": "2026-09-29T11:59:30Z", "event": "request_received"},
        {
            "ts": "2026-09-29T11:59:31Z",
            "event": "request_failed",
            "error_type": "RuntimeError",
            "tool_name": "retrieval",
            "tool_success": False,
        },
        {"ts": "2026-09-29T10:59:00Z", "event": "request_received"},
    ):
        write_log(logs, record)

    data = build_dashboard_data(logs, Path("config/dashboard.yaml"), now=now)

    assert [panel["id"] for panel in data["panels"]] == [
        "latency", "traffic", "errors", "cost", "tokens", "quality"
    ]
    assert data["stats"]["request_count"] == 3
    assert data["stats"]["latency_p50"] == 100
    assert data["stats"]["latency_p95"] == 800
    assert data["stats"]["ttft_p95"] == 50
    assert data["stats"]["error_rate_pct"] == 100 / 3
    assert data["stats"]["retrieval_success_pct"] == 200 / 3
    assert data["stats"]["cost_total_usd"] == 0.004
    assert data["stats"]["tokens_in_total"] == 35
    assert data["stats"]["tokens_out_total"] == 25
    assert data["stats"]["quality_avg"] == 0.7
    assert len(next(panel for panel in data["panels"] if panel["id"] == "traffic")["data"]["labels"]) == 61

    rendered = build_dashboard_html(data)
    assert rendered.count('data-panel="') == 6
    assert 'content="30"' in rendered
    assert "private@example.com" not in rendered
    assert "Last 60 minutes" in rendered


def test_each_chart_gets_a_container_of_its_own(tmp_path: Path) -> None:
    # A canvas sharing its parent with the panel text made Chart.js grow the page forever.
    data = build_dashboard_data(tmp_path / "missing.jsonl", Path("config/dashboard.yaml"))

    rendered = build_dashboard_html(data)

    assert rendered.count('<div class="chart-box"><canvas id="chart-') == 6


def test_dashboard_handles_missing_logs_and_invalid_json(tmp_path: Path) -> None:
    logs = tmp_path / "logs.jsonl"
    logs.write_text("not json\n", encoding="utf-8")

    data = build_dashboard_data(logs, Path("config/dashboard.yaml"))

    assert data["stats"]["request_count"] == 0
    assert data["stats"]["latency_p95"] == 0
    assert data["stats"]["quality_avg"] == 0