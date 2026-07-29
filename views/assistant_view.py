from fastapi import APIRouter

from models.assistant_request import AssistantRequest
from services.assistant_service import AssistantService


router = APIRouter(prefix="/assistant", tags=["assistant"])
assistant_service = AssistantService()


@router.post("/chat")
def customize_itinerary(request: AssistantRequest):
    return assistant_service.customize(request)
