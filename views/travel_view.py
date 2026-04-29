from fastapi import APIRouter
from services.itinerary_service import ItineraryService
from models.user_request import UserRequest

router = APIRouter()

itinerary_service = ItineraryService()

@router.post("/plan")
def plan_trip(request: dict):

    user = UserRequest(request)

    result = itinerary_service.build(user)

    summary = []

    for day in result["days"]:

        summary.append({

            "day": day["day"],

            "score": day["score"],

            "total_cost": day["total_cost"],

            "total_time": day["total_time"],

            "morning": day["morning"],

            "afternoon": day["afternoon"],

            "evening": day["evening"],

            "route_flow": day["route_flow"]
        })

    return {

        "status": "success",

        "data": {

            "itinerary_summary": summary,

            "ai_suggestion": result["ai_content"]
        }
    }