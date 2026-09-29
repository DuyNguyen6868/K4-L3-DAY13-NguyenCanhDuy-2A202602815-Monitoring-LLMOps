from __future__ import annotations

import json
from pathlib import Path

import structlog

from app import logging_config
from scripts.validate_logs import PII_DETECTORS


def log_to(monkeypatch, tmp_path: Path) -> Path:
    path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", path)
    logging_config.configure_logging()
    return path


def test_every_string_field_is_scrubbed_before_writing(monkeypatch, tmp_path: Path) -> None:
    log_path = log_to(monkeypatch, tmp_path)

    logging_config.get_logger().info(
        "request_received",
        service="api",
        session_id="student@vinuni.edu.vn",
        payload={
            "message_preview": "Call me at 0987654321",
            "nested": {"cards": ["4111 1111 1111 1111"], "cccd": "012345678901"},
        },
    )

    line = log_path.read_text(encoding="utf-8").strip()
    assert [name for name, detector in PII_DETECTORS.items() if detector.search(line)] == []
    record = json.loads(line)
    assert record["session_id"] == "[REDACTED_EMAIL]"
    assert record["payload"]["message_preview"] == "Call me at [REDACTED_PHONE_VN]"
    assert record["payload"]["nested"] == {
        "cards": ["[REDACTED_CREDIT_CARD]"],
        "cccd": "[REDACTED_CCCD]",
    }


def test_exception_traceback_is_scrubbed(monkeypatch, tmp_path: Path) -> None:
    log_path = log_to(monkeypatch, tmp_path)

    try:
        raise RuntimeError("vector store rejected student@vinuni.edu.vn")
    except RuntimeError:
        logging_config.get_logger().exception("request_failed", service="api")

    line = log_path.read_text(encoding="utf-8").strip()
    assert "student@vinuni.edu.vn" not in line
    assert "[REDACTED_EMAIL]" in json.loads(line)["exception"]


def test_scrub_runs_after_traceback_and_before_writer_and_renderer() -> None:
    logging_config.configure_logging()
    processors = structlog.get_config()["processors"]

    def position(matches) -> int:
        return next(i for i, processor in enumerate(processors) if matches(processor))

    traceback_at = position(lambda p: p is structlog.processors.format_exc_info)
    scrub_at = position(lambda p: p is logging_config.scrub_event)
    writer_at = position(lambda p: isinstance(p, logging_config.JsonlFileProcessor))
    renderer_at = position(lambda p: isinstance(p, structlog.processors.JSONRenderer))
    assert traceback_at < scrub_at < writer_at < renderer_at
