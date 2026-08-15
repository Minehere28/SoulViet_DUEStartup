from datetime import date
from typing import get_args

from langchain_core.messages import AIMessage

from models.assistant_request import AssistantRequest
from models.user_request import RegionName, UserRequest, VibeName
from services.langgraph_assistant_service import LangGraphAssistantService


def request():
    return UserRequest(
        vibe=get_args(VibeName)[0],
        region=get_args(RegionName)[1],
        start_date=date(2026, 8, 1),
    )


class FakeAgent:
    available = True
    model_id = "test-model"

    def invoke(self, **_kwargs):
        return {
            "messages": [AIMessage(content="Bạn muốn chọn bãi biển nào?")],
            "current_request": request().model_dump(mode="json"),
            "current_itinerary": [],
            "last_tool_names": ["ask_user_clarification"],
            "iteration_count": 2,
            "tool_call_count": 1,
            "committed": False,
            "dirty": False,
        }


class FailingAgent:
    available = True
    model_id = "test-model"

    def invoke(self, **_kwargs):
        raise RuntimeError("boom")


class APITimeoutError(Exception):
    pass


class TimeoutAgent:
    available = True
    model_id = "test-model"

    def invoke(self, **_kwargs):
        raise APITimeoutError("request timed out")


def test_service_exposes_thread_and_input_required_status():
    service = LangGraphAssistantService(agent=FakeAgent())
    payload = AssistantRequest(
        user_id="user-a",
        thread_id="thread-a",
        message="Thêm chỗ đó",
        current_request=request(),
    )

    result = service.customize(payload)

    assert result["thread_id"] == "thread-a"
    assert result["requires_input"] is True
    assert result["agent"]["status"] == "input_required"


def test_service_returns_json_payload_when_agent_call_fails():
    service = LangGraphAssistantService(agent=FailingAgent())
    payload = AssistantRequest(
        user_id="user-a",
        thread_id="thread-a",
        message="ThÃªm chá»— Ä‘Ã³",
        current_request=request(),
    )

    result = service.customize(payload)

    assert result["provider"] == "groq_langgraph_error"
    assert result["fallback_reason"] == "RuntimeError"
    assert result["agent"]["status"] == "error"
    assert result["agent"]["error"]["message"] == "boom"


def test_service_reports_timeout_instead_of_suggesting_bad_api_key():
    service = LangGraphAssistantService(agent=TimeoutAgent())
    payload = AssistantRequest(
        user_id="user-a",
        thread_id="thread-a",
        message="Thêm chỗ đó",
        current_request=request(),
    )

    result = service.customize(payload)

    assert result["fallback_reason"] == "APITimeoutError"
    assert "quá thời gian" in result["answer"]
    assert result["processing_seconds"] >= 0
