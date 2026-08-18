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


class SoulVietAgentGraph:
    MAX_ITERATIONS = 8
    MAX_TOOL_CALLS = 16
    MAX_REQUIRED_TOOL_FAILURES = 1
    MAX_REPAIR_ATTEMPTS = 2
    READ_TOOLS = {
        "get_trip_state",
        "get_itinerary_summary",
        "get_day_details",
        "get_place_details",
        "search_places",
        "resolve_location_scope",
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
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.groq_api_key = (
            os.getenv("GROQ_API_KEY", "").strip()
            or os.getenv("GROQ_API_KEY_1", "").strip()
            or os.getenv("GROQ_API_KEY_2", "").strip()
        )
        self.groq_api_keys = list(dict.fromkeys(filter(None, (
            os.getenv("GROQ_API_KEY", "").strip(),
            os.getenv("GROQ_API_KEY_1", "").strip(),
            os.getenv("GROQ_API_KEY_2", "").strip(),
        ))))
        self.sambanova_api_key = os.getenv("SAMBANOVA_API_KEY", "").strip()
        self.cerebras_api_key = os.getenv("CEREBRAS_API_KEY", "").strip()
        self.mistral_api_key = os.getenv("MISTRAL_API_KEY", "").strip()
        self.history_turns = max(
            1, int(os.getenv("AGENT_HISTORY_TURNS", "3"))
        )
        self.history_max_chars = max(
            2000, int(os.getenv("AGENT_HISTORY_MAX_CHARS", "16000"))
        )
        self.model = model
        configured_models = []
        if self.model is None:
            if self.gemini_api_key:
                configured_models.append((
                    "gemini",
                    os.getenv(
                        "GEMINI_MODEL", "gemini-3.5-flash-lite"
                    ).strip(),
                    self._gemini_model(),
                ))
            for index, api_key in enumerate(self.groq_api_keys, start=1):
                configured_models.append((
                    f"groq_{index}",
                    os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip(),
                    self._groq_model(api_key),
                ))
            if self.mistral_api_key:
                configured_models.append((
                    "mistral",
                    os.getenv(
                        "MISTRAL_MODEL", "mistral-small-latest"
                    ).strip(),
                    self._compatible_model(
                        "MISTRAL", self.mistral_api_key,
                        "mistral-small-latest", "https://api.mistral.ai/v1",
                    ),
                ))
            if self.sambanova_api_key:
                configured_models.append((
                    "sambanova",
                    os.getenv("SAMBANOVA_MODEL", "gpt-oss-120b").strip(),
                    self._compatible_model(
                        "SAMBANOVA", self.sambanova_api_key,
                        "gpt-oss-120b", "https://api.sambanova.ai/v1",
                    ),
                ))
            if self.cerebras_api_key:
                configured_models.append((
                    "cerebras",
                    os.getenv("CEREBRAS_MODEL", "gpt-oss-120b").strip(),
                    self._compatible_model(
                        "CEREBRAS", self.cerebras_api_key,
                        "gpt-oss-120b", "https://api.cerebras.ai/v1",
                        {"X-Cerebras-3rd-Party-Integration": "langgraph"},
                    ),
                ))

        if configured_models:
            self.provider_name, self.model_id, self.model = configured_models[0]
            fallback_models = [item[2] for item in configured_models[1:]]
            self.fallback_providers = [item[0] for item in configured_models[1:]]
        else:
            fallback_models = []
            self.fallback_providers = []
            self.provider_name = "injected" if self.model is not None else "none"
            self.model_id = getattr(self.model, "model_name", None)
        self.api_key = next((
            value for value in (
                self.gemini_api_key, *self.groq_api_keys,
                self.sambanova_api_key, self.cerebras_api_key,
                self.mistral_api_key,
            ) if value
        ), "")

        def bind_with_fallbacks(tools, **kwargs):
            if not self.model:
                return None
            primary = self.model.bind_tools(tools, **kwargs)
            if not fallback_models:
                return primary
            fallbacks = [
                fallback.bind_tools(tools, **kwargs)
                for fallback in fallback_models
            ]
            return primary.with_fallbacks(fallbacks)

        self.model_with_tools = bind_with_fallbacks(AGENT_TOOLS)
        first_turn_tools = [
            tool for tool in AGENT_TOOLS
            if tool.name in {
                *self.READ_TOOLS,
                "apply_trip_changes",
                "report_unsupported_request",
                "save_user_memory",
                "forget_user_memory",
            }
        ]
        self.model_with_required_tool = bind_with_fallbacks(
            first_turn_tools, tool_choice="required"
        )
        self.graph = self._build_graph()

    def _gemini_model(self):
        return ChatOpenAI(
            model=os.getenv(
                "GEMINI_MODEL", "gemini-3.5-flash-lite"
            ).strip(),
            api_key=self.gemini_api_key,
            base_url=(
                "https://generativelanguage.googleapis.com/v1beta/openai/"
            ),
            default_headers={"User-Agent": "SoulViet-RAG/1.0"},
            max_tokens=max(
                128, int(os.getenv("GEMINI_MAX_COMPLETION_TOKENS", "768")),
            ),
            timeout=float(os.getenv("GEMINI_TIMEOUT_SECONDS", "120")),
            max_retries=max(0, int(os.getenv("GEMINI_MAX_RETRIES", "1"))),
        )

    def _groq_model(self, api_key):
        return ChatOpenAI(
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip(),
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            default_headers={"User-Agent": "SoulViet-RAG/1.0"},
            temperature=1,
            max_tokens=max(
                128, int(os.getenv("GROQ_MAX_COMPLETION_TOKENS", "768")),
            ),
            top_p=1,
            reasoning_effort=os.getenv(
                "GROQ_REASONING_EFFORT", "medium"
            ).strip(),
            timeout=float(os.getenv("GROQ_TIMEOUT_SECONDS", "120")),
            max_retries=max(0, int(os.getenv("GROQ_MAX_RETRIES", "1"))),
        )

    @staticmethod
    def _compatible_model(
        prefix, api_key, default_model, default_base_url, extra_headers=None,
    ):
        headers = {"User-Agent": "SoulViet-RAG/1.0", **(extra_headers or {})}
        return ChatOpenAI(
            model=os.getenv(f"{prefix}_MODEL", default_model).strip(),
            api_key=api_key,
            base_url=os.getenv(
                f"{prefix}_BASE_URL", default_base_url
            ).strip().rstrip("/"),
            default_headers=headers,
            temperature=float(os.getenv(f"{prefix}_TEMPERATURE", "0.2")),
            max_tokens=max(
                128,
                int(os.getenv(f"{prefix}_MAX_COMPLETION_TOKENS", "768")),
            ),
            timeout=float(os.getenv(f"{prefix}_TIMEOUT_SECONDS", "120")),
            max_retries=max(
                0, int(os.getenv(f"{prefix}_MAX_RETRIES", "1"))
            ),
        )

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
            "current_constraints": state.get("current_constraints", {}),
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
                    "Lịch hiện tại vẫn được giữ nguyên."
                ))],
                "iteration_count": iteration,
                "outcome": "tool_error",
                "error": {"type": "iteration_limit_exceeded"},
            }
        must_use_tool = state.get("turn_tool_call_count", 0) == 0
        selected_model = (
            self.model_with_required_tool if must_use_tool
            else self.model_with_tools
        )
        response = selected_model.invoke([
            SystemMessage(content=self._runtime_prompt(state)),
            *self._recent_messages(state.get("messages", [])),
        ])
        updates = {"messages": [response], "iteration_count": iteration}
        if must_use_tool and not getattr(response, "tool_calls", None):
            failures = state.get("required_tool_failures", 0) + 1
            updates["required_tool_failures"] = failures
            if failures > self.MAX_REQUIRED_TOOL_FAILURES:
                updates.update({
                    "outcome": "tool_error",
                    "error": {"type": "missing_required_tool_call"},
                })
        elif not getattr(response, "tool_calls", None):
            updates["outcome"] = state.get("outcome") or "completed"
        return updates

    @staticmethod
    def _draft_snapshot(state):
        return {
            key: state.get(key)
            for key in (
                "working_request", "working_constraints", "working_itinerary",
                "validation_report", "dirty", "committed",
            )
        }

    @staticmethod
    def _plan_signature(state):
        itinerary = state.get("working_itinerary") or []
        report = state.get("validation_report") or {}
        return json.dumps({
            "days": [
                [item.get("id") for item in day.get("places", [])]
                for day in itinerary
            ],
            "violations": sorted(
                report.get("hard_violations", [])
                + report.get("quality_violations", [])
            ),
        }, sort_keys=True, ensure_ascii=False)

    def _next_repair(self, state, attempt):
        """Tighten optional planning policy without relaxing hard constraints."""
        constraints = self.executor._working_constraints(state)
        report = state.get("validation_report") or {}
        violations = set(
            report.get("hard_violations", [])
            + report.get("quality_violations", [])
        )
        if "empty_days" in violations:
            policy = dict(constraints.get("optimization_policy", {}))
            if constraints.get("allowed_place_ids") and not policy.get("reorder_only"):
                constraints.pop("allowed_place_ids", None)
                return constraints, "restore_full_candidate_pool"
            request = self.executor._working_request(state)
            if request.get("location_mode") == "nearby":
                radius = float(request.get("location_radius_km") or 8)
                if radius < 50:
                    request["location_radius_km"] = min(50, radius + 5 * attempt)
                    state["working_request"] = request
                    return constraints, f"expand_nearby_radius_to_{request['location_radius_km']:g}km"
            return None, None

        policy = dict(constraints.get("optimization_policy", {}))
        if policy.get("fill_idle_gaps", True):
            policy["fill_idle_gaps"] = False
            constraints["optimization_policy"] = policy
            return constraints, "disable_idle_gap_filling"

        request = self.executor._working_request(state)
        current_limit = int(request.get("max_places_per_day", 1))
        target = max(1, current_limit - attempt)
        policies = {
            int(item["day"]): dict(item)
            for item in constraints.get("day_policies", [])
        }
        changed = False
        for day in range(1, int(request["duration"]) + 1):
            previous = int(policies.get(day, {}).get("max_places") or current_limit)
            if target < previous:
                policies[day] = {
                    **policies.get(day, {}), "day": day, "max_places": target,
                }
                changed = True
        if not changed:
            return None, None
        constraints["day_policies"] = list(policies.values())
        return constraints, f"reduce_optional_density_to_{target}"

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
                "outcome": "tool_error",
                "auto_finalize": True,
            }

        updates = {}
        local_state = dict(state)
        batch_snapshot = self._draft_snapshot(state)
        batch_failed = False
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
                batch_failed = True
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
        if batch_failed:
            updates["outcome"] = "tool_error"
        if batch_failed and should_run_workflow:
            for key, value in batch_snapshot.items():
                updates[key] = value
                local_state[key] = value
        if (
            should_run_workflow
            and not batch_failed
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
                repair_history = []
                seen_signatures = {self._plan_signature(local_state)}
                repair_count = 0
                while (
                    not report.get("acceptable")
                    and repair_count < self.MAX_REPAIR_ATTEMPTS
                ):
                    attempt = repair_count + 1
                    repaired_constraints, strategy = self._next_repair(
                        local_state, attempt
                    )
                    if not strategy:
                        break
                    local_state["working_constraints"] = repaired_constraints
                    observation, tool_updates = self.executor.execute(
                        "replan_itinerary", {}, local_state
                    )
                    local_state.update(tool_updates)
                    updates.update(tool_updates)
                    repair_count = attempt
                    signature = self._plan_signature(local_state)
                    progressed = signature not in seen_signatures
                    repair_history.append({
                        "attempt": attempt,
                        "strategy": strategy,
                        "status": (local_state.get("validation_report") or {}).get("status"),
                        "progressed": progressed,
                    })
                    automatic.append({**observation, "repair_strategy": strategy})
                    tool_names.append("repair_itinerary")
                    report = local_state.get("validation_report") or {}
                    if not progressed:
                        break
                    seen_signatures.add(signature)
                updates["repair_count"] = repair_count
                updates["repair_history"] = repair_history
                if report.get("acceptable"):
                    observation, tool_updates = self.executor.execute(
                        "commit_itinerary", {}, local_state
                    )
                    local_state.update(tool_updates)
                    updates.update(tool_updates)
                    automatic.append(observation)
                    tool_names.append("commit_itinerary")
                    updates["outcome"] = "committed"
                else:
                    updates.update({
                        "working_request": None,
                        "working_constraints": None,
                        "working_itinerary": None,
                        "dirty": False,
                        "committed": False,
                        "failure_report": report,
                        "outcome": "infeasible",
                    })
                    local_state.update(updates)
            except Exception as error:
                updates["error"] = {
                    "tool": "automatic_workflow",
                    "type": error.__class__.__name__,
                    "message": str(error),
                }
                local_state["error"] = updates["error"]
                updates.update({
                    "working_request": None,
                    "working_constraints": None,
                    "working_itinerary": None,
                    "validation_report": None,
                    "dirty": False,
                    "committed": False,
                    "outcome": "tool_error",
                })
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
            "turn_tool_call_count": state.get("turn_tool_call_count", 0) + len(calls),
            "last_tool_names": tool_names,
            "last_tool_observations": observation_values,
            "auto_finalize": auto_finalize,
        })
        return updates

    @staticmethod
    def _committed_itinerary_reply(state, unsupported_notice=""):
        request = state.get("current_request") or {}
        focus = request.get("location_focus") or request.get("region") or "điểm đến"
        itinerary = state.get("current_itinerary") or []
        lines = [
            f"Mình đã tạo hành trình {len(itinerary)} ngày tại {focus}:"
        ]
        for index, day in enumerate(itinerary, start=1):
            names = [
                str(place.get("name"))
                for place in day.get("places", [])
                if place.get("name")
                and place.get("item_type", "attraction") != "meal"
            ]
            lines.append(
                f"Ngày {day.get('day', index)}: "
                + (" → ".join(names) if names else "chưa có địa điểm")
            )

        report = state.get("validation_report") or {}
        category_counts = (report.get("metrics") or {}).get(
            "category_counts", {}
        )
        unmet_soft = []
        for rule in request.get("category_constraints", []):
            if rule.get("mode") != "soft":
                continue
            desired = max(
                int(rule.get("min_count") or 0),
                int(rule.get("target_count") or 0),
            )
            if desired and int(category_counts.get(rule.get("category"), 0)) < desired:
                unmet_soft.append(str(rule.get("category")))
        if unmet_soft:
            lines.append(
                "Lưu ý: dữ liệu hiện chưa gắn đủ nhãn cho "
                + ", ".join(dict.fromkeys(unmet_soft))
                + "; mình đã dùng những điểm phù hợp nhất hiện có."
            )
        if unsupported_notice:
            lines.append(unsupported_notice.strip())
        return "\n".join(lines)

    @staticmethod
    def _finalize_tools(state):
        observations = state.get("last_tool_observations", [])
        for observation in reversed(observations):
            if observation.get("tool") == "ask_user_clarification":
                question = (observation.get("data") or {}).get("question")
                return {
                    "messages": [AIMessage(content=question or "Vui lòng làm rõ yêu cầu.")],
                    "outcome": "input_required",
                }
        error = state.get("error")
        if error:
            return {
                "messages": [AIMessage(content=(
                    "Mình chưa áp dụng được thay đổi. "
                    "Lịch hiện tại vẫn được giữ nguyên."
                ))],
                "outcome": state.get("outcome") or "tool_error",
            }
        unsupported = state.get("unsupported_requests") or []
        unsupported_notice = (
            " Phần yêu cầu về ăn uống chưa được áp dụng vì MVP hiện chỉ "
            "hỗ trợ lập lịch điểm tham quan."
            if any(
                item.get("capability") == "meal_planning"
                for item in unsupported
            )
            else ""
        )
        if state.get("committed"):
            return {
                "messages": [AIMessage(content=(
                    SoulVietAgentGraph._committed_itinerary_reply(
                        state, unsupported_notice
                    )
                ))],
                "outcome": "committed",
            }
        if state.get("outcome") == "infeasible":
            report = state.get("failure_report") or {}
            violations = (
                report.get("hard_violations", [])
                + report.get("quality_violations", [])
            )
            detail = ", ".join(violations[:4]) or "các ràng buộc đang xung đột"
            return {
                "messages": [AIMessage(content=(
                    "Chưa thể tạo lịch hợp lệ với yêu cầu hiện tại "
                    f"({detail}). Lịch trước đó vẫn được giữ nguyên."
                    f"{unsupported_notice}"
                ))],
                "outcome": "infeasible",
            }
        summaries = [
            item.get("summary") for item in observations if item.get("summary")
        ]
        if unsupported_notice:
            return {
                "messages": [AIMessage(content=(
                    "Mình hiểu bạn muốn bổ sung nội dung ăn uống."
                    f"{unsupported_notice} Lịch hiện tại vẫn được giữ nguyên."
                ))],
                "outcome": state.get("outcome") or "completed",
            }
        return {
            "messages": [AIMessage(content=(
                "; ".join(summaries) or "Đã xử lý yêu cầu."
            ))],
            "outcome": state.get("outcome") or "completed",
        }

    @staticmethod
    def _route_after_agent(state):
        message = state["messages"][-1]
        if getattr(message, "tool_calls", None):
            return "tools"
        if (
            state.get("turn_tool_call_count", 0) == 0
            and state.get("required_tool_failures", 0)
            <= SoulVietAgentGraph.MAX_REQUIRED_TOOL_FAILURES
            and not state.get("outcome")
        ):
            return "agent"
        if state.get("outcome") == "tool_error":
            return "finalize"
        return END

    @staticmethod
    def _route_after_tools(state):
        return (
            "finalize"
            if state.get("auto_finalize") or state.get("outcome") == "tool_error"
            else "agent"
        )

    def _build_graph(self):
        builder = StateGraph(SoulVietAgentState)
        builder.add_node("retrieve_memory", self._retrieve_memory)
        builder.add_node("agent", self._call_agent)
        builder.add_node("tools", self._execute_tools)
        builder.add_node("finalize", self._finalize_tools)
        builder.add_edge(START, "retrieve_memory")
        builder.add_edge("retrieve_memory", "agent")
        builder.add_conditional_edges(
            "agent",
            self._route_after_agent,
            {"agent": "agent", "tools": "tools", "finalize": "finalize", END: END},
        )
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
            raise RuntimeError("No supported LLM API key is configured")
        state = self.graph.invoke(
            {
                "messages": [HumanMessage(content=message)],
                "user_id": user_id,
                "thread_id": thread_id,
                "current_request": current_request,
                "current_itinerary": current_itinerary,
                "committed": False,
                "working_request": None,
                "working_constraints": None,
                "working_itinerary": None,
                "validation_report": None,
                "dirty": False,
                "iteration_count": 0,
                "tool_call_count": 0,
                "turn_tool_call_count": 0,
                "required_tool_failures": 0,
                "repair_count": 0,
                "repair_history": [],
                "outcome": None,
                "failure_report": None,
                "unsupported_requests": [],
                "last_tool_names": [],
                "last_tool_observations": [],
                "auto_finalize": False,
                "error": None,
            },
            {
                "configurable": {"thread_id": f"{user_id}:{thread_id}"},
                "recursion_limit": 30,
            },
        )
        return state
