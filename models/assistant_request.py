from pydantic import BaseModel, ConfigDict, Field
from uuid import uuid4

from models.user_request import UserRequest


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=1000)
    user_id: str = Field(
        default_factory=lambda: f"anonymous-{uuid4()}",
        min_length=3,
        max_length=120,
    )
    thread_id: str = Field(
        default_factory=lambda: f"thread-{uuid4()}",
        min_length=3,
        max_length=120,
    )
    current_request: UserRequest
    current_itinerary: list[dict] = Field(default_factory=list, max_length=14)
