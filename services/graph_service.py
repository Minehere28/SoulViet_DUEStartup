import torch

class GraphService:

    def __init__(self, path="graph.pt"):
        self.graph = torch.load(path)
        self.nodes = self.graph["nodes"]
        self.edges = self.graph["edges"]["near"]
 
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

            if p["price_max"] and p["price_max"] > user.budget:
                continue

            result.append(p)

        return result
 
    def score_place(self, place, user):
        import math

        vibe_match = 1 if user.vibe in place["vibes"] else 0
        review_score = math.log((place["review_count"] or 0) + 1)
        price_match = 1 if place["price_max"] <= user.budget else 0.5

        return (
            place["rating"] * 0.25 +
            review_score * 0.15 +
            vibe_match * 0.35 +
            price_match * 0.25
        )
 
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
                key=lambda p: haversine(
                    last["lat"], last["lng"],
                    p["lat"], p["lng"]
                )
            )

            visited.append(next_place)
            unvisited.remove(next_place)

        return visited

    # cluster BFS
    def get_clusters(self, place_ids):
        visited = set()
        clusters = []

        for pid in place_ids:
            if pid in visited:
                continue

            stack = [pid]
            cluster = []

            while stack:
                cur = stack.pop()
                if cur in visited:
                    continue

                visited.add(cur)
                cluster.append(cur)

                neighbors = self.edges.get(cur, [])
                for n in neighbors:
                    if n["to"] in place_ids:
                        stack.append(n["to"])

            clusters.append(cluster)

        return clusters