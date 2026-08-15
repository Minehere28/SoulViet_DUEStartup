import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from agent.memory import AgentMemory
from agent.state import SoulVietAgentState
from agent.tools import (
    AGENT_TOOLS,
    EXECUTOR_TOOLS,
    SoulVietToolExecutor,
    observation_json,
)
from services.llm_service import LLMService


load_dotenv()
load_dotenv(".env.example", override=False)


class SoulVietAgentGraph:
    MAX_ITERATIONS = 8
    MAX_TOOL_CALLS = 16
    READ_TOOLS = {
        "get_trip_state",
        "get_itinerary_summary",
        "get_day_details",
        "get_place_details",
        "search_places",
        "list_user_memories",
    }
    WORKFLOW_TOOLS = {
        "replan_itinerary",
        "validate_itinerary",
        "commit_itinerary",
        "rollback_working_changes",
    }
    MUTATION_TOOLS = {
        "apply_trip_changes",
        "update_trip_settings",
        "set_activity_preferences",
        "set_category_constraint",
        "set_meal_preferences",
        "require_place",
        "exclude_place",
        "remove_itinerary_item",
        "replace_itinerary_item",
        "set_exclusion_filters",
        "apply_quality_policies",
        "move_itinerary_item",
        "lock_itinerary_item",
        "unlock_itinerary_item",
    }

    def __init__(self, itinerary=None, memory=None, model=None):
        self.memory = memory or AgentMemory()
        self.executor = SoulVietToolExecutor(
            itinerary=itinerary,
            memory=self.memory,
        )
        self.system_prompt = (
            Path(__file__).parent / "prompts" / "system.md"
        ).read_text(encoding="utf-8")
        self.api_key = (
            os.getenv("GROQ_API_KEY", "").strip()
            or os.getenv("GROQ_API_KEY_1", "").strip()
            or os.getenv("GROQ_API_KEY_2", "").strip()
        )
        self.model_id = os.getenv(
            "GROQ_MODEL", "openai/gpt-oss-20b"
        ).strip()
        self.history_turns = max(
            1, int(os.getenv("AGENT_HISTORY_TURNS", "3"))
        )
        self.history_max_chars = max(
            2000, int(os.getenv("AGENT_HISTORY_MAX_CHARS", "16000"))
        )
        self.model = model
        if self.model is None and self.api_key:
            self.model = ChatOpenAI(
                model=self.model_id,
                api_key=self.api_key,
                base_url="https://api.groq.com/openai/v1",
                default_headers={"User-Agent": "SoulViet-RAG/1.0"},
                temperature=1,
                max_tokens=max(
                    128,
                    int(os.getenv("GROQ_MAX_COMPLETION_TOKENS", "768")),
                ),
                top_p=1,
                reasoning_effort=os.getenv(
                    "GROQ_REASONING_EFFORT", "medium"
                ).strip(),
                timeout=float(os.getenv("GROQ_TIMEOUT_SECONDS", "120")),
                max_retries=max(
                    0, int(os.getenv("GROQ_MAX_RETRIES", "1"))
                ),
            )
        self.model_with_tools = (
            self.model.bind_tools(AGENT_TOOLS) if self.model else None
        )
        self.graph = self._build_graph()

    @property
    def available(self):
        return self.model_with_tools is not None

    @staticmethod
    def _last_user_text(messages):
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                return str(message.content)
        return ""

    def _retrieve_memory(self, state):
        query = self._last_user_text(state.get("messages", []))
        memories = self.memory.search(state["user_id"], query, limit=5)
        return {"retrieved_memories": memories}

    def _runtime_prompt(self, state):
        compact_itinerary = LLMService._compact_itinerary(
            state.get("current_itinerary") or []
        )
        runtime = {
            "user_id": state.get("user_id"),
            "thread_id": state.get("thread_id"),
            "current_request": state.get("current_request"),
            "current_itinerary": compact_itinerary,
            "working_request": state.get("working_request"),
            "working_constraints": state.get("working_constraints", {}),
            "working_state_dirty": state.get("dirty", False),
            "validation_report": state.get("validation_report"),
            "retrieved_user_memories": state.get("retrieved_memories", []),
            "remaining_iterations": max(
                0, self.MAX_ITERATIONS - state.get("iteration_count", 0)
            ),
        }
        return (
            f"{self.system_prompt}\n\n"
            "<runtime_context>\n"
            f"{json.dumps(runtime, ensure_ascii=False, default=str)}\n"
            "</runtime_context>"
        )

    def _recent_messages(self, messages):
        """Keep recent complete user turns while checkpoints retain full history."""
        messages = list(messages or [])
        human_indexes = [
            index for index, message in enumerate(messages)
            if isinstance(message, HumanMessage)
        ]
        if not human_indexes:
            return messages

        eligible = human_indexes[-self.history_turns:]
        start = eligible[0]
        selected = messages[start:]
        while (
            sum(len(str(getattr(message, "content", ""))) for message in selected)
            > self.history_max_chars
            and len(eligible) > 1
        ):
            eligible.pop(0)
            start = eligible[0]
            selected = messages[start:]
        return selected

    def _call_agent(self, state):
        iteration = state.get("iteration_count", 0) + 1
        if iteration > self.MAX_ITERATIONS:
            return {
                "messages": [AIMessage(content=(
                    "Mình chưa hoàn tất yêu cầu trong giới hạn xử lý. "
                    "Các thay đổi chưa commit đã được giữ ở bản nháp."
                ))],
                "iteration_count": iteration,
            }
        response = self.model_with_tools.invoke([
            SystemMessage(content=self._runtime_prompt(state)),
            *self._recent_messages(state.get("messages", [])),
        ])
        return {"messages": [response], "iteration_count": iteration}

    def _execute_tools(self, state):
        message = state["messages"][-1]
        calls = list(getattr(message, "tool_calls", []) or [])
        total_calls = state.get("tool_call_count", 0) + len(calls)
        if total_calls > self.MAX_TOOL_CALLS:
            return {
                "messages": [ToolMessage(
                    content=observation_json({
                        "ok": False,
                        "error": "tool_call_limit_exceeded",
                    }),
                    tool_call_id=calls[0]["id"] if calls else "limit",
                )],
                "tool_call_count": total_calls,
                "error": {"type": "tool_call_limit_exceeded"},
            }

        updates = {}
        local_state = dict(state)
        observations = []
        observation_values = []
        tool_names = []
        tools_by_name = {tool.name: tool for tool in EXECUTOR_TOOLS}
        for call in calls:
            name = call["name"]
            tool_names.append(name)
            try:
                if name not in tools_by_name:
                    raise ValueError(f"Tool is not allowed: {name}")
                validated = tools_by_name[name].args_schema.model_validate(
                    call.get("args") or {}
                ).model_dump(mode="json", exclude_none=True)
                observation, tool_updates = self.executor.execute(
                    name, validated, local_state
                )
                local_state.update(tool_updates)
                updates.update(tool_updates)
            except Exception as error:  # Tool errors become model observations.
                observation = {
                    "ok": False,
                    "tool": name,
                    "error": error.__class__.__name__,
                    "message": str(error),
                }
                updates["error"] = {
                    "tool": name,
                    "type": error.__class__.__name__,
                    "message": str(error),
                }
                local_state["error"] = updates["error"]
            observation_values.append(observation)
            observations.append(ToolMessage(
                content=observation_json(observation),
                tool_call_id=call["id"],
                name=name,
            ))

        automatic = []
        model_called_names = [call["name"] for call in calls]
        called_workflow = self.WORKFLOW_TOOLS.intersection(tool_names)
        should_run_workflow = bool(
            self.MUTATION_TOOLS.intersection(model_called_names)
        )
        if (
            should_run_workflow
            and local_state.get("dirty")
            and "commit_itinerary" not in called_workflow
        ):
            try:
                if "replan_itinerary" not in called_workflow:
                    observation, tool_updates = self.executor.execute(
                        "replan_itinerary", {}, local_state
                    )
                    local_state.update(tool_updates)
                    updates.update(tool_updates)
                    automatic.append(observation)
                    tool_names.append("replan_itinerary")
                report = local_state.get("validation_report") or {}
                if report.get("acceptable"):
                    observation, tool_updates = self.executor.execute(
                        "commit_itinerary", {}, local_state
                    )
                    local_state.update(tool_updates)
                    updates.update(tool_updates)
                    automatic.append(observation)
                    tool_names.append("commit_itinerary")
            except Exception as error:
                updates["error"] = {
                    "tool": "automatic_workflow",
                    "type": error.__class__.__name__,
                    "message": str(error),
                }
                local_state["error"] = updates["error"]
                automatic.append({
                    "ok": False,
                    "tool": "automatic_workflow",
                    "error": error.__class__.__name__,
                    "message": str(error),
                })

        if automatic and observation_values:
            observation_values[-1]["automatic_workflow"] = automatic
            last = observations[-1]
            observations[-1] = ToolMessage(
                content=observation_json(observation_values[-1]),
                tool_call_id=last.tool_call_id,
                name=last.name,
            )
        auto_finalize = bool(model_called_names) and not all(
            name in self.READ_TOOLS for name in model_called_names
        )
        updates.update({
            "messages": observations,
            "tool_call_count": total_calls,
            "last_tool_names": tool_names,
            "last_tool_observations": observation_values,
            "auto_finalize": auto_finalize,
        })
        return updates

    @staticmethod
    def _finalize_tools(state):
        observations = state.get("last_tool_observations", [])
        for observation in reversed(observations):
            if observation.get("tool") == "ask_user_clarification":
                question = (observation.get("data") or {}).get("question")
                return {"messages": [AIMessage(content=question or "Bạn vui lòng làm rõ yêu cầu.")]}
        error = state.get("error")
        if error:
            return {"messages": [AIMessage(content=(
                "Mình chưa áp dụng được thay đổi: "
                f"{error.get('message', error.get('type', 'lỗi không xác định'))}"
            ))]}
        if state.get("committed"):
            return {"messages": [AIMessage(content=(
                "Đã cập nhật, lập lại và kiểm tra hành trình thành công."
            ))]}
        if state.get("dirty"):
            report = state.get("validation_report") or {}
            return {"messages": [AIMessage(content=(
                "Mình đã tạo bản nháp nhưng chưa commit vì lịch chưa thỏa các "
                f"ràng buộc ({report.get('status', 'chưa xác định')})."
            ))]}
        summaries = [
            item.get("summary") for item in observations if item.get("summary")
        ]
        return {"messages": [AIMessage(content=(
            "; ".join(summaries) or "Đã xử lý yêu cầu."
        ))]}

    @staticmethod
    def _route_after_agent(state):
        message = state["messages"][-1]
        if getattr(message, "tool_calls", None):
            return "tools"
        return END

    @staticmethod
    def _route_after_tools(state):
        return "finalize" if state.get("auto_finalize") else "agent"

    def _build_graph(self):
        builder = StateGraph(SoulVietAgentState)
        builder.add_node("retrieve_memory", self._retrieve_memory)
        builder.add_node("agent", self._call_agent)
        builder.add_node("tools", self._execute_tools)
        builder.add_node("finalize", self._finalize_tools)
        builder.add_edge(START, "retrieve_memory")
        builder.add_edge("retrieve_memory", "agent")
        builder.add_conditional_edges("agent", self._route_after_agent)
        builder.add_conditional_edges(
            "tools",
            self._route_after_tools,
            {"finalize": "finalize", "agent": "agent"},
        )
        builder.add_edge("finalize", END)
        return builder.compile(
            checkpointer=self.memory.checkpointer,
            store=self.memory.store,
        )

    def invoke(self, user_id, thread_id, message, current_request, current_itinerary):
        if not self.available:
            raise RuntimeError("GROQ_API_KEY is not configured")
        state = self.graph.invoke(
            {
                "messages": [HumanMessage(content=message)],
                "user_id": user_id,
                "thread_id": thread_id,
                "current_request": current_request,
                "current_itinerary": current_itinerary,
                "committed": False,
                "iteration_count": 0,
                "tool_call_count": 0,
                "last_tool_names": [],
                "last_tool_observations": [],
                "auto_finalize": False,
                "error": None,
            },
            {"configurable": {"thread_id": thread_id}, "recursion_limit": 30},
        )
        return state
