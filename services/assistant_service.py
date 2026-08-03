import re
from datetime import time
from typing import get_args

from models.assistant_intent import (
    AssistantIntent,
    GraphQueryPlan,
    PlaceOperation,
)
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
            r"(?:bắt\s*đầu|xuất\s*phát|khởi\s*hành)\s*"
            r"(?:lúc\s*)?(\d{1,2})(?::(\d{2}))?\s*(?:giờ|h)?"
            r"|(?:đi|tham\s*quan)\s+từ\s+"
            r"(\d{1,2})(?::(\d{2}))?\s*(?:giờ|h)?",
            normalized,
        )
        if start_time_match:
            hour = int(start_time_match.group(1) or start_time_match.group(3))
            minute = int(
                start_time_match.group(2)
                or start_time_match.group(4)
                or 0
            )
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                updates["day_start_time"] = time(hour, minute)
                applied.append(f"bắt đầu lúc {hour:02d}:{minute:02d}")

        duration_window_match = re.search(
            r"trong\s+(\d+(?:[.,]\d+)?)\s*(?:tiếng|giờ)",
            normalized,
        )
        if duration_window_match:
            duration_minutes = round(
                float(duration_window_match.group(1).replace(",", "."))
                * 60
            )
            start = updates.get(
                "day_start_time", current_request.day_start_time
            )
            end_minutes = start.hour * 60 + start.minute + duration_minutes
            if 0 < duration_minutes and end_minutes < 24 * 60:
                updates["day_end_time"] = time(
                    end_minutes // 60, end_minutes % 60
                )
                applied.append(
                    f"khung thời gian {duration_minutes:g} phút"
                )

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
    def _fallback_meal_preferences(message):
        normalized = message.casefold()
        aliases = {
            "ăn uống": "local_food",
            "ẩm thực": "local_food",
            "đồ ăn địa phương": "local_food",
            "món địa phương": "local_food",
            "đặc sản": "local_food",
            "cà phê": "cafe",
            "cafe": "cafe",
            "café": "cafe",
            "hải sản": "seafood",
            "ăn trưa": "meal",
            "ăn tối": "meal",
            "bữa trưa": "meal",
            "bữa tối": "meal",
            "nhà hàng": "meal",
            "quán ăn": "meal",
        }
        return sorted({
            value for keyword, value in aliases.items()
            if keyword in normalized
        })

    @staticmethod
    def _fallback_operations(message):
        normalized = message.casefold()
        if not re.search(r"\b(?:bỏ|xóa|loại)\b", normalized):
            return []
        match = re.search(
            r"(?:điểm|mục)\s+"
            r"(?:thứ\s*(\d+)|(đầu\s*tiên))"
            r"(?:\s+(?:ở\s+)?ngày\s*(\d+))?",
            normalized,
        )
        if not match:
            return []
        position = int(match.group(1) or 1)
        item_type = "any" if "mục" in match.group(0) else "attraction"
        return [PlaceOperation(
            action="remove",
            day=int(match.group(3) or 1),
            position=position,
            item_type=item_type,
        )]

    @staticmethod
    def _requested_place_target(message):
        normalized = message.casefold()
        match = re.search(
            r"\bđi\s+(\d)\s*(?:địa\s*)?điểm\b", normalized
        )
        if match and any(
            phrase in normalized[max(0, match.start() - 12):match.end()]
            for phrase in ("chỉ đi", "tối đa đi", "không quá")
        ):
            return None
        return int(match.group(1)) if match else None

    @staticmethod
    def _policy_rebuild_label(message):
        normalized = message.casefold()
        if re.search(r"đừng\s+(?:chọn\s+(?:toàn|hết)|để\s+toàn)", normalized):
            return "lọc điểm tham quan chính"
        if re.search(r"(?:đừng|không)\s+lặp", normalized):
            return "loại trùng thương hiệu"
        if re.search(
            r"đừng\s+trả\s+lịch\s+trống|không\s+khả\s+thi.*giảm",
            normalized,
        ):
            return "kiểm tra tính khả thi"
        return None

    @staticmethod
    def _question_like(message):
        normalized = message.strip().casefold()
        return bool(re.search(
            r"^(?:tại sao|vì sao|bao nhiêu|tổng\s+(?:budget|ngân\s*sách|chi\s*phí|quãng\s*đường)|"
            r"ngày\s+nào|hôm\s+nào|lịch này|lịch trình này|đánh giá|giải thích|"
            r"có hợp lý|có ổn|ổn không|có quá dày|có bị trùng|"
            r"có\s+(?:địa\s*điểm|ngày|điểm)\s+nào)",
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
        if operation.item_type != "any":
            places = [
                place for place in places
                if (
                    (place.get("item_type") == "meal")
                    == (operation.item_type == "meal")
                )
            ]
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
        fallback_meal_preferences = self._fallback_meal_preferences(
            assistant_request.message
        )
        fallback_operations = self._fallback_operations(
            assistant_request.message
        )
        requested_place_target = self._requested_place_target(
            assistant_request.message
        )

        policy_label = self._policy_rebuild_label(
            assistant_request.message
        )

        if parsed_intent is None:
            if (
                rule_updates
                or fallback_query.is_active()
                or fallback_meal_preferences
                or fallback_operations
            ):
                parsed_intent = AssistantIntent(
                    intent="modify_itinerary",
                    graph_query=fallback_query,
                    scope=(
                        "meals_only"
                        if fallback_meal_preferences
                        and not fallback_query.is_active()
                        else "full_itinerary"
                    ),
                    meal_preferences=fallback_meal_preferences,
                    operations=fallback_operations,
                )
            elif policy_label:
                applied.append(policy_label)
                parsed_intent = AssistantIntent(
                    intent="modify_itinerary",
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

        meal_preferences = (
            parsed_intent.meal_preferences or fallback_meal_preferences
        )
        if meal_preferences:
            applied.append("đổi ưu tiên ăn uống")
        effective_scope = parsed_intent.scope
        if (
            meal_preferences
            and not query.is_active()
            and not parsed_intent.operations
        ):
            effective_scope = "meals_only"
        retained_attraction_ids = (
            [
                place["id"]
                for day in current_itinerary
                for place in day.get("places", [])
                if place.get("id")
                and place.get("item_type") != "meal"
            ]
            if effective_scope == "meals_only" and current_itinerary
            else None
        )

        query_metadata = None
        itinerary = []
        validation_report = None
        working_query = query
        for attempt in range(self.MAX_QUERY_ATTEMPTS):
            candidate_ids = retained_attraction_ids
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
                    else (
                        {
                            place_id: 100
                            for place_id in retained_attraction_ids
                        }
                        if retained_attraction_ids
                        else None
                    )
                ),
                meal_preferences=meal_preferences,
            )
            validation_report = self.validator.validate(
                itinerary, updated_request
            )
            if requested_place_target:
                max_day_attractions = max(
                    (
                        sum(
                            place.get("item_type") != "meal"
                            for place in day.get("places", [])
                        )
                        for day in itinerary
                    ),
                    default=0,
                )
                validation_report["metrics"][
                    "requested_place_target"
                ] = requested_place_target
                if 0 < max_day_attractions < requested_place_target:
                    validation_report["acceptable"] = False
                    validation_report["status"] = "partial"
                    validation_report["quality_violations"] = sorted(set([
                        *validation_report["quality_violations"],
                        "requested_place_count_unmet",
                    ]))
            if (
                validation_report["valid"]
                and validation_report.get("acceptable", True)
            ):
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
