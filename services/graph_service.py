import re
import unicodedata

import torch

from services.scoring_service import ScoringService
from utils.place_matching import place_categories, place_types
from services.locality_service import ResolvedLocality


class GraphService:
    """Load graph data and expose one canonical dictionary-based schema."""

    MEAL_TYPES = {
        "bakery", "breakfast_restaurant", "brunch_restaurant", "cafe",
        "coffee_shop", "fast_food_restaurant", "food", "food_court",
        "restaurant", "seafood_restaurant", "tea_house",
        "vietnamese_restaurant", "vegetarian_restaurant",
    }
    SUPPORTING_TYPES = {
        "food_store", "gift_shop", "grocery_or_supermarket", "lodging",
        "manufacturer", "shopping_mall", "store", "souvenir_store",
    }
    EXPERIENCE_TYPES = {
        "art_gallery", "art_studio", "beach", "campground",
        "historical_landmark", "historical_place", "market", "monument",
        "museum", "natural_feature", "park", "place_of_worship",
        "scenic_spot", "tourist_attraction",
    }

    def __init__(self, path="graph.pt"):
        graph = torch.load(path, weights_only=False)
        self.nodes = self._normalize_nodes(graph.get("nodes", {}))
        self.edges = self._normalize_edges(graph.get("edges", {}))
        max_reviews = max(
            (item["review_count"] for item in self.nodes.values()),
            default=0,
        )
        self.scoring = ScoringService(max_reviews)

    @classmethod
    def _place_roles(cls, primary_type, types):
        normalized = {
            str(value).strip().casefold()
            for value in (primary_type, *types)
            if value
        }
        roles = set()
        if normalized & cls.MEAL_TYPES or any(
            "restaurant" in value for value in normalized
        ):
            roles.add("meal")
        if normalized & cls.SUPPORTING_TYPES:
            roles.add("supporting")
        if normalized & cls.EXPERIENCE_TYPES:
            roles.add("attraction")

        primary = str(primary_type or "").strip().casefold()
        if primary in cls.MEAL_TYPES or "restaurant" in primary:
            primary_role = "meal"
        elif primary in cls.SUPPORTING_TYPES:
            primary_role = "supporting"
        elif primary in cls.EXPERIENCE_TYPES:
            primary_role = "attraction"
        elif "attraction" in roles:
            primary_role = "attraction"
        elif "meal" in roles:
            primary_role = "meal"
        elif "supporting" in roles:
            primary_role = "supporting"
        else:
            # The source dataset is a tourism dataset. Unknown legacy types stay
            # eligible until their taxonomy is audited explicitly.
            primary_role = "attraction"
            roles.add("attraction")
        return primary_role, sorted(roles)

    @staticmethod
    def _brand_key(name):
        value = unicodedata.normalize("NFKD", str(name or ""))
        value = "".join(char for char in value if not unicodedata.combining(char))
        value = value.casefold()
        value = re.sub(r"\([^)]*\)", " ", value)
        parts = re.split(r"\s+(?:-|–|—)\s+", value)
        if len(parts) > 1 and len(parts[0].split()) <= 8:
            value = parts[0]
        value = re.sub(r"\b(?:chi nhanh|co so|cs)\s*\d*\b", " ", value)
        value = re.sub(r"[^a-z0-9]+", " ", value)
        return "_".join(value.split())

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

            primary_type = row.get("type", "")
            all_types = list(row.get("all_types", []))
            primary_role, roles = GraphService._place_roles(
                primary_type, all_types or list(types)
            )
            name = row.get("name", row.get("Name", ""))

            nodes[place_id] = {
                "id": place_id,
                "google_place_id": row.get("google_place_id", ""),
                "name": name,
                "type": primary_type,
                "all_types": all_types,
                "primary_role": primary_role,
                "roles": roles,
                "brand_key": row.get("brand_key") or GraphService._brand_key(name),
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
                "opening_hours": dict(row.get("opening_hours", {})),
                "opening_hours_status": row.get(
                    "opening_hours_status", "unknown"
                ),
                "opening_hours_needs_review": bool(
                    row.get("opening_hours_needs_review", False)
                ),
                "opening_hours_verification_status": row.get(
                    "opening_hours_verification_status",
                    "source_unverified",
                ),
                "visit_duration_minutes": int(
                    row.get("visit_duration_minutes", 90) or 90
                ),
                "visit_duration_source": row.get(
                    "visit_duration_source", "default_estimate"
                ),
                "visit_duration_confidence": row.get(
                    "visit_duration_confidence", "low"
                ),
                "activities": list(row.get("activities", [])),
                "activity_categories": list(
                    row.get("activity_categories", [])
                ),
                "reviews": list(row.get("reviews", [])),
                "vibes": list(vibes),
                "types": list(types),
                "main_image": row.get("main_image", ""),
                "images": list(row.get("images", [])),
                "entrance_fee_min": int(row.get("entrance_fee_min", 0) or 0),
                "entrance_fee_max": int(row.get("entrance_fee_max", 0) or 0),
                "typical_spend_min": int(row.get("typical_spend_min", 0) or 0),
                "typical_spend_max": int(row.get("typical_spend_max", 0) or 0),
                "price_unit": row.get("price_unit", "person"),
                "price_source": row.get("price_source", "type_estimate"),
                "price_verified_at": row.get("price_verified_at", ""),
                "price_confidence": row.get("price_confidence", "low"),
                "price_verification_status": row.get(
                    "price_verification_status", "estimated"
                ),
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
        excluded_ids = set(user.excluded_place_ids)
        required_ids = set(getattr(user, "required_place_ids", []))
        exclusion_exceptions = set(
            getattr(user, "exclusion_exception_place_ids", [])
        )
        excluded_types = {
            str(value).strip().casefold()
            for value in getattr(user, "excluded_place_types", [])
            if str(value).strip()
        }
        excluded_categories = {
            str(value).strip().casefold()
            for value in getattr(user, "excluded_activity_categories", [])
            if str(value).strip()
        }
        regional_places = [
            place for place in self.nodes.values()
            if place["region"] == user.region
        ]
        if user.location_focus:
            locality = ResolvedLocality.resolve(
                regional_places,
                user.location_focus,
                user.location_mode,
                user.location_radius_km,
                neighbor_lookup=self.get_neighbors,
            )
            regional_places = locality.filter(regional_places)
        for place in regional_places:
            if place["id"] in excluded_ids:
                continue
            current_types = place_types(place)
            current_categories = place_categories(place)
            if (
                place["id"] not in exclusion_exceptions
                and excluded_types & current_types
            ):
                continue
            if (
                place["id"] not in exclusion_exceptions
                and excluded_categories & current_categories
            ):
                continue
            if place["rating"] < 4 and place["id"] not in required_ids:
                continue
            result.append(place)
        return result

    def score_place(self, place, user):
        return self.scoring.calculate(place, user)

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
