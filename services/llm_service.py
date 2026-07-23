import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

class LLMService:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model_id = "arcee-ai/trinity-large-preview:free"  
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    def generate_itinerary_text(self, itinerary_data, user_vibe, weather):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
 
        prompt = f"""
        Bạn là Trinity, trợ lý du lịch của SoulViet.
        Thời tiết hiện tại: {weather}.
        Yêu cầu của khách: Thích phong cách {user_vibe}.
        
        Đây là danh sách địa điểm đã chọn:
        {json.dumps(itinerary_data, ensure_ascii=False)}

        Hãy viết một bài giới thiệu hành trình cực kỳ lôi cuốn, có tâm. 
        Mô tả từng ngày nên đi đâu, cảm nhận không khí thế nào. 
        Lưu ý: Nếu thời tiết xấu, hãy dặn khách chuẩn bị ô hoặc đổi lịch đi cafe.
        Văn phong: Gần gũi, sành điệu, đậm chất văn hóa Việt Nam.
        """

        payload = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        response = requests.post(self.url, headers=headers, data=json.dumps(payload))
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return f"Lỗi gọi AI: {response.text}"