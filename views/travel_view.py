from fastapi import APIRouter
from services.data_service import DataService
from services.itinerary_service import ItineraryService
from models.user_request import UserRequest

router = APIRouter()

data_service = DataService("dataset/SoulViet_Dataset.csv")
places = data_service.load()

itinerary_service = ItineraryService(places)

@router.post("/plan")
def plan_trip(request: dict):
    user = UserRequest(request)

    clusters = itinerary_service.build(user)

    result = []
    for i, day in enumerate(clusters):
        result.append({
            "day": i + 1,
            "places": [p.name for p in day]
        })

    return {"itinerary": result}