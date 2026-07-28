from fastapi import APIRouter
from services.itinerary_service import ItineraryService
from models.user_request import UserRequest

router = APIRouter()

itinerary_service = ItineraryService()

@router.post("/plan")
def plan_trip(request: dict):

    user = UserRequest(request)

    clusters = itinerary_service.build(user)

    result = []
    for i, day in enumerate(clusters):
        result.append({
            "day": i + 1,
            "places": [
                {
                    "id": place["id"],
                    "name": place["name"],
                    "lat": place["lat"],
                    "lng": place["lng"],
                    "rating": place["rating"],
                }
                for place in day
            ],
        })

    return {"itinerary": result}
