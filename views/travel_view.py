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
            "start_location": day["start_location"],
            "total_distance_km": day["total_distance_km"],
            "total_travel_time_minutes": day[
                "total_travel_time_minutes"
            ],
            "travel_time_source": day["travel_time_source"],
            "routing_fallback_reason": day[
                "routing_fallback_reason"
            ],
            "route_optimization_source": day[
                "route_optimization_source"
            ],
            "route_optimization_objective": day[
                "route_optimization_objective"
            ],
            "estimated_spend_min": day["estimated_spend_min"],
            "estimated_spend_max": day["estimated_spend_max"],
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
                    "travel_time_source": place[
                        "travel_time_source"
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
                    "spend_min": place["spend_min"],
                    "spend_max": place["spend_max"],
                    "price_unit": place["price_unit"],
                    "price_source": place["price_source"],
                    "price_confidence": place["price_confidence"],
                    "price_verification_status": place[
                        "price_verification_status"
                    ],
                }
                for place in places
            ],
        })

    return {"itinerary": result}
