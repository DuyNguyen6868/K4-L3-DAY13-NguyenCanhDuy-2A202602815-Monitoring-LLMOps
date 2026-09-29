from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_alerts_have_complete_symptom_contract_and_runbooks() -> None:
    payload = yaml.safe_load((REPO_ROOT / "config" / "alert_rules.yaml").read_text(encoding="utf-8"))
    alerts = payload["alerts"]
    assert len(alerts) == 3

    for index, alert in enumerate(alerts, start=1):
        assert alert["name"]
        assert alert["severity"] in {"P1", "P2", "P3"}
        assert alert["condition"]
        assert alert["duration"]
        assert alert["type"] == "symptom-based"
        assert alert["channel"] == "slack"
        assert alert["slack_channel"].startswith("#")
        assert alert["owner"]
        assert alert["runbook"] == f"docs/alerts.md#alert-{index}"

    serialized = (REPO_ROOT / "config" / "alert_rules.yaml").read_text(encoding="utf-8")
    assert "TODO" not in serialized

    runbook = (REPO_ROOT / "docs" / "alerts.md").read_text(encoding="utf-8")
    assert all(f"## Alert {index}" in runbook for index in range(1, 4))
    assert all(section in runbook for section in ("Kiểm tra:", "Mitigation:"))


def test_latency_alert_tracks_provisional_slo_not_dashboard_contract() -> None:
    alerts = yaml.safe_load((REPO_ROOT / "config" / "alert_rules.yaml").read_text(encoding="utf-8"))["alerts"]
    slo = yaml.safe_load((REPO_ROOT / "config" / "slo.yaml").read_text(encoding="utf-8"))["primary_slo"]
    dashboard = yaml.safe_load((REPO_ROOT / "config" / "dashboard.yaml").read_text(encoding="utf-8"))["dashboard"]

    assert "2000 ms" in alerts[0]["condition"]
    assert "2000" in slo["sli"]["good_event"]
    latency_panel = next(panel for panel in dashboard["panels"] if panel["id"] == "latency")
    assert latency_panel["threshold"]["value"] == 3000