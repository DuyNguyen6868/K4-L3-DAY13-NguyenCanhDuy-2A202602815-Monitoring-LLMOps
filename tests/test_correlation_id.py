from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

import httpx
import pytest
from structlog.contextvars import bind_contextvars

from app import logging_config
from app.main import agent, app
from app.pii import hash_user_id

ID_FORMAT = re.compile(r"req-[0-9a-f]{8}")


@pytest.fixture
def log_path(monkeypatch, tmp_path: Path) -> Path:
    path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", path)
    return path


def read_logs(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def send_chats(
    *calls: tuple[str, dict[str, str]], stale_context: dict[str, str] | None = None
) -> list[httpx.Response]:
    """Send (user_id, headers) chats one after another in a single asyncio task.

    ASGITransport runs the app in the caller's task, so all requests share one
    context, like a long-lived worker handling request after request.
    """

    async def scenario() -> list[httpx.Response]:
        if stale_context:
            bind_contextvars(**stale_context)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return [
                await client.post(
                    "/chat",
                    headers=headers,
                    json={
                        "user_id": user_id,
                        "session_id": f"session-{user_id}",
                        "feature": "qa",
                        "message": "Explain observability",
                    },
                )
                for user_id, headers in calls
            ]

    return asyncio.run(scenario())


def test_valid_request_id_is_kept_in_headers_body_and_logs(log_path: Path) -> None:
    (response,) = send_chats(("student-01", {"x-request-id": "req-0000abcd"}))

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-0000abcd"
    assert response.json()["correlation_id"] == "req-0000abcd"
    assert float(response.headers["x-response-time-ms"]) >= 0

    records = read_logs(log_path)
    assert [r["event"] for r in records] == ["request_received", "response_sent"]
    for record in records:
        assert record["correlation_id"] == "req-0000abcd"
        assert record["user_id_hash"] == hash_user_id("student-01")
        assert record["session_id"] == "session-student-01"
        assert record["feature"] == "qa"
        assert record["model"] == agent.model
        assert record["env"] == os.getenv("APP_ENV", "dev")


@pytest.mark.parametrize(
    "incoming",
    [None, "hello", "req-0000ABCD", "req-0000abcd-extra", "student@vinuni.edu.vn"],
)
def test_missing_or_malformed_request_id_is_replaced(
    log_path: Path, incoming: str | None
) -> None:
    headers = {"x-request-id": incoming} if incoming else {}
    (response,) = send_chats(("student-01", headers))

    correlation_id = response.headers["x-request-id"]
    assert ID_FORMAT.fullmatch(correlation_id)
    assert correlation_id != incoming
    assert response.json()["correlation_id"] == correlation_id
    assert {r["correlation_id"] for r in read_logs(log_path)} == {correlation_id}


def test_generated_ids_differ_between_requests(log_path: Path) -> None:
    first, second = send_chats(("student-01", {}), ("student-01", {}))

    assert first.headers["x-request-id"] != second.headers["x-request-id"]


def test_context_does_not_leak_between_requests(log_path: Path) -> None:
    first, second = send_chats(
        ("student-01", {}),
        ("student-02", {}),
        stale_context={"leaked_field": "left-by-an-earlier-request"},
    )

    records = read_logs(log_path)
    assert len(records) == 4
    assert all("leaked_field" not in record for record in records)
    user_by_id = {
        first.headers["x-request-id"]: "student-01",
        second.headers["x-request-id"]: "student-02",
    }
    for record in records:
        assert record["user_id_hash"] == hash_user_id(user_by_id[record["correlation_id"]])
