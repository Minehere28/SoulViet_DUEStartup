from groq import Groq

import os

from dotenv import load_dotenv

load_dotenv()


class LLMService:

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        
        # Thêm dòng này để kiểm tra xem key có được load không
        print("====== DEBUG GROQ_API_KEY ======")
        print(f"Value: {api_key}")
        print(f"Type: {type(api_key)}")
        print("================================")

        self.client = Groq(
            api_key=api_key
        )

    def generate_itinerary_text(
        self,
        itinerary_data,
        user
    ):

        prompt = f"""
Bạn là SoulViet AI.

Hãy viết lịch trình du lịch tự nhiên,
thực tế,
logic,
không bịa thêm địa điểm.

======== USER ========

Vibe:
{user.vibe}

Budget:
{user.budget}

Duration:
{user.duration} ngày

======== ITINERARY ========

{itinerary_data}

======== RULES ========

- CHỈ được sử dụng các địa điểm có trong itinerary
- Không tự thêm nhà hàng/quán cafe không tồn tại
- Không bịa địa điểm mới
- Các địa điểm đã được sắp xếp gần nhau
- Viết theo:
  + sáng
  + chiều
  + tối

- Không cần quá văn vẻ
- Viết giống app travel thật
- Ưu tiên practical
- Có tip nhỏ
- Có gợi ý chụp ảnh
- Không teleport khoảng cách xa
- Không lặp ý
- Không markdown
- Ưu tiên tính thực tế hơn văn vẻ
- Không mô tả cảm xúc quá nhiều
- Không viết như blog du lịch
- Mỗi phần chỉ 2-3 câu
- Tập trung flow di chuyển hợp lý
"""

        try:

            completion = (
                self.client.chat.completions.create(

                    model="openai/gpt-oss-120b",

                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],

                    temperature=0.8,

                    max_completion_tokens=2048,

                    top_p=1,

                    stream=False
                )
            )

            return (
                completion
                .choices[0]
                .message
                .content
            )

        except Exception as e:

            print(
                "❌ GROQ ERROR:",
                e
            )

            return (
                "AI đang bận 😭"
            )