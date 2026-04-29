from groq import Groq

import os

from dotenv import load_dotenv

load_dotenv()


class LLMService:

    def __init__(self):

        self.client = Groq(
            api_key=os.getenv(
                "GROQ_API_KEY"
            )
        )

    def generate_itinerary_text(
        self,
        itinerary_data,
        user
    ):

        prompt = f"""
Bạn là SoulViet AI.

Hãy viết lịch trình du lịch tự nhiên,
có cảm xúc và giống travel blogger.

======== USER ========

Vibe:
{user.vibe}

Budget:
{user.budget}

Duration:
{user.duration} ngày

======== ITINERARY ========

{itinerary_data}

======== REQUIREMENTS ========

- Viết theo từng ngày
- Có sáng / chiều / tối
- Diễn đạt tự nhiên
- Có storytelling nhẹ
- Có tip nhỏ
- Có gợi ý ăn uống/chụp ảnh
- Không viết như AI
- Không lặp câu
- Không markdown
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