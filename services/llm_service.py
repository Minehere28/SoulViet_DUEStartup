import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


load_dotenv()


class LLMService:
    """Optional OpenRouter client with a deterministic local fallback."""

    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.model_id = os.getenv(
            "OPENROUTER_MODEL",
            "openai/gpt-5-mini",
        ).strip()
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    @staticmethod
    def fallback_reply(itinerary, applied_changes):
        place_count = sum(len(day["places"]) for day in itinerary)
        changes = ", ".join(applied_changes) if applied_changes else (
            "chưa nhận diện được thay đổi cụ thể"
        )
        return (
            f"Mình đã tạo lại hành trình gồm {len(itinerary)} ngày và "
            f"{place_count} địa điểm. Điều chỉnh: {changes}. "
            "Bạn có thể nói rõ số ngày, khu vực, vibe, số địa điểm "
            "mỗi ngày hoặc bán kính tối đa để mình chỉnh tiếp."
        )

    def chat(self, message, itinerary, request_data, applied_changes):
        fallback = self.fallback_reply(itinerary, applied_changes)
        if not self.api_key:
            return {
                "answer": fallback,
                "provider": "local_fallback",
                "model": None,
                "fallback_reason": "OPENROUTER_API_KEY is not configured",
                "usage": None,
            }

        compact_itinerary = [
            {
                "day": index + 1,
                "date": day["date"],
                "places": [
                    {
                        "name": place["name"],
                        "item_type": place.get("item_type", "attraction"),
                        "meal_slot": place.get("meal_slot"),
                        "arrival_time": place["arrival_time"],
                        "departure_time": place["departure_time"],
                    }
                    for place in day["places"]
                ],
            }
            for index, day in enumerate(itinerary)
        ]
        system_prompt = (
            "Bạn là trợ lý du lịch SoulViet. Trả lời ngắn gọn bằng "
            "tiếng Việt. Không bịa giá, giờ mở cửa hay thời gian đường bộ. "
            "Lịch trình trong JSON đã được bộ giải ràng buộc kiểm tra; không tự ý "
            "thêm, xóa, đổi giờ hoặc đổi thứ tự địa điểm. Phân biệt attraction và "
            "meal: meal không được tính là điểm tham quan. Không cảnh báo chỉ vì "
            "giờ mở cửa có trạng thái unknown; chỉ nêu schedule_warnings đã có. "
            "Nếu người dùng yêu cầu thay đổi, mô tả đúng thay đổi backend đã áp dụng."
        )
        user_prompt = {
            "message": message,
            "applied_changes": applied_changes,
            "request": request_data,
            "itinerary": compact_itinerary,
        }
        try:
            payload = json.dumps(
                {
                    "model": self.model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(
                                user_prompt,
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    "temperature": 0.4,
                    "max_tokens": 500,
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
                response_payload = json.loads(
                    response.read().decode("utf-8")
                )
            answer = response_payload[
                "choices"
            ][0]["message"]["content"].strip()
            if not answer:
                raise ValueError("OpenRouter returned empty content")
            return {
                "answer": answer,
                "provider": "openrouter",
                "model": response_payload.get("model", self.model_id),
                "fallback_reason": None,
                "usage": response_payload.get("usage"),
            }
        except HTTPError as error:
            return {
                "answer": fallback,
                "provider": "local_fallback",
                "model": None,
                "fallback_reason": f"HTTPError_{error.code}",
                "usage": None,
            }
        except (
            URLError,
            TimeoutError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as error:
            return {
                "answer": fallback,
                "provider": "local_fallback",
                "model": None,
                "fallback_reason": error.__class__.__name__,
                "usage": None,
            }
