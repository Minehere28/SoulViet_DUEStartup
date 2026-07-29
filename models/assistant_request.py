from pydantic import BaseModel, ConfigDict, Field

from models.user_request import UserRequest


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=1000)
    current_request: UserRequest
