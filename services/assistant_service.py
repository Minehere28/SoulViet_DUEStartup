import re
from datetime import time
from typing import get_args

from models.assistant_intent import AssistantIntent, GraphQueryPlan
from models.user_request import RegionName, UserRequest, VibeName
from services.graph_query_service import GraphQueryService
from services.itinerary_service import ItineraryService
from services.itinerary_validator import ItineraryValidator
from services.llm_service import LLMService


class AssistantService:
    MAX_QUERY_ATTEMPTS = 2

    def __init__(
        self,
        itinerary=None,
        llm=None,
        graph_query=None,
        validator=None,
    ):
        self.itinerary = itinerary or ItineraryService()
        self.llm = llm or LLMService()
        self.graph_query = graph_query or GraphQueryService(
            self.itinerary.graph
        )
        self.validator = validator or ItineraryValidator()

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
            if 1 <= max_places <= 8:
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

        start_time_match = re.search(
            r"(?:bắt\s*đầu|đi)\s*(?:lúc|từ)?\s*(\d{1,2})(?::(\d{2}))?\s*(?:giờ|h)?",
            normalized,
        )
        if start_time_match:
            hour = int(start_time_match.group(1))
            minute = int(start_time_match.group(2) or 0)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                updates["day_start_time"] = time(hour, minute)
                applied.append(f"bắt đầu lúc {hour:02d}:{minute:02d}")

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

    @staticmethod
    def _fallback_graph_query(message):
        normalized = message.casefold()
        category_aliases = {
            "biển": "Biển & Hoạt động dưới nước",
            "ăn uống": "Ẩm thực",
            "ẩm thực": "Ẩm thực",
            "cà phê": "Cà phê & Đồ uống",
            "văn hóa": "Văn hóa & Lịch sử",
            "lịch sử": "Văn hóa & Lịch sử",
            "thiên nhiên": "Thiên nhiên & Ngắm cảnh",
            "thư giãn": "Thư giãn & Chăm sóc sức khỏe",
        }
        keywords = [
            keyword for keyword in category_aliases if keyword in normalized
        ]
        categories = sorted({category_aliases[item] for item in keywords})
        nearby = any(
            phrase in normalized
            for phrase in ("ít di chuyển", "gần nhau", "gần hơn", "quanh đây")
        )
        return GraphQueryPlan(
            keywords=keywords,
            activity_categories=categories,
            expand_near=nearby,
            near_hops=1 if nearby else 0,
            include_similar=bool(keywords),
        )

    @staticmethod
    def _question_like(message):
        normalized = message.strip().casefold()
        return bool(re.search(
            r"^(?:tại sao|vì sao|bao nhiêu|lịch này|lịch trình này|"
            r"đánh giá|giải thích|có hợp lý|có ổn)",
            normalized,
        ))

    @staticmethod
    def _operation_place_id(operation, current_itinerary):
        current_ids = {
            place.get("id")
            for day in current_itinerary
            for place in day.get("places", [])
            if place.get("id")
        }
        if operation.place_id:
            return (
                operation.place_id
                if operation.place_id in current_ids
                else None
            )
        if not operation.day or not operation.position:
            return None
        if operation.day > len(current_itinerary):
            return None
        places = current_itinerary[operation.day - 1].get("places", [])
        if operation.position > len(places):
            return None
        return places[operation.position - 1].get("id")

    @staticmethod
    def _change_labels(updates):
        labels = {
            "duration": "số ngày",
            "vibe": "vibe",
            "region": "khu vực",
            "budget_level": "mức ngân sách",
            "max_places_per_day": "số địa điểm mỗi ngày",
            "max_daily_distance_km": "giới hạn quãng đường",
            "preferred_activities": "hoạt động ưu tiên",
            "start_date": "ngày bắt đầu",
            "day_start_time": "giờ bắt đầu ngày",
            "day_end_time": "giờ kết thúc ngày",
        }
        return [f"đổi {labels[key]}" for key in updates if key in labels]

    def _explain(
        self,
        message,
        itinerary,
        request_data,
        applied,
        validation_report,
        query_metadata,
    ):
        try:
            return self.llm.chat(
                message,
                itinerary,
                request_data,
                applied,
                validation_report=validation_report,
                query_metadata=query_metadata,
            )
        except TypeError:
            # Compatibility for test doubles and older LLM adapters.
            return self.llm.chat(
                message, itinerary, request_data, applied
            )

    def customize(self, assistant_request):
        current_itinerary = assistant_request.current_itinerary
        raw_current_request = assistant_request.current_request.model_dump(
            mode="json"
        )
        parsed_intent = None
        if hasattr(self.llm, "parse_intent"):
            parsed_intent = self.llm.parse_intent(
                assistant_request.message,
                raw_current_request,
                current_itinerary,
            )
        if parsed_intent is not None and not isinstance(
            parsed_intent, AssistantIntent
        ):
            parsed_intent = AssistantIntent.model_validate(parsed_intent)

        rule_updates, applied = self._extract_adjustments(
            assistant_request.message,
            assistant_request.current_request,
        )
        fallback_query = self._fallback_graph_query(
            assistant_request.message
        )

        if parsed_intent is None:
            if rule_updates or fallback_query.is_active():
                parsed_intent = AssistantIntent(
                    intent="modify_itinerary",
                    graph_query=fallback_query,
                )
            elif self._question_like(assistant_request.message):
                parsed_intent = AssistantIntent(intent="question")
            else:
                parsed_intent = AssistantIntent(
                    intent="unknown",
                    needs_clarification=True,
                    clarification_question=(
                        "Bạn muốn hỏi về lịch hiện tại hay muốn thay đổi "
                        "khu vực, hoạt động, thời gian hoặc quãng đường?"
                    ),
                )

        if parsed_intent.intent == "question":
            if hasattr(self.llm, "answer_question"):
                llm_result = self.llm.answer_question(
                    assistant_request.message,
                    current_itinerary,
                    raw_current_request,
                )
            else:
                llm_result = self.llm.chat(
                    assistant_request.message,
                    current_itinerary,
                    raw_current_request,
                    [],
                )
            return {
                **llm_result,
                "intent": "question",
                "applied_changes": [],
                "request": raw_current_request,
                "itinerary": current_itinerary,
                "query_metadata": None,
                "validation_report": None,
            }

        if parsed_intent.needs_clarification or parsed_intent.intent == "unknown":
            return {
                "answer": parsed_intent.clarification_question or (
                    "Bạn có thể nói rõ thay đổi mong muốn không?"
                ),
                "provider": "local_clarification",
                "model": None,
                "fallback_reason": None,
                "usage": None,
                "intent": "unknown",
                "applied_changes": [],
                "request": raw_current_request,
                "itinerary": current_itinerary,
                "query_metadata": None,
                "validation_report": None,
            }

        intent_updates = parsed_intent.request_updates.model_dump(
            exclude_none=True
        )
        updates = {**intent_updates, **rule_updates}
        for label in self._change_labels(intent_updates):
            if label not in applied:
                applied.append(label)

        excluded = set(
            updates.get(
                "excluded_place_ids",
                assistant_request.current_request.excluded_place_ids,
            )
        )
        for operation in parsed_intent.operations:
            place_id = self._operation_place_id(
                operation, current_itinerary
            )
            if place_id:
                excluded.add(place_id)
                applied.append(f"bỏ địa điểm {place_id}")
        if excluded != set(assistant_request.current_request.excluded_place_ids):
            updates["excluded_place_ids"] = sorted(excluded)

        raw_request = assistant_request.current_request.model_dump()
        raw_request.update(updates)
        updated_request = UserRequest.model_validate(raw_request)

        query = parsed_intent.graph_query
        if not query.is_active() and fallback_query.is_active():
            query = fallback_query
        if query.activity_categories and "preferred_activities" not in updates:
            updated_request = UserRequest.model_validate({
                **updated_request.model_dump(),
                "preferred_activities": query.activity_categories,
            })
            applied.append("đổi hoạt động ưu tiên")

        query_metadata = None
        itinerary = []
        validation_report = None
        working_query = query
        for attempt in range(self.MAX_QUERY_ATTEMPTS):
            candidate_ids = None
            if working_query.is_active():
                query_metadata = self.graph_query.search(
                    updated_request, working_query
                )
                candidate_ids = query_metadata["candidate_ids"]
                query_metadata["attempts"] = attempt + 1
                query_metadata["query"] = working_query.model_dump(
                    mode="json"
                )

            itinerary = self.itinerary.build(
                updated_request,
                candidate_ids=candidate_ids,
                candidate_priorities=(
                    query_metadata["priorities"]
                    if query_metadata
                    else None
                ),
            )
            validation_report = self.validator.validate(
                itinerary, updated_request
            )
            has_places = any(day["places"] for day in itinerary)
            if validation_report["valid"] and has_places:
                break
            if not working_query.is_active():
                break
            revised_query = None
            if hasattr(self.llm, "revise_query"):
                revised_query = self.llm.revise_query(
                    assistant_request.message,
                    updated_request.model_dump(mode="json"),
                    working_query,
                    itinerary,
                    validation_report,
                )
            working_query = revised_query or working_query.model_copy(
                update={
                    "candidate_limit": min(
                        24, working_query.candidate_limit + 4
                    ),
                    "include_similar": True,
                }
            )

        llm_result = self._explain(
            assistant_request.message,
            itinerary,
            updated_request.model_dump(mode="json"),
            applied,
            validation_report,
            query_metadata,
        )
        return {
            **llm_result,
            "intent": "modify_itinerary",
            "applied_changes": applied,
            "request": updated_request.model_dump(mode="json"),
            "itinerary": itinerary,
            "query_metadata": query_metadata,
            "validation_report": validation_report,
        }
