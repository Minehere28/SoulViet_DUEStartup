import re
from datetime import time
from typing import get_args

from models.assistant_intent import (
    AssistantIntent,
    GraphQueryPlan,
    PlaceOperation,
)
from models.user_request import (
    CategoryConstraint,
    RegionName,
    UserRequest,
    VibeName,
)
from services.graph_query_service import GraphQueryService
from services.itinerary_service import ItineraryService
from services.itinerary_validator import ItineraryValidator
from services.llm_service import LLMService
from services.place_requirement_service import PlaceRequirementService
from utils.place_matching import normalize_command_text, normalize_text


class AssistantService:
    MAX_QUERY_ATTEMPTS = 5

    CATEGORY_ALIASES = {
        "bai bien": "Biển & Hoạt động dưới nước",
        "bien": "Biển & Hoạt động dưới nước",
        "van hoa": "Văn hóa & Lịch sử",
        "lich su": "Văn hóa & Lịch sử",
        "thien nhien": "Thiên nhiên & Ngắm cảnh",
        "thu gian": "Thư giãn & Chăm sóc sức khỏe",
    }
    EXCLUDED_TYPE_ALIASES = {
        "chua": "place_of_worship",
        "den": "place_of_worship",
        "tam linh": "place_of_worship",
    }

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
        self.place_requirements = PlaceRequirementService(
            self.itinerary.graph
        )

    @staticmethod
    def _normalize_text(value):
        return normalize_text(value)

    def _named_places_in_message(self, message):
        normalized = self._normalize_text(message)
        matches = []
        for place in self.itinerary.graph.get_all_places():
            name = self._normalize_text(place.get("name"))
            if len(name) >= 4 and re.search(
                rf"(?:^|\s){re.escape(name)}(?:$|\s)", normalized
            ):
                matches.append(place)
        matches.sort(key=lambda place: len(place.get("name", "")), reverse=True)
        selected = []
        selected_names = []
        for place in matches:
            normalized_name = self._normalize_text(place.get("name"))
            if any(normalized_name in name for name in selected_names):
                continue
            selected.append(place)
            selected_names.append(normalized_name)
        return selected

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

        normalized_ascii = normalize_command_text(message)
        remove_requested = re.search(
            r"\b(?:bo|xoa|loai|khong\s+(?:di|ghe))\b",
            normalized_ascii,
        )
        if remove_requested:
            excluded = set(current_request.excluded_place_ids)
            candidates = [
                place
                for place in self._named_places_in_message(message)
                if place["region"] == current_request.region
            ]
            for selected in candidates:
                excluded.add(selected["id"])
                applied.append(f"bỏ địa điểm {selected['name']}")
            if candidates:
                updates["excluded_place_ids"] = sorted(excluded)

        add_requested = re.search(
            r"\b(?:them|ghe|bat buoc|nhat dinh|phai di|muon di)\b",
            normalized_ascii,
        )
        if add_requested:
            required = set(current_request.required_place_ids)
            candidates = [
                place
                for place in self._named_places_in_message(message)
                if place["region"] == current_request.region
            ]
            for selected in candidates:
                required.add(selected["id"])
                applied.append(f"thêm địa điểm {selected['name']}")
            if candidates:
                updates["required_place_ids"] = sorted(required)

        return updates, applied

    @classmethod
    def _fallback_graph_query(cls, message):
        normalized = normalize_command_text(message)
        keywords = [
            alias for alias in cls.CATEGORY_ALIASES
            if re.search(rf"(?:^|\s){re.escape(alias)}(?:$|\s)", normalized)
        ]
        categories = sorted({cls.CATEGORY_ALIASES[item] for item in keywords})
        nearby = any(
            phrase in normalized
            for phrase in ("it di chuyen", "gan nhau", "gan hon", "quanh day")
        )

        excluded_types = []
        for alias, place_type in cls.EXCLUDED_TYPE_ALIASES.items():
            pattern = (
                rf"(?:khong(?:\s+muon)?\s+(?:di|ghe)|bo\s+cac|loai\s+(?:bo\s+)?(?:cac\s+)?)"
                rf"\s+{re.escape(alias)}(?:\s+nao)?(?:$|[,.]|\s+(?:va|nhung|khoi))"
            )
            if re.search(pattern, normalized):
                excluded_types.append(place_type)

        constraints = []
        for alias, category in cls.CATEGORY_ALIASES.items():
            match = re.search(
                rf"(?:(dung|it nhat|toi da|khong qua|khoang)\s+)?"
                rf"(\d{{1,2}})\s+(?:dia diem\s+)?{re.escape(alias)}(?:$|\s)",
                normalized,
            )
            if not match:
                continue
            qualifier = match.group(1) or "dung"
            count = int(match.group(2))
            if qualifier == "khoang":
                constraint = CategoryConstraint(
                    category=category, target_count=count, mode="soft"
                )
            elif qualifier == "it nhat":
                constraint = CategoryConstraint(
                    category=category, min_count=count
                )
            elif qualifier in {"toi da", "khong qua"}:
                constraint = CategoryConstraint(
                    category=category, max_count=count
                )
            else:
                constraint = CategoryConstraint(
                    category=category, min_count=count, max_count=count
                )
            constraints.append(constraint)

        if categories and not constraints and not any(
            phrase in normalized
            for phrase in ("chi muon", "chi di", "toan", "tat ca")
        ):
            constraints = [
                CategoryConstraint(
                    category=category,
                    min_count=1,
                    target_count=1,
                    mode="hard",
                )
                for category in categories
            ]

        return GraphQueryPlan(
            keywords=keywords,
            activity_categories=categories,
            excluded_types=sorted(set(excluded_types)),
            category_constraints=constraints,
            expand_near=nearby,
            near_hops=1 if nearby else 0,
            include_similar=bool(keywords),
        )

    @staticmethod
    def _merge_query_plans(primary, fallback):
        def merged_values(first, second):
            return list(dict.fromkeys([*first, *second]))

        constraints = {
            rule.category.casefold(): rule
            for rule in primary.category_constraints
        }
        for rule in fallback.category_constraints:
            constraints.setdefault(rule.category.casefold(), rule)
        return primary.model_copy(update={
            "keywords": merged_values(primary.keywords, fallback.keywords),
            "activity_categories": merged_values(
                primary.activity_categories, fallback.activity_categories
            ),
            "required_place_names": merged_values(
                primary.required_place_names, fallback.required_place_names
            ),
            "excluded_place_names": merged_values(
                primary.excluded_place_names, fallback.excluded_place_names
            ),
            "excluded_types": merged_values(
                primary.excluded_types, fallback.excluded_types
            ),
            "excluded_activity_categories": merged_values(
                primary.excluded_activity_categories,
                fallback.excluded_activity_categories,
            ),
            "category_constraints": list(constraints.values()),
            "expand_near": primary.expand_near or fallback.expand_near,
            "near_hops": max(primary.near_hops, fallback.near_hops),
            "include_similar": (
                primary.include_similar or fallback.include_similar
            ),
        })

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

        # Compatibility for injected legacy adapters used by older integrations.
        # The production LLMService always exposes parse_intent and never enters
        # this deterministic branch.
        legacy_adapter = not hasattr(self.llm, "parse_intent")
        use_fallback = legacy_adapter or (parsed_intent is None)
        rule_updates = {}
        applied = []
        mentioned_required_ids = set()
        fallback_query = GraphQueryPlan()
        fallback_meal_preferences = []
        fallback_operations = []
        requested_place_target = None
        policy_label = None
        if use_fallback:
            rule_updates, applied = self._extract_adjustments(
                assistant_request.message,
                assistant_request.current_request,
            )
            required_mentions = self.place_requirements.resolve(
                assistant_request.message,
                assistant_request.current_request.region,
            )
            mentioned_required_ids = {
                place["id"] for place in required_mentions
            }
            if required_mentions:
                rule_updates["required_place_ids"] = sorted({
                    *assistant_request.current_request.required_place_ids,
                    *rule_updates.get("required_place_ids", []),
                    *mentioned_required_ids,
                })
                for place in required_mentions:
                    applied.append(f"thêm địa điểm {place['name']}")
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
            if use_fallback and (
                rule_updates
                or fallback_query.is_active()
                or fallback_meal_preferences
                or fallback_operations
                or policy_label
                or self._question_like(assistant_request.message)
            ):
                if policy_label:
                    applied.append(policy_label)
                parsed_intent = AssistantIntent(
                    intent=(
                        "question"
                        if self._question_like(assistant_request.message)
                        and not (
                            rule_updates
                            or fallback_query.is_active()
                            or fallback_meal_preferences
                            or fallback_operations
                            or policy_label
                        )
                        else "modify_itinerary"
                    ),
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
            else:
                return {
                    "answer": (
                        "Mình chưa thể hiểu và thực thi yêu cầu vì LLM tool-calling "
                        "không khả dụng. Hãy kiểm tra GROQ_API_KEY và model có "
                        "hỗ trợ tools."
                    ),
                    "provider": "tool_call_unavailable",
                    "model": None,
                    "fallback_reason": "LLM did not return a valid tool call",
                    "usage": None,
                    "intent": "unknown",
                    "applied_changes": [],
                    "request": raw_current_request,
                    "itinerary": current_itinerary,
                    "query_metadata": None,
                    "validation_report": None,
                }

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

        query = self._merge_query_plans(
            parsed_intent.graph_query, fallback_query
        ) if legacy_adapter else parsed_intent.graph_query
        persistent_constraints = {
            rule.category.casefold(): rule
            for rule in updated_request.category_constraints
        }
        for rule in query.category_constraints:
            persistent_constraints[rule.category.casefold()] = rule
        query = query.model_copy(update={
            "category_constraints": list(persistent_constraints.values())
        })
        requested_candidates = (
            updated_request.duration * updated_request.max_places_per_day
        )
        query = query.model_copy(update={
            "candidate_limit": min(
                87,
                max(query.candidate_limit, (requested_candidates * 5 + 1) // 2),
            )
        })

        resolved = self.graph_query.resolve_constraints(updated_request, query)
        required_ids = set(updated_request.required_place_ids)
        required_ids.update(resolved["required_place_ids"])
        excluded_ids = set(updated_request.excluded_place_ids)
        excluded_ids.update(resolved["excluded_place_ids"])
        required_ids.difference_update(excluded_ids)
        anchor_ids = list(dict.fromkeys([
            *mentioned_required_ids,
            *resolved["required_place_ids"],
        ]))[:5]
        if anchor_ids:
            query = query.model_copy(update={
                "seed_place_ids": list(dict.fromkeys([
                    *query.seed_place_ids,
                    *anchor_ids,
                ]))[:5],
                "include_similar": True,
                "expand_near": True,
                "near_hops": 1,
            })
        constraint_map = {
            rule.category.casefold(): rule
            for rule in updated_request.category_constraints
        }
        for rule in query.category_constraints:
            constraint_map[rule.category.casefold()] = rule
        updated_request = UserRequest.model_validate({
            **updated_request.model_dump(),
            "required_place_ids": sorted(required_ids),
            "excluded_place_ids": sorted(excluded_ids),
            "excluded_place_types": sorted(set([
                *updated_request.excluded_place_types,
                *query.excluded_types,
            ])),
            "excluded_activity_categories": sorted(set([
                *updated_request.excluded_activity_categories,
                *query.excluded_activity_categories,
            ])),
            "category_constraints": list(constraint_map.values()),
        })
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
        attempt_history = []
        itinerary = []
        validation_report = None
        working_query = query
        protected_seed_ids = list(query.seed_place_ids)
        semantic_refinement = None
        semantic_classifier_used = False
        candidate_semantic_categories = {}
        for attempt in range(self.MAX_QUERY_ATTEMPTS):
            candidate_ids = retained_attraction_ids
            if working_query.is_active():
                query_metadata = self.graph_query.search(
                    updated_request, working_query
                )
                has_semantic_request = bool(
                    working_query.keywords
                    or working_query.types
                    or working_query.activity_categories
                    or working_query.vibes
                )
                if (
                    has_semantic_request
                    and not semantic_classifier_used
                    and query_metadata.get("semantic_match_count", 0) == 0
                    and hasattr(self.llm, "classify_place_matches")
                ):
                    semantic_classifier_used = True
                    shortlist = self.graph_query.semantic_candidates(
                        updated_request, working_query, limit=30
                    )
                    semantic_refinement = self.llm.classify_place_matches(
                        assistant_request.message, shortlist
                    )
                    matched_ids = list(dict.fromkeys(
                        (semantic_refinement or {}).get(
                            "matched_place_ids", []
                        )
                    ))[:5]
                    if matched_ids:
                        semantic_labels = list(dict.fromkeys([
                            *working_query.activity_categories,
                            *(
                                rule.category
                                for rule in working_query.category_constraints
                            ),
                        ]))
                        for place_id in matched_ids:
                            candidate_semantic_categories[place_id] = (
                                semantic_labels
                            )
                        protected_seed_ids = list(dict.fromkeys([
                            *protected_seed_ids,
                            *matched_ids,
                        ]))[:5]
                        working_query = working_query.model_copy(update={
                            "seed_place_ids": protected_seed_ids,
                        })
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
                candidate_semantic_categories=(
                    candidate_semantic_categories
                ),
            )
            validation_report = self.validator.validate(
                itinerary, updated_request
            )
            if resolved["unresolved_required_place_names"]:
                validation_report["acceptable"] = False
                validation_report["status"] = "partial"
                validation_report["quality_violations"] = sorted(set([
                    *validation_report["quality_violations"],
                    "required_place_not_found",
                ]))
                validation_report["metrics"][
                    "unresolved_required_place_names"
                ] = resolved["unresolved_required_place_names"]
            if requested_place_target:
                max_day_attractions = max((
                    sum(
                        place.get("item_type") != "meal"
                        for place in day.get("places", [])
                    )
                    for day in itinerary
                ), default=0)
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
            attempt_history.append({
                "attempt": attempt + 1,
                "candidate_count": (
                    query_metadata.get("candidate_count")
                    if query_metadata
                    else None
                ),
                "status": validation_report.get("status"),
                "quality_violations": validation_report.get(
                    "quality_violations", []
                ),
                "query": working_query.model_dump(mode="json"),
            })
            if (
                validation_report["valid"]
                and validation_report.get("acceptable", True)
            ):
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
            base_query = revised_query or working_query
            update = {
                "seed_place_ids": protected_seed_ids,
                "required_place_names": query.required_place_names,
                "excluded_place_names": query.excluded_place_names,
                "excluded_types": query.excluded_types,
                "excluded_activity_categories": (
                    query.excluded_activity_categories
                ),
                "category_constraints": query.category_constraints,
                "candidate_limit": min(
                    90, max(base_query.candidate_limit, query.candidate_limit) + 8
                ),
            }
            if attempt == 0:
                update["include_similar"] = True
            elif attempt == 1:
                update["include_similar"] = True
            elif attempt == 2:
                update.update({"expand_near": True, "near_hops": 1})
            elif attempt == 3:
                update.update({
                    "keywords": [],
                    "types": [],
                    "activity_categories": [],
                    "vibes": [],
                    "include_similar": True,
                })
            working_query = base_query.model_copy(update=update)

        if query_metadata is None:
            query_metadata = {}
        query_metadata.update({
            "attempts": len(attempt_history),
            "attempt_history": attempt_history,
            "semantic_classifier_used": semantic_classifier_used,
            "semantic_refinement": semantic_refinement,
            **resolved,
        })

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
