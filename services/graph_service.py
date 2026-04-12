import torch
from services.scoring_service import ScoringService

class GraphService:

    def __init__(self, path="graph.pt"):
        self.graph = torch.load(path)
        self.scoring_service = ScoringService() 

        raw_nodes = self.graph["nodes"]
        raw_edges = self.graph["edges"]
 
        self.nodes = {}
        for p in raw_nodes:
            normalized = self.normalize_place(p)
            self.nodes[normalized["id"]] = normalized
 
        self.edges = {}
        for e in raw_edges:
            src = e["src"]
            if src not in self.edges:
                self.edges[src] = []

            self.edges[src].append({
                "to": e["dst"],
                "distance": e.get("distance", 0)
            })
 
    def get_all_places(self):
        return list(self.nodes.values())

    def get_place(self, place_id):
        return self.nodes.get(place_id)

    def get_neighbors(self, place_id):
        return self.edges.get(place_id, []) 


    def filter_places(self, user):
        result = []
        for p in self.nodes.values():
            if p["rating"] < 4:
                continue
            if p.get("price_max") and p["price_max"] > user.budget:
                continue
            result.append(p)
        return result 

    def score_place(self, place, user): 
        return self.scoring_service.calculate(place, user)
 

    def optimize_route(self, place_list):
        from utils.distance import haversine
        if not place_list:
            return []
        visited = [place_list[0]]
        unvisited = place_list[1:]
        while unvisited:
            last = visited[-1]
            next_place = min(
                unvisited,
                key=lambda p: haversine(last["lat"], last["lng"], p["lat"], p["lng"])
            )
            visited.append(next_place)
            unvisited.remove(next_place)
        return visited
 
    def normalize_place(self, p):
        return {
            "id": p.get("PlaceId"),
            "name": p.get("Name"),
            "lat": p.get("Lat"),
            "lng": p.get("Lng"),
            "rating": p.get("RatingScore", 0),
            "review_count": p.get("ReviewCount", 0),
            "price_min": p.get("PriceMin", 0),
            "price_max": p.get("PriceMax", 0),
            "vibes": p.get("VibeTag", []),
            "types": p.get("Type", []),
            "description": p.get("Generated_Description", "")
        }
 
# bfs để clusters
    def get_clusters(self, place_ids):
        visited = set()
        clusters = []
        for pid in place_ids:
            if pid in visited: continue
            stack = [pid]
            cluster = []
            while stack:
                cur = stack.pop()
                if cur in visited: continue
                visited.add(cur)
                cluster.append(cur)
                for n in self.edges.get(cur, []):
                    if n["to"] in place_ids:
                        stack.append(n["to"])
            clusters.append(cluster)
        return clusters