import math

import torch

from utils.distance import haversine


class GraphService:
    """Load graph data and expose one canonical dictionary-based schema."""

    def __init__(self, path="graph.pt"):
        graph = torch.load(path, weights_only=False)
        self.nodes = self._normalize_nodes(graph.get("nodes", {}))
        self.edges = self._normalize_edges(graph.get("edges", {}))
        max_reviews = max(
            (item["review_count"] for item in self.nodes.values()),
            default=0,
        )
        self.max_log_reviews = math.log1p(max_reviews)

    @staticmethod
    def _normalize_nodes(raw_nodes):
        if isinstance(raw_nodes, dict):
            records = raw_nodes.values()
        elif isinstance(raw_nodes, list):
            records = raw_nodes
        else:
            raise ValueError("graph.pt: 'nodes' must be a list or dictionary")

        nodes = {}
        for row in records:
            place_id = row.get("id") or row.get("PlaceId")
            if not place_id:
                continue

            vibes = row.get("vibes", row.get("VibeTag", []))
            types = (
                row.get("types")
                or row.get("all_types")
                or row.get("Type", [])
            )
            if isinstance(vibes, str):
                vibes = [vibes] if vibes else []
            if isinstance(types, str):
                types = [types] if types else []

            nodes[place_id] = {
                "id": place_id,
                "google_place_id": row.get("google_place_id", ""),
                "name": row.get("name", row.get("Name", "")),
                "type": row.get("type", ""),
                "all_types": list(row.get("all_types", [])),
                "address": row.get("address", ""),
                "region": row.get("region", ""),
                "lat": float(row.get("lat", row.get("Lat", 0)) or 0),
                "lng": float(row.get("lng", row.get("Lng", 0)) or 0),
                "rating": float(
                    row.get("rating", row.get("RatingScore", 0)) or 0
                ),
                "review_count": int(
                    row.get("review_count", row.get("ReviewCount", 0)) or 0
                ),
                "description": row.get(
                    "description", row.get("Generated_Description", "")
                )
                or "",
                "operation_hours": row.get("operation_hours", ""),
                "activities": list(row.get("activities", [])),
                "reviews": list(row.get("reviews", [])),
                "vibes": list(vibes),
                "types": list(types),
                "main_image": row.get("main_image", ""),
                "images": list(row.get("images", [])),
            }

        return nodes

    @staticmethod
    def _normalize_edges(raw_edges):
        if isinstance(raw_edges, dict) and "near" in raw_edges:
            raw_edges = raw_edges["near"]

        if isinstance(raw_edges, dict):
            return {
                source: list(neighbors)
                for source, neighbors in raw_edges.items()
            }

        if not isinstance(raw_edges, list):
            raise ValueError("graph.pt: 'edges' must be a list or dictionary")

        adjacency = {}
        for edge in raw_edges:
            source = edge.get("src")
            target = edge.get("dst")
            if not source or not target:
                continue
            adjacency.setdefault(source, []).append(
                {
                    "to": target,
                    "distance": float(edge.get("distance", 0) or 0),
                }
            )
        return adjacency

    def get_all_places(self):
        return list(self.nodes.values())

    def get_place(self, place_id):
        return self.nodes.get(place_id)

    def get_neighbors(self, place_id):
        return self.edges.get(place_id, [])

    def filter_places(self, user):
        result = []
        for place in self.nodes.values():
            if place["rating"] < 4:
                continue
            result.append(place)
        return result

    def score_place(self, place, user):
        vibe_match = 1 if user.vibe in place["vibes"] else 0
        rating_score = min(max(place["rating"] / 5, 0), 1)
        popularity_score = (
            math.log1p(place["review_count"]) / self.max_log_reviews
            if self.max_log_reviews
            else 0
        )

        return (
            rating_score * 0.45
            + popularity_score * 0.20
            + vibe_match * 0.35
        )

    def optimize_route(self, place_list):
        if not place_list:
            return []

        visited = [place_list[0]]
        unvisited = place_list[1:]
        while unvisited:
            last = visited[-1]
            next_place = min(
                unvisited,
                key=lambda place: haversine(
                    last["lat"],
                    last["lng"],
                    place["lat"],
                    place["lng"],
                ),
            )
            visited.append(next_place)
            unvisited.remove(next_place)

        return visited

    def get_clusters(self, place_ids):
        allowed_ids = set(place_ids)
        visited = set()
        clusters = []

        for place_id in place_ids:
            if place_id in visited:
                continue

            stack = [place_id]
            cluster = []
            while stack:
                current = stack.pop()
                if current in visited:
                    continue

                visited.add(current)
                cluster.append(current)
                for neighbor in self.get_neighbors(current):
                    neighbor_id = neighbor["to"]
                    if neighbor_id in allowed_ids and neighbor_id not in visited:
                        stack.append(neighbor_id)

            clusters.append(cluster)

        return clusters
