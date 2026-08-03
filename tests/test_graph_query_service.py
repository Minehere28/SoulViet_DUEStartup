import unittest

from models.assistant_intent import GraphQueryPlan
from services.graph_query_service import GraphQueryService
from services.graph_service import GraphService


def place(place_id, rating=4.5, name=None):
    return {
        "id": place_id,
        "name": name or place_id,
        "description": "",
        "type": "tourist_attraction",
        "types": ["tourist_attraction"],
        "all_types": ["tourist_attraction"],
        "activities": [],
        "activity_categories": [],
        "vibes": [],
        "rating": rating,
        "review_count": 10,
    }


class FakeGraph:
    def __init__(self):
        self.places = {
            item["id"]: item
            for item in [
                place("a", 4.1),
                place("b", 4.0),
                place("c", 4.2),
                place("d", 5.0),
                place("e", 4.9),
                place("f", 4.8),
                place("g", 4.7),
            ]
        }
        self.edges = {
            "a": [{"to": "b", "distance": 0.5}],
            "b": [{"to": "c", "distance": 0.5}],
        }

    def filter_places(self, _user):
        return list(self.places.values())

    def score_place(self, item, _user):
        return {"total": item["rating"] / 5}

    def get_neighbors(self, place_id):
        return self.edges.get(place_id, [])


class FakeSimilarity:
    def find_similar(self, *_args, **_kwargs):
        return []


class GraphQueryServiceTests(unittest.TestCase):
    def test_runtime_taxonomy_separates_meals_and_supporting_places(self):
        primary, roles = GraphService._place_roles(
            "tea_house", ["tea_house"]
        )
        self.assertEqual(primary, "meal")
        self.assertIn("meal", roles)

        primary, roles = GraphService._place_roles(
            "gift_shop", ["gift_shop", "store", "food"]
        )
        self.assertEqual(primary, "supporting")
        self.assertNotIn("attraction", roles)

    def test_brand_key_groups_ezi_branches(self):
        first = GraphService._brand_key(
            "EZI - Đậm Đà Nẵng - 74 Phan Đăng Lưu"
        )
        second = GraphService._brand_key(
            "EZI - Đậm Đà Nẵng - 388 Đống Đa"
        )
        self.assertEqual(first, second)

    def test_expands_near_exactly_one_hop_and_records_provenance(self):
        service = GraphQueryService(FakeGraph(), FakeSimilarity())
        query = GraphQueryPlan(
            seed_place_ids=["a"],
            expand_near=True,
            near_hops=1,
            candidate_limit=7,
        )

        result = service.search(object(), query)

        self.assertEqual(result["provenance"]["a"], "explicit_seed")
        self.assertEqual(result["provenance"]["b"], "near:a")
        self.assertNotEqual(result["provenance"]["c"], "near:b")
        self.assertEqual(result["candidate_count"], 7)
        self.assertEqual(result["near_hops"], 1)


if __name__ == "__main__":
    unittest.main()
