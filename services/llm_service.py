import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from models.assistant_intent import AssistantIntent, GraphQueryPlan


load_dotenv()


class LLMService:
    """OpenRouter intent parser and response writer with local fallbacks."""

    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.model_id = os.getenv(
            "OPENROUTER_MODEL",
            "openai/gpt-5-mini",
        ).strip()
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    @staticmethod
    def _compact_itinerary(itinerary):
        return [
            {
                "day": day.get("day", index + 1),
                "date": day.get("date"),
                "total_distance_km": day.get("total_distance_km"),
                "total_travel_time_minutes": day.get(
                    "total_travel_time_minutes"
                ),
                "estimated_spend_min": day.get("estimated_spend_min"),
                "estimated_spend_max": day.get("estimated_spend_max"),
                "places": [
                    {
                        "id": place.get("id"),
                        "name": place.get("name"),
                        "item_type": place.get("item_type", "attraction"),
                        "meal_slot": place.get("meal_slot"),
                        "arrival_time": place.get("arrival_time"),
                        "departure_time": place.get("departure_time"),
                        "travel_time_minutes": place.get(
                            "travel_time_minutes"
                        ),
                        "distance_from_previous_km": place.get(
                            "distance_from_previous_km"
                        ),
                        "spend_min": place.get("spend_min"),
                        "spend_max": place.get("spend_max"),
                        "schedule_warnings": place.get(
                            "schedule_warnings", []
                        ),
                    }
                    for place in day.get("places", [])
                ],
            }
            for index, day in enumerate(itinerary)
        ]

    def _complete(self, messages, temperature=0.2, max_tokens=700):
        payload = json.dumps(
            {
                "model": self.model_id,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            self.url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://127.0.0.1:8000",
                "X-Title": "SoulViet AI",
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        content = response_payload["choices"][0]["message"]["content"].strip()
        if not content:
            raise ValueError("OpenRouter returned empty content")
        return content, response_payload

    @staticmethod
    def _json_object(content):
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end < start:
            raise ValueError("LLM response does not contain a JSON object")
        return json.loads(content[start:end + 1])

    def parse_intent(self, message, current_request, current_itinerary):
        """Return a validated intent, or None so deterministic rules can run."""
        if not self.api_key:
            return None

        schema = AssistantIntent.model_json_schema()
        system_prompt = (
            "Bạn là bộ phân tích yêu cầu cho SoulViet. Chỉ trả về một JSON object "
            "đúng JSON Schema được cung cấp, không markdown, không giải thích. "
            "Phân loại intent: question nếu người dùng chỉ hỏi về lịch hiện tại; "
            "modify_itinerary nếu họ muốn thay đổi; unknown nếu thiếu thông tin. "
            "Không tạo ID địa điểm. Chỉ dùng place_id có trong current_itinerary; "
            "với điểm mới hãy ghi tên thật vào graph_query.required_place_names. "
            "Các cách nói 'thêm X', 'cần có X', 'muốn có X', 'nhất định ghé X' "
            "đều là yêu cầu bắt buộc: đưa X vào required_place_names, không chỉ "
            "đưa từ khóa chung của X vào activity_categories. "
            "Dùng graph_query để tách sở thích mềm, loại địa điểm/type/category và "
            "category_constraints. Dùng keywords cho tín hiệu trong tên/mô tả, "
            "types cho loại địa điểm, activity_categories cho nhóm hoạt động và "
            "vibes cho không khí. Một sở thích tự nhiên như 'muốn đi biển' là "
            "target mềm một điểm, không phải bắt toàn bộ lịch đều là biển. "
            "Phân biệt đúng, ít nhất, tối đa và khoảng; "
            "NEAR tối đa một hop, candidate_limit tối đa 90. "
            "Tách sở thích ăn uống vào meal_preferences; "
            "nếu chỉ đổi bữa ăn hoặc thêm cà phê thì đặt scope=meals_only. "
            "Nếu câu lệnh mơ hồ, đặt "
            "needs_clarification=true và viết một câu hỏi ngắn."
        )
        user_payload = {
            "message": message,
            "current_request": current_request,
            "current_itinerary": self._compact_itinerary(current_itinerary),
            "json_schema": schema,
        }
        try:
            content, _ = self._complete(
                [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(user_payload, ensure_ascii=False),
                    },
                ],
                temperature=0,
                max_tokens=900,
            )
            return AssistantIntent.model_validate(
                self._json_object(content)
            )
        except (
            HTTPError,
            URLError,
            TimeoutError,
            json.JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ):
            return None

    def revise_query(
        self,
        message,
        current_request,
        query,
        itinerary,
        validation_report,
    ):
        """Let the model revise only the bounded graph query after a failed run."""
        if not self.api_key:
            return None
        system_prompt = (
            "Bạn đang sửa graph query cho SoulViet sau một lần lập lịch chưa đạt. "
            "Chỉ trả về một JSON object đúng GraphQueryPlan schema, không markdown. "
            "Không thay đổi yêu cầu cứng của người dùng, không tạo place ID, NEAR "
            "tối đa một hop và candidate_limit tối đa 90. Không được xóa hoặc nới "
            "required places, exclusions hay hard category constraints."
        )
        payload = {
            "message": message,
            "current_request": current_request,
            "previous_query": query.model_dump(mode="json"),
            "failed_itinerary": self._compact_itinerary(itinerary),
            "validation_report": validation_report,
            "json_schema": GraphQueryPlan.model_json_schema(),
        }
        try:
            content, _ = self._complete(
                [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                ],
                temperature=0,
                max_tokens=600,
            )
            return GraphQueryPlan.model_validate(self._json_object(content))
        except (
            HTTPError,
            URLError,
            TimeoutError,
            json.JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ):
            return None

    def classify_place_matches(self, message, candidates):
        """Classify a bounded candidate list without allowing invented IDs."""
        if not self.api_key or not candidates:
            return None
        allowed_ids = {item["id"] for item in candidates}
        system_prompt = (
            "Bạn kiểm tra candidate địa điểm có thỏa yêu cầu du lịch hay không. "
            "Đánh giá đồng thời tên, type, activities, activity_categories, vibes "
            "và description; không chỉ dựa vào một tag. Chỉ trả JSON object gồm "
            "matched_place_ids (list ID), confidence_by_id (object ID->0..1) và "
            "reason_by_id (object ID->lý do ngắn). Không tạo ID ngoài danh sách."
        )
        payload = {
            "message": message,
            "candidates": candidates,
        }
        try:
            content, _ = self._complete(
                [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                ],
                temperature=0,
                max_tokens=600,
            )
            result = self._json_object(content)
            confidence = result.get("confidence_by_id", {})
            matched_ids = [
                place_id
                for place_id in result.get("matched_place_ids", [])
                if place_id in allowed_ids
                and float(confidence.get(place_id, 0)) >= 0.65
            ]
            reasons = result.get("reason_by_id", {})
            return {
                "matched_place_ids": list(dict.fromkeys(matched_ids)),
                "confidence_by_id": {
                    place_id: float(confidence[place_id])
                    for place_id in matched_ids
                },
                "reason_by_id": {
                    place_id: str(reasons.get(place_id, ""))[:200]
                    for place_id in matched_ids
                },
            }
        except (
            HTTPError,
            URLError,
            TimeoutError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def fallback_reply(itinerary, applied_changes):
        place_count = sum(len(day.get("places", [])) for day in itinerary)
        changes = ", ".join(applied_changes) if applied_changes else (
            "chưa nhận diện được thay đổi cụ thể"
        )
        return (
            f"Mình đã tạo lại hành trình gồm {len(itinerary)} ngày và "
            f"{place_count} điểm dừng. Điều chỉnh: {changes}."
        )

    @staticmethod
    def local_question_reply(message, itinerary):
        if not itinerary:
            return "Mình chưa có lịch trình hiện tại để đánh giá."
        normalized = message.casefold()
        place_count = sum(
            sum(
                place.get("item_type") != "meal"
                for place in day.get("places", [])
            )
            for day in itinerary
        )
        distance = sum(
            float(day.get("total_distance_km") or 0) for day in itinerary
        )
        spend_min = sum(
            int(day.get("estimated_spend_min") or 0) for day in itinerary
        )
        spend_max = sum(
            int(day.get("estimated_spend_max") or 0) for day in itinerary
        )
        spend_min_text = f"{spend_min:,}".replace(",", ".")
        spend_max_text = f"{spend_max:,}".replace(",", ".")
        if any(
            phrase in normalized
            for phrase in ("budget", "ngân sách", "chi phí", "bao nhiêu")
        ):
            return (
                f"Chi phí ước tính của lịch hiện tại là "
                f"{spend_min_text}–{spend_max_text} đồng/người."
            )
        if ("ngày nào" in normalized or "hôm nào" in normalized) and any(
            phrase in normalized for phrase in ("xa", "di chuyển", "quãng đường")
        ):
            day_index, farthest = max(
                enumerate(itinerary, start=1),
                key=lambda item: float(item[1].get("total_distance_km") or 0),
            )
            return (
                f"Ngày {day_index} di chuyển xa nhất, khoảng "
                f"{float(farthest.get('total_distance_km') or 0):.1f} km."
            )
        if "trùng" in normalized:
            ids = [
                place.get("id")
                for day in itinerary
                for place in day.get("places", [])
                if place.get("id")
            ]
            duplicate_count = len(ids) - len(set(ids))
            return (
                "Lịch hiện tại không bị trùng địa điểm."
                if duplicate_count == 0
                else f"Lịch hiện tại có {duplicate_count} địa điểm bị lặp."
            )
        return (
            f"Lịch hiện tại có {len(itinerary)} ngày, {place_count} điểm tham quan, "
            f"tổng quãng đường khoảng {distance:.1f} km và chi phí ước tính "
            f"{spend_min_text}–{spend_max_text} đồng/người."
        )

    def answer_question(self, message, itinerary, request_data):
        fallback = self.local_question_reply(message, itinerary)
        if not self.api_key:
            return {
                "answer": fallback,
                "provider": "local_fallback",
                "model": None,
                "fallback_reason": "OPENROUTER_API_KEY is not configured",
                "usage": None,
            }
        system_prompt = (
            "Bạn là trợ lý du lịch SoulViet. Chỉ trả lời câu hỏi dựa trên JSON "
            "lịch trình. Không thay đổi lịch, không bịa dữ liệu. Trả lời ngắn gọn "
            "bằng tiếng Việt và nêu rõ dữ liệu nào chưa có nếu cần."
        )
        try:
            answer, payload = self._complete(
                [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "message": message,
                                "request": request_data,
                                "itinerary": self._compact_itinerary(itinerary),
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=500,
            )
            return {
                "answer": answer,
                "provider": "openrouter",
                "model": payload.get("model", self.model_id),
                "fallback_reason": None,
                "usage": payload.get("usage"),
            }
        except (HTTPError, URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError) as error:
            return {
                "answer": fallback,
                "provider": "local_fallback",
                "model": None,
                "fallback_reason": error.__class__.__name__,
                "usage": None,
            }

    def chat(
        self,
        message,
        itinerary,
        request_data,
        applied_changes,
        validation_report=None,
        query_metadata=None,
    ):
        fallback = self.fallback_reply(itinerary, applied_changes)
        if not self.api_key:
            return {
                "answer": fallback,
                "provider": "local_fallback",
                "model": None,
                "fallback_reason": "OPENROUTER_API_KEY is not configured",
                "usage": None,
            }

        system_prompt = (
            "Bạn là trợ lý du lịch SoulViet. Trả lời ngắn gọn bằng tiếng Việt. "
            "Không bịa giá, giờ mở cửa hay thời gian đường bộ. Lịch trình trong "
            "JSON đã được backend kiểm tra; không tự thêm, xóa, đổi giờ hoặc đổi "
            "thứ tự. Mô tả đúng applied_changes, kết quả validation và lý do "
            "chọn ứng viên graph. Meal không phải điểm tham quan."
        )
        user_prompt = {
            "message": message,
            "applied_changes": applied_changes,
            "request": request_data,
            "query_metadata": query_metadata,
            "validation_report": validation_report,
            "itinerary": self._compact_itinerary(itinerary),
        }
        try:
            answer, response_payload = self._complete(
                [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(user_prompt, ensure_ascii=False),
                    },
                ],
                temperature=0.3,
                max_tokens=600,
            )
            return {
                "answer": answer,
                "provider": "openrouter",
                "model": response_payload.get("model", self.model_id),
                "fallback_reason": None,
                "usage": response_payload.get("usage"),
            }
        except (HTTPError, URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError) as error:
            return {
                "answer": fallback,
                "provider": "local_fallback",
                "model": None,
                "fallback_reason": error.__class__.__name__,
                "usage": None,
            }
