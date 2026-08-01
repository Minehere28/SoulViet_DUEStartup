import re

from models.user_request import RegionName, UserRequest, VibeName
from services.itinerary_service import ItineraryService
from services.llm_service import LLMService
from typing import get_args


class AssistantService:
    def __init__(self, itinerary=None, llm=None):
        self.itinerary = itinerary or ItineraryService()
        self.llm = llm or LLMService()

    def _extract_adjustments(self, message, current_request):
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

        budget_aliases = {
            "tiết kiệm": "economy",
            "bình dân": "economy",
            "tiêu chuẩn": "standard",
            "cao cấp": "premium",
            "premium": "premium",
        }
        for keyword, level in budget_aliases.items():
            if keyword in normalized:
                updates["budget_level"] = level
                applied.append(f"mức ngân sách {keyword}")
                break

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

        remove_requested = re.search(
            r"\b(?:bỏ|xóa|loại|không\s+(?:đi|ghé))\b",
            normalized,
        )
        if remove_requested:
            excluded = set(current_request.excluded_place_ids)
            candidates = [
                place
                for place in self.itinerary.graph.get_all_places()
                if place["region"] == current_request.region
                and place["name"].casefold() in normalized
            ]
            candidates.sort(key=lambda place: len(place["name"]), reverse=True)
            if candidates:
                selected = candidates[0]
                excluded.add(selected["id"])
                updates["excluded_place_ids"] = sorted(excluded)
                applied.append(f"bỏ địa điểm {selected['name']}")

        return updates, applied

    def customize(self, assistant_request):
        updates, applied = self._extract_adjustments(
            assistant_request.message,
            assistant_request.current_request,
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
