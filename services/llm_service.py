from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()

class LLMService:
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    def generate_itinerary_text(self, itinerary_data, user_vibe, weather="Trời nắng đẹp, không khí trong lành"):
        # Prompt này copy từ bản test thành công của bạn
        prompt = f"""
Bạn là SoulViet AI – hướng dẫn viên du lịch Việt Nam.

Phong cách: {user_vibe}
Thời tiết: {weather}

Dữ liệu:
{itinerary_data}

Yêu cầu:
- Viết hành trình theo từng ngày
- Có sáng / chiều / tối
- Văn phong tự nhiên, có cảm xúc
- Có tip nhỏ
- Không nói kiểu AI
"""

        try:
            completion = self.client.chat.completions.create(
                model="openai/gpt-oss-120b",  # Dùng đúng model bạn đã test thành công
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_completion_tokens=2048,
                top_p=1,
                stream=False
            )
            return completion.choices[0].message.content
        except Exception as e:
            print("❌ GROQ ERROR:", e)
            return "AI đang bận, đây là lịch trình mẫu: Ngày 1 đi tham quan các làng nghề truyền thống 🌊"