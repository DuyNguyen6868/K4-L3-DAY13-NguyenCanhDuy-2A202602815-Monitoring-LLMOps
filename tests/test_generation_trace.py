from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import agent as agent_module
from app.incidents import STATE


class LocalPromptClient:
    def get_prompt(self, name: str, **kwargs):
        raise AssertionError("prompt management is off in these tests")

    def update_current_span(self, **kwargs) -> None:
        return None


@pytest.fixture
def recorded(monkeypatch) -> dict[str, list[dict]]:
    calls: dict[str, list[dict]] = {"observation": [], "generation": []}
    monkeypatch.setattr(agent_module, "get_langfuse_client", LocalPromptClient)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: False)
    monkeypatch.setattr(
        agent_module, "update_current_observation", lambda **kwargs: calls["observation"].append(kwargs)
    )
    monkeypatch.setattr(
        agent_module, "update_current_generation", lambda **kwargs: calls["generation"].append(kwargs)
    )
    return calls


def run_agent(message: str):
    agent = agent_module.LabAgent()
    result = agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message=message,
        correlation_id="req-12345678",
    )
    return agent, result


def test_generation_reports_model_usage_cost_and_first_token_time(recorded) -> None:
    before = datetime.now(timezone.utc)
    agent, result = run_agent("Explain monitoring")
    after = datetime.now(timezone.utc)

    [generation] = recorded["generation"]
    assert generation["model"] == agent.model
    assert generation["usage_details"] == {"input": result.tokens_in, "output": result.tokens_out}
    # The trace must show the same cost as the log line and /metrics for this request.
    cost = generation["cost_details"]
    assert cost["total"] == result.cost_usd
    assert cost["input"] + cost["output"] == pytest.approx(result.cost_usd)

    # First token = generation start + TTFT: after the run started, and well before
    # the end of the 100 ms FakeLLM spends on the rest of the answer.
    first_token_at = generation["completion_start_time"]
    assert first_token_at.tzinfo is not None
    assert first_token_at - before >= timedelta(milliseconds=result.ttft_ms)
    assert after - first_token_at >= timedelta(milliseconds=50)


def test_child_observations_receive_summaries_not_raw_text(recorded) -> None:
    _, result = run_agent("Explain monitoring to student@vinuni.edu.vn")

    assert recorded["observation"] == [
        {"input": {"query_preview": "Explain monitoring to [REDACTED_EMAIL]"}},
        {"output": {"doc_count": 1}},
    ]
    # No input/output on the generation: the prompt embeds the raw user message.
    assert set(recorded["generation"][0]) == {
        "model",
        "usage_details",
        "cost_details",
        "completion_start_time",
    }
    sent = repr(recorded)
    assert "student@vinuni.edu.vn" not in sent
    assert result.answer not in sent


def test_failed_retrieval_keeps_query_preview_and_skips_generation(recorded, monkeypatch) -> None:
    monkeypatch.setitem(STATE, "tool_fail", True)

    with pytest.raises(RuntimeError, match="Vector store timeout"):
        run_agent("Explain monitoring")

    # The failed retriever span still shows which query it was working on.
    assert recorded["observation"] == [{"input": {"query_preview": "Explain monitoring"}}]
    assert recorded["generation"] == []
