from fastapi import APIRouter

from models.assistant_request import AssistantRequest
from services.langgraph_assistant_service import LangGraphAssistantService


router = APIRouter(prefix="/assistant", tags=["assistant"])
assistant_service = LangGraphAssistantService()


@router.post("/chat")
def customize_itinerary(request: AssistantRequest):
    return assistant_service.customize(request)
