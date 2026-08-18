from datetime import date
from typing import get_args

from langchain_core.messages import AIMessage, HumanMessage

from agent.graph import SoulVietAgentGraph
from agent.memory import AgentMemory
from models.user_request import RegionName, UserRequest, VibeName
from services.locality_service import ResolvedLocality


def request_data(**updates):
    values = {
        "duration": 1,
        "vibe": get_args(VibeName)[0],
        "region": get_args(RegionName)[2],
        "start_date": date(2026, 8, 1),
    }
    values.update(updates)
    return UserRequest(**values).model_dump(mode="json")


class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.bindings = []

    def bind_tools(self, tools, **kwargs):
        self.bindings.append(([tool.name for tool in tools], kwargs))
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        return self.responses.pop(0)


def read_call(call_id):
    return AIMessage(content="", tool_calls=[{
        "name": "get_trip_state", "args": {},
        "id": call_id, "type": "tool_call",
    }])


def test_first_decision_requires_a_non_clarification_tool(tmp_path):
    model = ScriptedModel([read_call("read"), AIMessage(content="Đã đọc.")])
    agent = SoulVietAgentGraph(memory=AgentMemory(tmp_path), model=model)

    state = agent.invoke("user-a", "thread-a", "Lịch thế nào?", request_data(), [])

    required_tools, options = model.bindings[1]
    assert options == {"tool_choice": "required"}
    assert "ask_user_clarification" not in required_tools
    assert state["outcome"] == "completed"


def test_missing_required_tool_retries_then_returns_tool_error(tmp_path):
    model = ScriptedModel([
        AIMessage(content="trả lời trực tiếp"),
        AIMessage(content="vẫn không gọi tool"),
    ])
    agent = SoulVietAgentGraph(memory=AgentMemory(tmp_path), model=model)

    state = agent.invoke("user-a", "thread-a", "Lập lịch", request_data(), [])

    assert len(model.calls) == 2
    assert state["outcome"] == "tool_error"
    assert state["tool_call_count"] == 0


def test_checkpoint_is_namespaced_by_user_and_thread(tmp_path):
    model = ScriptedModel([
        read_call("a"), AIMessage(content="A"),
        read_call("b"), AIMessage(content="B"),
    ])
    agent = SoulVietAgentGraph(memory=AgentMemory(tmp_path), model=model)
    agent.invoke("user-a", "shared", "bí mật A", request_data(), [])
    agent.invoke("user-b", "shared", "câu hỏi B", request_data(), [])

    assert not any(
        isinstance(message, HumanMessage) and message.content == "bí mật A"
        for message in model.calls[2]
    )


def test_multi_tool_failure_discards_the_whole_draft_batch(tmp_path):
    model = ScriptedModel([])
    agent = SoulVietAgentGraph(memory=AgentMemory(tmp_path), model=model)
    state = {
        "messages": [AIMessage(content="", tool_calls=[
            {
                "name": "apply_trip_changes",
                "args": {"trip_settings": {"max_places_per_day": 3}},
                "id": "ok", "type": "tool_call",
            },
            {
                "name": "apply_trip_changes",
                "args": {"unsupported": True},
                "id": "bad", "type": "tool_call",
            },
        ])],
        "user_id": "user-a", "thread_id": "thread-a",
        "current_request": request_data(), "current_itinerary": [],
        "working_request": None, "working_constraints": None,
        "working_itinerary": None, "dirty": False, "committed": False,
    }

    updates = agent._execute_tools(state)

    assert updates["outcome"] == "tool_error"
    assert updates["working_request"] is None
    assert updates["working_constraints"] is None
    assert updates["dirty"] is False


def test_repair_changes_policy_and_can_reach_commit(tmp_path):
    model = ScriptedModel([AIMessage(content="", tool_calls=[{
        "name": "apply_trip_changes",
        "args": {"trip_settings": {"max_places_per_day": 3}},
        "id": "mutation", "type": "tool_call",
    }])])
    agent = SoulVietAgentGraph(memory=AgentMemory(tmp_path), model=model)
    calls = {"replan": 0}
    draft = [{"places": [{"id": "p"}], "total_distance_km": 1}]

    def execute(name, _args, state):
        if name == "apply_trip_changes":
            return {"ok": True, "tool": name}, {
                "working_request": {**state["current_request"], "max_places_per_day": 3},
                "working_constraints": {}, "dirty": True, "committed": False,
            }
        if name == "replan_itinerary":
            calls["replan"] += 1
            acceptable = calls["replan"] > 1
            report = {
                "acceptable": acceptable,
                "status": "success" if acceptable else "partial",
                "hard_violations": [],
                "quality_violations": [] if acceptable else ["duplicate_brands"],
            }
            return {"ok": True, "tool": name}, {
                "working_itinerary": draft,
                "validation_report": report,
                "dirty": True, "committed": False,
            }
        if name == "commit_itinerary":
            return {"ok": True, "tool": name}, {
                "current_request": state["working_request"],
                "current_itinerary": state["working_itinerary"],
                "current_constraints": state["working_constraints"],
                "working_request": None, "working_itinerary": None,
                "working_constraints": None, "dirty": False, "committed": True,
            }
        raise AssertionError(name)

    agent.executor.execute = execute
    state = agent.invoke("user-a", "repair", "Giảm mật độ", request_data(), [])

    assert calls["replan"] == 2
    assert state["repair_count"] == 1
    assert state["repair_history"][0]["strategy"] == "disable_idle_gap_filling"
    assert state["outcome"] == "committed"


def test_empty_days_does_not_trigger_density_reduction(tmp_path):
    agent = SoulVietAgentGraph(
        memory=AgentMemory(tmp_path),
        model=ScriptedModel([]),
    )
    state = {
        "current_request": request_data(),
        "working_request": request_data(),
        "working_constraints": {},
        "validation_report": {
            "hard_violations": [],
            "quality_violations": ["empty_days"],
        },
    }

    constraints, strategy = agent._next_repair(state, 1)

    assert constraints is None
    assert strategy is None


def test_automatic_workflow_failure_discards_dirty_draft(tmp_path):
    model = ScriptedModel([AIMessage(content="", tool_calls=[{
        "name": "apply_trip_changes",
        "args": {"trip_settings": {"max_places_per_day": 3}},
        "id": "mutation", "type": "tool_call",
    }])])
    agent = SoulVietAgentGraph(memory=AgentMemory(tmp_path), model=model)

    def execute(name, _args, state):
        if name == "apply_trip_changes":
            return {"ok": True, "tool": name}, {
                "working_request": {
                    **state["current_request"], "max_places_per_day": 3,
                },
                "working_constraints": {},
                "dirty": True,
                "committed": False,
            }
        if name == "replan_itinerary":
            raise RuntimeError("planner failed")
        raise AssertionError(name)

    agent.executor.execute = execute
    state = agent.invoke("user-a", "workflow-error", "Đổi lịch", request_data(), [])

    assert state["outcome"] == "tool_error"
    assert state["dirty"] is False
    assert state["working_request"] is None
    assert state["working_constraints"] is None
    assert state["working_itinerary"] is None
    assert state["validation_report"] is None


def test_tool_call_limit_finalizes_as_tool_error(tmp_path):
    model = ScriptedModel([])
    agent = SoulVietAgentGraph(memory=AgentMemory(tmp_path), model=model)
    state = {
        "messages": [read_call("too-many")],
        "tool_call_count": agent.MAX_TOOL_CALLS,
    }

    updates = agent._execute_tools(state)

    assert updates["outcome"] == "tool_error"
    assert updates["auto_finalize"] is True
    assert agent._route_after_tools(updates) == "finalize"


def test_locality_nearby_filter_and_boundary_use_the_same_predicate():
    places = [
        {"id": "direct", "name": "Phố cổ Hội An", "address": "Hội An", "lat": 15.88, "lng": 108.33},
        {"id": "near", "name": "Bãi biển", "address": "", "lat": 15.89, "lng": 108.34},
        {"id": "far", "name": "Điểm xa", "address": "", "lat": 16.20, "lng": 108.50},
    ]
    locality = ResolvedLocality.resolve(places, "Hội An", "nearby", 8)

    assert locality.is_direct(places[0])
    assert locality.contains(places[1])
    assert not locality.contains(places[2])
    assert {place["id"] for place in locality.filter(places)} == {"direct", "near"}


def test_name_anchor_expands_one_hop_through_near_relationship():
    places = [
        {
            "id": "anchor", "name": "Mũi Nhỏ", "address": "Đà Nẵng",
            "region": "Đà Nẵng", "lat": 16.1, "lng": 108.3,
        },
        {
            "id": "neighbor", "name": "Bãi đá", "address": "Đà Nẵng",
            "region": "Đà Nẵng", "lat": 16.11, "lng": 108.31,
        },
    ]
    edges = {
        "anchor": [{"to": "neighbor", "distance": 1.5}],
        "neighbor": [{"to": "anchor", "distance": 1.5}],
    }

    scope = ResolvedLocality.resolve_scope(places, "Mũi Nhỏ")
    locality = ResolvedLocality.resolve(
        places,
        "Mũi Nhỏ",
        "nearby",
        8,
        neighbor_lookup=lambda place_id: edges.get(place_id, []),
    )

    assert scope["region"] == "Đà Nẵng"
    assert scope["match_source"] == "name_fallback"
    assert {place["id"] for place in locality.filter(places)} == {
        "anchor", "neighbor",
    }


def test_locality_name_does_not_override_conflicting_address():
    places = [{
        "id": "false-positive",
        "name": "Đình làng Hội An",
        "address": "Sơn Cẩm Hà, Đà Nẵng, Việt Nam",
        "region": "Đà Nẵng",
        "lat": 15.9,
        "lng": 108.2,
    }]

    locality = ResolvedLocality.resolve(places, "Hội An", "strict", 8)

    assert locality.found is False
    assert locality.filter(places) == []


def test_locality_scope_resolves_region_from_all_graph_places():
    places = [
        {
            "id": "danang-name-only",
            "name": "Đình làng Hội An",
            "address": "Đà Nẵng, Việt Nam",
            "region": "Đà Nẵng",
        },
        {
            "id": "hoi-an-address",
            "name": "Nhà cổ",
            "address": "Minh An, Hội An, Quảng Nam, Việt Nam",
            "region": "Quảng Nam",
        },
    ]

    scope = ResolvedLocality.resolve_scope(places, "Hội An")

    assert scope["region"] == "Quảng Nam"
    assert scope["candidate_count"] == 1
    assert scope["match_source"] == "administrative"
