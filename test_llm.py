from services.llm_service import LLMService

llm = LLMService()

# fake data   
itinerary_data = [
    {
        "day": 1,
        "locations": [
            {
                "name": "Biển Mỹ Khê",
                "vibe": ["chill", "biển"],
                "rating": 4.7,
                "description": "Bãi biển đẹp, nước trong xanh, rất chill"
            },
            {
                "name": "Cafe Sơn Trà",
                "vibe": ["cafe", "chill"],
                "rating": 4.5,
                "description": "View núi và biển cực đẹp"
            }
        ]
    },
    {
        "day": 2,
        "locations": [
            {
                "name": "Bà Nà Hills",
                "vibe": ["checkin", "du lịch"],
                "rating": 4.6,
                "description": "Khu du lịch nổi tiếng với cầu Vàng"
            }
        ]
    }
]

result = llm.generate_itinerary_text(
    itinerary_data=itinerary_data,
    user_vibe="chill",
    weather="Trời nắng đẹp"
)

print(result)