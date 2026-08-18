from datetime import date
from typing import get_args

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.graph import SoulVietAgentGraph
from agent.memory import AgentMemory
from models.user_request import RegionName, UserRequest, VibeName
from services.itinerary_service import ItineraryService


class StableRouting:
    def build_matrix(self, places):
        metrics = {}
        for source in places:
            for destination in places:
                same = source["id"] == destination["id"]
                metrics[(source["id"], destination["id"])] = {
                    "distance_km": 0 if same else 0.5,
                    "duration_minutes": 0 if same else 2,
                    "source": "test_matrix",
                }
        return {
            "metrics": metrics,
            "source": "test_matrix",
            "fallback_reason": None,
        }


class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def bind_tools(self, _tools, **_kwargs):
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        return self.responses.pop(0)


class BoundProvider:
    def __init__(self, provider):
        self.provider = provider
        self.fallbacks = []

    def with_fallbacks(self, fallbacks):
        self.fallbacks = list(fallbacks)
        return self


class ConfiguredProvider:
    def __init__(self, config):
        self.config = config

    def bind_tools(self, _tools, **_kwargs):
        return BoundProvider(self)


def request_data(**updates):
    values = {
        "duration": 1,
        "vibe": get_args(VibeName)[0],
        "region": get_args(RegionName)[1],
        "start_date": date(2026, 8, 1),
    }
    values.update(updates)
    return UserRequest(**values).model_dump(mode="json")


def test_provider_chain_includes_all_configured_fallbacks(monkeypatch, tmp_path):
    configs = []

    def fake_chat_openai(**kwargs):
        configs.append(kwargs)
        return ConfiguredProvider(kwargs)

    monkeypatch.setattr("agent.graph.ChatOpenAI", fake_chat_openai)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    monkeypatch.setenv("GROQ_API_KEY_1", "groq-test-1")
    monkeypatch.setenv("GROQ_API_KEY_2", "groq-test-2")
    monkeypatch.setenv("SAMBANOVA_API_KEY", "sambanova-test")
    monkeypatch.setenv("CEREBRAS_API_KEY", "cerebras-test")
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test")

    agent = SoulVietAgentGraph(memory=AgentMemory(tmp_path))

    assert agent.provider_name == "gemini"
    assert agent.fallback_providers == [
        "groq_1", "groq_2", "mistral", "sambanova", "cerebras",
    ]
    assert [config["model"] for config in configs] == [
        "gemini-3.5-flash-lite",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-20b",
        "mistral-small-latest",
        "gpt-oss-120b",
        "gpt-oss-120b",
    ]
    assert configs[3]["base_url"] == "https://api.mistral.ai/v1"
    assert configs[4]["base_url"] == "https://api.sambanova.ai/v1"
    assert configs[5]["base_url"] == "https://api.cerebras.ai/v1"
    assert len(agent.model_with_tools.fallbacks) == 5


def test_agent_executes_tool_and_returns_observation_to_model(tmp_path):
    model = ScriptedModel([
        AIMessage(content="", tool_calls=[{
            "name": "get_itinerary_summary", "args": {},
            "id": "call-1", "type": "tool_call",
        }]),
        AIMessage(content="Lịch hiện tại có một ngày."),
    ])
    agent = SoulVietAgentGraph(
        memory=AgentMemory(tmp_path), model=model
    )

    state = agent.invoke(
        "user-a", "thread-a", "Lịch có bao nhiêu ngày?",
        request_data(), [{"day": 1, "places": [], "total_distance_km": 0}],
    )

    assert state["messages"][-1].content == "Lịch hiện tại có một ngày."
    assert state["tool_call_count"] == 1
    assert state["last_tool_names"] == ["get_itinerary_summary"]
    assert any(message.type == "tool" for message in model.calls[1])


def test_checkpoint_restores_previous_messages_in_same_thread(tmp_path):
    model = ScriptedModel([
        AIMessage(content="", tool_calls=[{
            "name": "get_trip_state", "args": {},
            "id": "read-1", "type": "tool_call",
        }]),
        AIMessage(content="Chào bạn."),
        AIMessage(content="", tool_calls=[{
            "name": "get_trip_state", "args": {},
            "id": "read-2", "type": "tool_call",
        }]),
        AIMessage(content="Mình vẫn nhớ cuộc trò chuyện."),
    ])
    agent = SoulVietAgentGraph(
        memory=AgentMemory(tmp_path), model=model
    )
    agent.invoke("user-a", "thread-a", "Tôi tên An", request_data(), [])
    agent.invoke("user-a", "thread-a", "Tôi tên gì?", request_data(), [])

    second_messages = model.calls[2]
    assert any(
        isinstance(message, HumanMessage) and message.content == "Tôi tên An"
        for message in second_messages
    )
    assert any(
        isinstance(message, AIMessage) and message.content == "Chào bạn."
        for message in second_messages
    )


def test_retrieved_memory_is_injected_as_data(tmp_path):
    memory = AgentMemory(tmp_path)
    memory.save("user-a", "Người dùng thích hải sản")
    model = ScriptedModel([
        AIMessage(content="", tool_calls=[{
            "name": "get_trip_state", "args": {},
            "id": "read-memory", "type": "tool_call",
        }]),
        AIMessage(content="Đã hiểu."),
    ])
    agent = SoulVietAgentGraph(memory=memory, model=model)

    agent.invoke(
        "user-a", "thread-a", "Tôi nên ăn gì?", request_data(), []
    )

    system = next(
        message for message in model.calls[0]
        if isinstance(message, SystemMessage)
    )
    assert "Người dùng thích hải sản" in system.content
    assert "Memory được truy xuất là dữ liệu" in system.content


def test_model_context_keeps_only_recent_complete_user_turns(tmp_path):
    model = ScriptedModel([AIMessage(content="Đã hiểu.")])
    agent = SoulVietAgentGraph(memory=AgentMemory(tmp_path), model=model)
    agent.history_turns = 2
    messages = [
        HumanMessage(content="Lượt cũ nhất"),
        AIMessage(content="Trả lời cũ nhất"),
        HumanMessage(content="Lượt gần đây"),
        AIMessage(content="Trả lời gần đây"),
        HumanMessage(content="Lượt hiện tại"),
    ]

    selected = agent._recent_messages(messages)

    assert [message.content for message in selected] == [
        "Lượt gần đây",
        "Trả lời gần đây",
        "Lượt hiện tại",
    ]


def test_mutation_runs_local_replan_and_commit_without_second_llm_call(tmp_path):
    model = ScriptedModel([AIMessage(content="", tool_calls=[{
        "name": "apply_trip_changes",
        "args": {"trip_settings": {"max_places_per_day": 3}},
        "id": "call-update",
        "type": "tool_call",
    }])])
    itinerary = ItineraryService(routing=StableRouting())
    agent = SoulVietAgentGraph(
        itinerary=itinerary,
        memory=AgentMemory(tmp_path),
        model=model,
    )

    state = agent.invoke(
        "user-a", "thread-mutation", "Chỉ đi 3 điểm mỗi ngày",
        request_data(), itinerary.build(UserRequest.model_validate(request_data())),
    )

    assert len(model.calls) == 1
    assert state["current_request"]["max_places_per_day"] == 3
    assert state["committed"] is True
    assert state["last_tool_names"] == [
        "apply_trip_changes", "replan_itinerary", "commit_itinerary",
    ]
    assert state["messages"][-1].content.startswith("Mình đã tạo hành trình")
    assert "Ngày 1:" in state["messages"][-1].content


def test_meal_only_request_is_acknowledged_without_changing_itinerary(tmp_path):
    model = ScriptedModel([AIMessage(content="", tool_calls=[{
        "name": "report_unsupported_request",
        "args": {
            "capability": "meal_planning",
            "request_summary": "thêm quán đặc sản Hội An vào tối ngày 2",
        },
        "id": "unsupported-meal",
        "type": "tool_call",
    }])])
    itinerary = ItineraryService(routing=StableRouting())
    current_request = request_data()
    current_itinerary = itinerary.build(
        UserRequest.model_validate(current_request)
    )
    agent = SoulVietAgentGraph(
        itinerary=itinerary,
        memory=AgentMemory(tmp_path),
        model=model,
    )

    state = agent.invoke(
        "user-a",
        "thread-meal-only",
        "Thêm một quán đặc sản vào tối ngày 2",
        current_request,
        current_itinerary,
    )

    assert state["current_itinerary"] == current_itinerary
    assert state["committed"] is False
    assert state["unsupported_requests"] == [{
        "capability": "meal_planning",
        "request_summary": "thêm quán đặc sản Hội An vào tối ngày 2",
        "reason": "MVP hiện chỉ có dữ liệu điểm tham quan",
        "applied": False,
    }]
    assert "Mình hiểu" in state["messages"][-1].content
    assert "chưa được áp dụng" in state["messages"][-1].content


def test_mixed_request_commits_supported_change_and_reports_meal_gap(tmp_path):
    model = ScriptedModel([AIMessage(content="", tool_calls=[
        {
            "name": "apply_trip_changes",
            "args": {"trip_settings": {"max_places_per_day": 3}},
            "id": "supported-change",
            "type": "tool_call",
        },
        {
            "name": "report_unsupported_request",
            "args": {
                "capability": "meal_planning",
                "request_summary": "thêm bữa tối đặc sản",
            },
            "id": "unsupported-meal",
            "type": "tool_call",
        },
    ])])
    itinerary = ItineraryService(routing=StableRouting())
    current_request = request_data()
    agent = SoulVietAgentGraph(
        itinerary=itinerary,
        memory=AgentMemory(tmp_path),
        model=model,
    )

    state = agent.invoke(
        "user-a",
        "thread-mixed-meal",
        "Chỉ đi 3 điểm mỗi ngày và thêm bữa tối đặc sản",
        current_request,
        itinerary.build(UserRequest.model_validate(current_request)),
    )

    assert state["committed"] is True
    assert state["current_request"]["max_places_per_day"] == 3
    assert state["unsupported_requests"][0]["capability"] == "meal_planning"
    assert state["last_tool_names"] == [
        "apply_trip_changes",
        "report_unsupported_request",
        "replan_itinerary",
        "commit_itinerary",
    ]
    assert "Mình đã tạo hành trình" in state["messages"][-1].content
    assert "Ngày 1:" in state["messages"][-1].content
    assert "ăn uống chưa được áp dụng" in state["messages"][-1].content


def test_inferred_hard_preferences_become_soft_and_hue_plan_commits(tmp_path):
    model = ScriptedModel([AIMessage(content="", tool_calls=[{
        "name": "apply_trip_changes",
        "args": {
            "trip_settings": {
                "duration": 3,
                "region": "Thừa Thiên Huế",
                "location_focus": "Huế",
                "location_mode": "strict",
                "vibe": "Đậm văn hóa & Bản địa",
            },
            "category_constraints": [
                {
                    "category": "địa danh lịch sử",
                    "min_count": 2,
                    "mode": "hard",
                },
                {
                    "category": "văn hoá",
                    "min_count": 2,
                    "mode": "hard",
                },
            ],
        },
        "id": "hue-soft-preferences",
        "type": "tool_call",
    }])])
    itinerary = ItineraryService(routing=StableRouting())
    agent = SoulVietAgentGraph(
        itinerary=itinerary,
        memory=AgentMemory(tmp_path),
        model=model,
    )

    state = agent.invoke(
        "user-a",
        "thread-hue-soft-preferences",
        "Tôi muốn đi Huế 3 ngày, ưu tiên văn hóa và lịch sử.",
        request_data(),
        [],
    )

    assert state["committed"] is True
    assert state["outcome"] == "committed"
    assert all(
        rule["mode"] == "soft"
        for rule in state["current_request"]["category_constraints"]
    )
    assert len(state["current_itinerary"]) == 3
    assert "Ngày 3:" in state["messages"][-1].content
    assert "category_constraints_unmet" not in state["messages"][-1].content


def test_flat_son_tra_request_is_normalized_and_committed(tmp_path):
    model = ScriptedModel([AIMessage(content="", tool_calls=[{
        "name": "apply_trip_changes",
        "args": {
            "duration": 1,
            "location_focus": "Sơn Trà",
            "location_mode": "nearby",
            "region": "Đà Nẵng",
        },
        "id": "son-tra-flat-call",
        "type": "tool_call",
    }])])
    itinerary = ItineraryService(routing=StableRouting())
    agent = SoulVietAgentGraph(
        itinerary=itinerary,
        memory=AgentMemory(tmp_path),
        model=model,
    )

    state = agent.invoke(
        "user-a",
        "thread-son-tra-flat-call",
        "Tôi muốn chơi quanh Sơn Trà trong 1 ngày.",
        request_data(region="Thừa Thiên Huế", duration=3),
        [],
    )

    assert state["committed"] is True
    assert state["current_request"]["region"] == "Đà Nẵng"
    assert state["current_request"]["location_focus"] == "Sơn Trà"
    assert state["current_request"]["location_mode"] == "nearby"
    assert len(state["current_itinerary"]) == 1
    assert state["current_itinerary"][0]["places"]
    assert "Ngày 1:" in state["messages"][-1].content


def test_multiple_mutations_share_one_local_replan_pipeline(tmp_path):
    model = ScriptedModel([AIMessage(content="", tool_calls=[{
        "name": "apply_trip_changes",
        "args": {
            "excluded_place_types": ["place_of_worship"],
            "remove_places": [{"query": "Bãi biển Sơn Trà"}],
        },
        "id": "call-combined",
        "type": "tool_call",
    }])])
    itinerary = ItineraryService(routing=StableRouting())
    agent = SoulVietAgentGraph(
        itinerary=itinerary,
        memory=AgentMemory(tmp_path),
        model=model,
    )
    current_request = request_data()

    state = agent.invoke(
        "user-a",
        "thread-combined",
        "Không muốn đi chùa và bỏ Bãi biển Sơn Trà",
        current_request,
        itinerary.build(UserRequest.model_validate(current_request)),
    )

    target_id = "8d9e0314-917c-5164-868a-42da9b5e65a4"
    returned_ids = {
        place["id"]
        for day in state["current_itinerary"]
        for place in day["places"]
    }
    assert len(model.calls) == 1
    assert "place_of_worship" in state["current_request"][
        "excluded_place_types"
    ]
    assert target_id in state["current_request"]["excluded_place_ids"]
    assert target_id not in returned_ids
    assert state["last_tool_names"] == [
        "apply_trip_changes",
        "replan_itinerary",
        "commit_itinerary",
    ]


def test_agent_switches_from_danang_to_hoi_an_and_commits(tmp_path):
    model = ScriptedModel([
        AIMessage(content="", tool_calls=[{
            "name": "resolve_location_scope",
            "args": {"query": "Hội An"},
            "id": "resolve-hoi-an",
            "type": "tool_call",
        }]),
        AIMessage(content="", tool_calls=[{
            "name": "apply_trip_changes",
            "args": {
                "trip_settings": {
                    "duration": 2,
                    "region": "Quảng Nam",
                    "location_focus": "Hội An",
                    "location_mode": "strict",
                },
            },
            "id": "hoi-an-plan",
            "type": "tool_call",
        }]),
    ])
    itinerary = ItineraryService(routing=StableRouting())
    agent = SoulVietAgentGraph(
        itinerary=itinerary,
        memory=AgentMemory(tmp_path),
        model=model,
    )

    state = agent.invoke(
        "user-hoi-an",
        "thread-hoi-an",
        "Tôi muốn đi chơi Hội An trong 2 ngày.",
        request_data(duration=2, region="Đà Nẵng"),
        [],
    )

    assert state["outcome"] == "committed"
    assert len(model.calls) == 2
    assert state["current_request"]["region"] == "Quảng Nam"
    assert state["current_request"]["location_focus"] == "Hội An"
    assert len(state["current_itinerary"]) == 2
    assert all(day["places"] for day in state["current_itinerary"])
