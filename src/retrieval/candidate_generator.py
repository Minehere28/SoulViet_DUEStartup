from typing import List, Dict, Optional
from src.graph.graph_store import GraphStore
from src.models.place import CandidatePlace
from src.models.graph_path import RankedSubgraph
from src.normalization.place_normalizer import PlaceNormalizer
from src.normalization.price_normalizer import PriceNormalizer


class CandidateGenerator:
    """
    Maps graph nodes to CandidatePlace records.
    Matches Task T3.2 and Section 7 of Design Doc.
    """

    def __init__(self, graph_store: GraphStore):
        self.graph_store = graph_store

    def generate_from_subgraph(self, subgraph: RankedSubgraph) -> List[CandidatePlace]:
        """
        Converts subgraph nodes to CandidatePlace objects.
        """
        candidates = []
        seen_ids = set()

        for path in subgraph.paths:
            place_id = path.terminal_place_id
            if place_id in seen_ids:
                continue
                
            node = self.graph_store.get_place(place_id)
            if not node:
                continue
                
            candidate = self._map_node_to_candidate(node)
            # Attach graph context
            candidate.graph_edges = [
                {"id": path.edge_ids[i], "reason": path.edge_reasons[i+1]} 
                for i in range(len(path.edge_ids))
            ]
            
            candidates.append(candidate)
            seen_ids.add(place_id)
            
        return candidates

    def _map_node_to_candidate(self, node: Dict) -> CandidatePlace:
        """
        Helper to map raw node dictionary to CandidatePlace.
        """
        # Price normalization
        p_min, p_max, p_cat = PriceNormalizer.normalize_price_range(node.get('PriceRange', ''))
        
        return CandidatePlace(
            place_id=str(node.get('PlaceId', '')),
            name=node.get('Name', 'Unknown'),
            type=node.get('Type', 'Other'),
            types=PlaceNormalizer.normalize_list(node.get('AllTypes', [])),
            vibes=PlaceNormalizer.normalize_list(node.get('VibeTag', [])),
            address=node.get('Address', ''),
            lat=PlaceNormalizer.normalize_coordinate(node.get('Lat', 0)),
            lng=PlaceNormalizer.normalize_coordinate(node.get('Lng', 0)),
            rating=PlaceNormalizer.normalize_rating(node.get('RatingScore')),
            review_count=PlaceNormalizer.normalize_review_count(node.get('ReviewCount')),
            price_min=p_min,
            price_max=p_max,
            price_category=p_cat,
            operation_hours=node.get('OperationHours'),
            description=node.get('Description'),
            activities=PlaceNormalizer.normalize_list(node.get('Activities_JSON', [])),
            reviews=PlaceNormalizer.normalize_list(node.get('TopReviews_JSON', [])),
            image=node.get('MainImage'),
            graph_edges=[],
            evidence_refs=[]
        )
