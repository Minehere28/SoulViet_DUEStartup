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
            "Không tạo ID địa điểm. Chỉ dùng place_id có trong current_itinerary. "
            "Dùng graph_query để mô tả sở thích tìm kiếm; NEAR tối đa một hop, "
            "candidate_limit tối đa 24. Nếu câu lệnh mơ hồ, đặt "
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
            "tối đa một hop và candidate_limit tối đa 24."
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
            return GraphQueryPlan.model_validate(
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
    def local_question_reply(itinerary):
        if not itinerary:
            return "Mình chưa có lịch trình hiện tại để đánh giá."
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
        return (
            f"Lịch hiện tại có {len(itinerary)} ngày, {place_count} điểm tham quan, "
            f"tổng quãng đường khoảng {distance:.1f} km và chi phí ước tính "
            f"{spend_min_text}–{spend_max_text} đồng/người."
        )

    def answer_question(self, message, itinerary, request_data):
        fallback = self.local_question_reply(itinerary)
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
