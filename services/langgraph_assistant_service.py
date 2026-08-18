import logging
from time import perf_counter

from langchain_core.messages import AIMessage

from agent.graph import SoulVietAgentGraph


logger = logging.getLogger(__name__)


class LangGraphAssistantService:
    def __init__(self, agent=None):
        self.agent = agent or SoulVietAgentGraph()

    def customize(self, assistant_request):
        started_at = perf_counter()
        request_data = assistant_request.current_request.model_dump(mode="json")
        if not self.agent.available:
            return {
                "answer": (
                    "Agent chưa hoạt động vì chưa có API key của nhà cung cấp "
                    "LLM được hỗ trợ."
                ),
                "provider": "langgraph_unavailable",
                "model": None,
                "fallback_reason": "No supported LLM API key is configured",
                "usage": None,
                "intent": "unknown",
                "applied_changes": [],
                "request": request_data,
                "itinerary": assistant_request.current_itinerary,
                "query_metadata": None,
                "validation_report": None,
                "unsupported_requests": [],
                "user_id": assistant_request.user_id,
                "thread_id": assistant_request.thread_id,
                "agent": {
                    "status": "unavailable",
                    "committed": False,
                    "fallback_providers": getattr(
                        self.agent, "fallback_providers", []
                    ),
                },
            }

        try:
            state = self.agent.invoke(
                user_id=assistant_request.user_id,
                thread_id=assistant_request.thread_id,
                message=assistant_request.message,
                current_request=request_data,
                current_itinerary=assistant_request.current_itinerary,
            )
        except Exception as error:
            logger.exception(
                "LLM LangGraph request failed for thread_id=%s",
                assistant_request.thread_id,
            )
            error_name = error.__class__.__name__
            if "timeout" in error_name.casefold():
                answer = (
                    "LLM đã xử lý quá thời gian cho phép. Bạn hãy thử lại; "
                    "hành trình và bộ nhớ vẫn được giữ nguyên."
                )
            elif "ratelimit" in error_name.casefold():
                answer = (
                    "Các nhà cung cấp LLM đang giới hạn tần suất hoặc quota. "
                    "Bạn hãy chờ một chút rồi thử lại."
                )
            elif "authentication" in error_name.casefold():
                answer = "API key của nhà cung cấp không hợp lệ hoặc đã hết hiệu lực."
            else:
                answer = (
                    "Agent chưa hoàn tất yêu cầu do lỗi kết nối với LLM. "
                    "Chi tiết lỗi đã được ghi trong terminal server."
                )
            return {
                "answer": answer,
                "provider": f"{getattr(self.agent, 'provider_name', 'llm')}_langgraph_error",
                "model": self.agent.model_id,
                "fallback_reason": error_name,
                "processing_seconds": round(perf_counter() - started_at, 3),
                "usage": None,
                "intent": "unknown",
                "applied_changes": [],
                "request": request_data,
                "itinerary": assistant_request.current_itinerary,
                "query_metadata": None,
                "validation_report": None,
                "unsupported_requests": [],
                "user_id": assistant_request.user_id,
                "thread_id": assistant_request.thread_id,
                "requires_input": False,
                "agent": {
                    "status": "provider_error",
                    "requires_input": False,
                    "iterations": 0,
                    "tool_calls": 0,
                    "committed": False,
                    "dirty": False,
                    "error": {
                        "type": error.__class__.__name__,
                        "message": str(error)[:500],
                    },
                    "fallback_providers": getattr(
                        self.agent, "fallback_providers", []
                    ),
                },
            }
        answer = next((
            str(message.content)
            for message in reversed(state.get("messages", []))
            if isinstance(message, AIMessage) and not message.tool_calls
        ), "Mình đã xử lý yêu cầu.")
        outcome = state.get("outcome")
        requires_input = outcome == "input_required"
        if outcome is None:
            requires_input = "ask_user_clarification" in state.get(
                "last_tool_names", []
            )
            if requires_input:
                outcome = "input_required"
            elif state.get("committed"):
                outcome = "committed"
            elif state.get("error"):
                outcome = "tool_error"
            else:
                outcome = "completed"
        return {
            "answer": answer,
            "provider": f"{getattr(self.agent, 'provider_name', 'llm')}_langgraph",
            "model": self.agent.model_id,
            "fallback_reason": None,
            "processing_seconds": round(perf_counter() - started_at, 3),
            "usage": None,
            "intent": "agent",
            "applied_changes": state.get("last_tool_names", []),
            "request": state.get("current_request", request_data),
            "itinerary": state.get(
                "current_itinerary", assistant_request.current_itinerary
            ),
            "query_metadata": None,
            "validation_report": state.get("validation_report"),
            "unsupported_requests": state.get("unsupported_requests", []),
            "user_id": assistant_request.user_id,
            "thread_id": assistant_request.thread_id,
            "requires_input": requires_input,
            "agent": {
                "status": outcome,
                "requires_input": requires_input,
                "iterations": state.get("iteration_count", 0),
                "tool_calls": state.get("tool_call_count", 0),
                "committed": state.get("committed", False),
                "dirty": state.get("dirty", False),
                "error": state.get("error"),
                "repair_count": state.get("repair_count", 0),
                "repair_history": state.get("repair_history", []),
                "failure_report": state.get("failure_report"),
                "unsupported_requests": state.get("unsupported_requests", []),
                "fallback_providers": getattr(
                    self.agent, "fallback_providers", []
                ),
            },
        }
