import unittest
from unittest.mock import MagicMock
from src.models.user_request import UserRequest, NormalizedConstraints
from src.models.place import CandidatePlace
from src.models.score_breakdown import ScoreBreakdown
from src.validation.request_validator import RequestValidator
from src.graph.graph_retriever import GraphRetriever
from src.retrieval.candidate_generator import CandidateGenerator
from src.retrieval.hard_filter import HardFilter
from src.scoring.place_scorer import PlaceScorer
from src.scoring.reranker import Reranker
from src.scoring.utility_optimizer import UtilityOptimizer
from src.planning.day_planner import DayPlanner
from src.planning.route_optimizer import RouteOptimizer


class TestSoulVietPipeline(unittest.TestCase):

    def setUp(self):
        # Mock GraphStore
        self.mock_store = MagicMock()
        
        # Realistic mock data
        self.places = {
            "P001": {
                "PlaceId": "P001", "Name": "Nhà Thờ Đức Bà", "Type": "Sightseeing",
                "AllTypes": "Sightseeing, Landmark", "VibeTag": "Culture",
                "Lat": 10.7797, "Lng": 106.6990, "RatingScore": 4.5, "ReviewCount": 1200,
                "PriceRange": "30.000 - 50.000"
            },
            "P002": {
                "PlaceId": "P002", "Name": "Bưu Điện Thành Phố", "Type": "Sightseeing",
                "AllTypes": "Sightseeing, Architecture", "VibeTag": "Culture",
                "Lat": 10.7799, "Lng": 106.6999, "RatingScore": 4.6, "ReviewCount": 1500,
                "PriceRange": "20.000 - 40.000"
            },
            "P003": {
                "PlaceId": "P003", "Name": "Cơm Tấm Bụi Sài Gòn", "Type": "Restaurant",
                "AllTypes": "Restaurant, Food", "VibeTag": "Food",
                "Lat": 10.7750, "Lng": 106.6950, "RatingScore": 4.2, "ReviewCount": 800,
                "PriceRange": "80.000 - 120.000"
            },
            "P004": {
                "PlaceId": "P004", "Name": "Phố Đi Bộ Nguyễn Huệ", "Type": "Park",
                "AllTypes": "Park, Entertainment", "VibeTag": "Chill",
                "Lat": 10.7740, "Lng": 106.7030, "RatingScore": 4.7, "ReviewCount": 5000,
                "PriceRange": "10.000 - 20.000"
            },
            "P005": {
                "PlaceId": "P005", "Name": "Dinh Độc Lập", "Type": "Sightseeing",
                "AllTypes": "Sightseeing, History", "VibeTag": "Culture",
                "Lat": 10.7770, "Lng": 106.6955, "RatingScore": 4.4, "ReviewCount": 2000,
                "PriceRange": "40.000 - 60.000"
            }
        }
        
        self.edges = {
            "P001": [
                {"target_id": "P002", "type": "NEAR", "edge_id": "E001"},
                {"target_id": "P003", "type": "NEAR", "edge_id": "E005"},
                {"target_id": "P004", "type": "NEAR", "edge_id": "E006"}
            ],
            "P002": [
                {"target_id": "P001", "type": "NEAR", "edge_id": "E002"},
                {"target_id": "P005", "type": "NEAR", "edge_id": "E003"}
            ],
            "P005": [
                {"target_id": "P003", "type": "NEAR", "edge_id": "E004"}
            ]
        }
        
        self.mock_store.get_place.side_effect = lambda pid: self.places.get(pid)
        self.mock_store.get_edges.side_effect = lambda pid: self.edges.get(pid, [])

    def test_full_pipeline_success(self):
        # 1. User Request
        req = UserRequest(duration=2, budget=500000.0, vibe="culture")
        
        # 2. Validation
        val_res = RequestValidator.validate(req)
        self.assertTrue(val_res.is_valid)
        
        # 3. Normalization (Manual for test)
        constraints = NormalizedConstraints(
            days=req.duration,
            total_budget=req.budget,
            daily_budget=req.budget / req.duration,
            style_tags=["culture"]
        )
        
        # 4. Retrieval (Graph Traversal)
        retriever = GraphRetriever(self.mock_store)
        subgraph = retriever.beam_search(seed_ids=["P001"], constraints=constraints)
        self.assertGreater(len(subgraph.paths), 0)
        
        # 5. Candidate Generation
        gen = CandidateGenerator(self.mock_store)
        candidates = gen.generate_from_subgraph(subgraph)
        self.assertGreater(len(candidates), 0)
        
        # 6. Hard Filtering
        accepted, rejected = HardFilter.apply(candidates, constraints)
        self.assertGreater(len(accepted), 0)
        
        # 7. Scoring
        scorer = PlaceScorer()
        scored = [(c, scorer.score(c, constraints)) for c in accepted]
        
        # 8. Reranking & Utility
        reranked = Reranker.diversify(scored)
        optimized = UtilityOptimizer.optimize(reranked, constraints)
        
        # 9. Planning
        draft = DayPlanner.plan_days(optimized, constraints)
        draft.request = req # Fill mandatory field
        self.assertEqual(len(draft.days), 2)
        
        # 10. Routing & Freezing
        frozen = RouteOptimizer.optimize_and_freeze(draft)
        self.assertTrue(frozen.is_frozen)
        self.assertIsNotNone(frozen.draft_id)
        self.assertEqual(frozen.budget_status, "good_value")
        self.assertGreater(len(frozen.score_breakdowns), 0)

    def test_over_budget_status(self):
        req = UserRequest(duration=1, budget=10000.0, vibe="culture")
        constraints = NormalizedConstraints(days=1, total_budget=10000.0, daily_budget=10000.0)
        
        # Mock an expensive candidate
        expensive_c = CandidatePlace(
            place_id="P_EXP", name="Expensive Place", type="Sightseeing", 
            lat=10.0, lng=106.0, price_max=50000.0
        )
        score = ScoreBreakdown(total_score=0.8, estimated_item_cost=50000.0)
        
        draft = DayPlanner.plan_days([(expensive_c, score)], constraints)
        self.assertEqual(draft.budget_status, "over_budget")

    def test_hard_filter_blacklist(self):
        req = UserRequest(duration=1, budget=100000.0, vibe="culture")
        constraints = NormalizedConstraints(days=1, total_budget=100000.0, daily_budget=100000.0, blacklist_types=["Nightlife"])
        
        candidates = [
            CandidatePlace(place_id="P1", name="Museum", type="Culture", lat=10.0, lng=106.0),
            CandidatePlace(place_id="P2", name="Bar", type="Nightlife", lat=10.1, lng=106.1)
        ]
        
        accepted, rejected = HardFilter.apply(candidates, constraints)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0].place_id, "P1")
        self.assertEqual(rejected[0]["reason"], "blacklisted_type")

    def test_request_validation_errors(self):
        # Invalid duration
        req = UserRequest(duration=10, budget=1000.0, vibe="culture")
        res = RequestValidator.validate(req)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.errors[0]["code"], "out_of_range")
        
        # Invalid budget
        req = UserRequest(duration=1, budget=-100.0, vibe="culture")
        res = RequestValidator.validate(req)
        self.assertFalse(res.is_valid)
        
        # Invalid vibe
        req = UserRequest(duration=1, budget=100.0, vibe="unknown")
        res = RequestValidator.validate(req)
        self.assertFalse(res.is_valid)

if __name__ == "__main__":
    unittest.main()
