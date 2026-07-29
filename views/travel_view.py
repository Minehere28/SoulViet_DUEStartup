from fastapi import APIRouter
from services.itinerary_service import ItineraryService
from models.user_request import UserRequest

router = APIRouter()

itinerary_service = ItineraryService()

@router.post("/plan")
def plan_trip(request: UserRequest):
    clusters = itinerary_service.build(request)

    result = []
    for i, day in enumerate(clusters):
        places = day["places"]
        result.append({
            "day": i + 1,
            "date": day["date"],
            "weekday": day["weekday"],
            "region": request.region,
            "day_start_time": day["day_start_time"],
            "day_end_time": day["day_end_time"],
            "total_distance_km": day["total_distance_km"],
            "total_travel_time_minutes": day[
                "total_travel_time_minutes"
            ],
            "travel_time_source": day["travel_time_source"],
            "places": [
                {
                    "id": place["id"],
                    "name": place["name"],
                    "region": place["region"],
                    "lat": place["lat"],
                    "lng": place["lng"],
                    "rating": place["rating"],
                    "review_count": place["review_count"],
                    "type": place["type"],
                    "address": place["address"],
                    "activity_categories": place[
                        "activity_categories"
                    ],
                    "main_image": place["main_image"],
                    "recommendation_score": place[
                        "recommendation_score"
                    ],
                    "score_breakdown": place["score_breakdown"],
                    "arrival_time": place["arrival_time"],
                    "departure_time": place["departure_time"],
                    "visit_duration_minutes": place[
                        "visit_duration_minutes"
                    ],
                    "visit_duration_source": place[
                        "visit_duration_source"
                    ],
                    "distance_from_previous_km": place[
                        "distance_from_previous_km"
                    ],
                    "travel_time_minutes": place[
                        "travel_time_minutes"
                    ],
                    "opening_status_for_day": place[
                        "opening_status_for_day"
                    ],
                    "opening_intervals_for_day": place[
                        "opening_intervals_for_day"
                    ],
                    "schedule_verified": place[
                        "schedule_verified"
                    ],
                    "schedule_verification_status": place[
                        "schedule_verification_status"
                    ],
                    "schedule_warnings": place[
                        "schedule_warnings"
                    ],
                }
                for place in places
            ],
        })

    return {"itinerary": result}
