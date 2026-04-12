import math

class ScoringService:
    def calculate(self, place, user):
        # place: là dict đã được normalize từ GraphService
        # user: là object UserRequest
        
        # kiểm tra vibe (vì place["vibes"] là một list)
        # nếu vibe người dùng chọn nằm trong danh sách vibes của địa điểm
        vibe_match = 1 if user.vibe in place.get("vibes", []) else 0
        
        # điểm review (log để giảm bớt sự chênh lệch quá lớn giữa các số lượng review)
        review_count = place.get("review_count", 0)
        review_score = math.log(review_count + 1)
        
        # kiểm tra ngân sách
        price_max = place.get("price_max", 0)
        price_match = 1 if price_max <= user.budget else 0.5

        # tính tổng điểm theo trọng số m có thể sửa ở đây tùy m=)))
        score = (
            place.get("rating", 0) * 0.25 +
            review_score * 0.15 +
            vibe_match * 0.35 +
            price_match * 0.25
        )

        return score