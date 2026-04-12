from services.graph_service import GraphService
from services.llm_service import LLMService
from utils.distance import haversine

class ItineraryService:
    def __init__(self):
        self.graph = GraphService()
        self.llm = LLMService()
        self.vibe_map = {
            "chill": "Chữa lành & Yên bình",
            "food": "Ẩm thực & Đặc sản",
            "culture": "Đậm văn hóa & Bản địa",
            "adventure": "Năng động & Phiêu lưu",
            "creative": "Sáng tạo & Truyền cảm hứng",
            "spiritual": "Tâm linh & Tín ngưỡng"
        }

    def build(self, user):
        mapped_vibe = self.vibe_map.get(user.vibe.lower(), user.vibe)
         
        all_places = self.graph.get_all_places()
        scored_places = []
        for p in all_places:
            vibe_score = 5.0 if mapped_vibe in p["vibes"] else 0.0 
            total_score = vibe_score + (p["rating"] * 2) 
            scored_places.append((p, total_score))
         
        scored_places.sort(key=lambda x: x[1], reverse=True)
         
        final_itinerary = []
        used_ids = set()
        
        for day in range(user.duration):
            day_locations = []
             
            seed_place = None
            for p, score in scored_places:
                if p["id"] not in used_ids:
                    seed_place = p
                    break
            
            if not seed_place:
                break
                
            day_locations.append(seed_place)
            used_ids.add(seed_place["id"])
             
            neighbors = self.graph.get_neighbors(seed_place["id"])
             
            potential_neighbors = []
            for n in neighbors:
                if n["to"] not in used_ids:
                    p_target = self.graph.get_place(n["to"])
                    if p_target:
                        potential_neighbors.append(p_target)
             
            if len(potential_neighbors) < 3:
                for p, score in scored_places:
                    if p["id"] not in used_ids and p["id"] != seed_place["id"]:
                        dist = haversine(seed_place["lat"], seed_place["lng"], p["lat"], p["lng"])
                        if dist < 5:  
                            potential_neighbors.append(p)
                    if len(potential_neighbors) >= 5: break
 
            for p_near in potential_neighbors[:2]:
                if p_near["id"] not in used_ids:
                    day_locations.append(p_near)
                    used_ids.add(p_near["id"])
            
            final_itinerary.append({
                "day": day + 1,
                "locations": [
                    {
                        "name": loc["name"],
                        "vibe": loc["vibes"],
                        "rating": loc["rating"],
                        "description": loc["description"]
                    } for loc in day_locations
                ]
            })
 
        ai_content = self.llm.generate_itinerary_text(
            itinerary_data=final_itinerary,
            user_vibe=user.vibe,
            weather="Nắng nhẹ, trời trong xanh"
        )

        return {
            "days": final_itinerary,
            "ai_content": ai_content
        }