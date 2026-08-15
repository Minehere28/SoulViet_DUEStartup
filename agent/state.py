from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class SoulVietAgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    user_id: str
    thread_id: str
    current_request: dict
    current_itinerary: list[dict]
    working_request: dict | None
    working_constraints: dict
    working_itinerary: list[dict] | None
    retrieved_memories: list[dict]
    validation_report: dict | None
    dirty: bool
    committed: bool
    iteration_count: int
    tool_call_count: int
    last_tool_names: list[str]
    last_tool_observations: list[dict]
    auto_finalize: bool
    error: dict | None
