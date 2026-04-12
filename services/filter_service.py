class FilterService:

    def __init__(self):
        self.vibe_map = {
            "chill": ["Chữa lành & Yên bình"],
            "food": ["Ẩm thực & Đặc sản"],
            "culture": ["Đậm văn hóa & Bản địa"],
            "adventure": ["Năng động & Phiêu lưu"],
            "creative": ["Sáng tạo & Truyền cảm hứng"],
            "spiritual": ["Tâm linh & Tín ngưỡng"]
        }

    def match_vibe(self, user_vibe, place_vibes):
        mapped = self.vibe_map.get(user_vibe.lower(), [])

        for v in place_vibes:
            if v in mapped:
                return True

        return False