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
    for day_data in result["days"]:  
        summary.append({
            "day": day_data["day"],
            "places": [p["name"] for p in day_data["locations"]]  
        })

    return {
        "status": "success",
        "data": {
            "itinerary_summary": summary,
            "ai_suggestion": result["ai_content"]
        }
    }