import re

from models.user_request import RegionName, UserRequest, VibeName
from services.itinerary_service import ItineraryService
from services.llm_service import LLMService
from typing import get_args


class AssistantService:
    def __init__(self, itinerary=None, llm=None):
        self.itinerary = itinerary or ItineraryService()
        self.llm = llm or LLMService()

    @staticmethod
    def _extract_adjustments(message):
        normalized = message.casefold()
        updates = {}
        applied = []

        duration_match = re.search(r"(\d{1,2})\s*ngày", normalized)
        if duration_match:
            duration = int(duration_match.group(1))
            if 1 <= duration <= 14:
                updates["duration"] = duration
                applied.append(f"thời lượng {duration} ngày")

        place_match = re.search(
            r"(\d)\s*(?:địa\s*điểm|điểm)(?:\s*mỗi\s*ngày)?",
            normalized,
        )
        if place_match:
            max_places = int(place_match.group(1))
            if 1 <= max_places <= 6:
                updates["max_places_per_day"] = max_places
                applied.append(f"tối đa {max_places} địa điểm/ngày")

        distance_match = re.search(
            r"(\d+(?:[.,]\d+)?)\s*km",
            normalized,
        )
        if distance_match:
            distance = float(distance_match.group(1).replace(",", "."))
            if 0 < distance <= 100:
                updates["max_daily_distance_km"] = distance
                applied.append(f"quãng đường tối đa {distance:g} km/ngày")

        for region in get_args(RegionName):
            if region.casefold() in normalized:
                updates["region"] = region
                applied.append(f"khu vực {region}")
                break

        for vibe in get_args(VibeName):
            if vibe.casefold() in normalized:
                updates["vibe"] = vibe
                applied.append(f"vibe {vibe}")
                break

        return updates, applied

    def customize(self, assistant_request):
        updates, applied = self._extract_adjustments(
            assistant_request.message
        )
        raw_request = assistant_request.current_request.model_dump()
        raw_request.update(updates)
        updated_request = UserRequest.model_validate(raw_request)
        itinerary = self.itinerary.build(updated_request)
        llm_result = self.llm.chat(
            assistant_request.message,
            itinerary,
            updated_request.model_dump(mode="json"),
            applied,
        )
        return {
            **llm_result,
            "applied_changes": applied,
            "request": updated_request.model_dump(mode="json"),
            "itinerary": itinerary,
        }
