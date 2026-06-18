from typing import List, Dict, Set, Optional
from src.graph.graph_store import GraphStore
from src.models.graph_path import RankedGraphPath, RankedSubgraph
from src.models.user_request import NormalizedConstraints


class GraphRetriever:
    """
    Implements Bounded Beam Search Graph Traversal.
    Matches Task T3.1 and Section 7 of Design Doc.
    """

    def __init__(self, graph_store: GraphStore):
        self.graph_store = graph_store

    def beam_search(
        self, 
        seed_ids: List[str], 
        constraints: NormalizedConstraints,
        depth_limit: int = 2,
        beam_width: int = 50
    ) -> RankedSubgraph:
        """
        Performs bounded beam search over the graph.
        """
        frontier: List[RankedGraphPath] = []
        
        # Initialize frontier with seeds
        for seed_id in seed_ids:
            place = self.graph_store.get_place(seed_id)
            if not place:
                continue
                
            frontier.append(RankedGraphPath(
                seed_id=seed_id,
                terminal_place_id=seed_id,
                node_ids=[seed_id],
                edge_ids=[],
                depth=0,
                graph_score=1.0, # Initial score
                expansion_scores=[1.0],
                edge_reasons=["seed"],
                rank=0
            ))

        all_paths: List[RankedGraphPath] = list(frontier)
        discarded: List[Dict[str, str]] = []

        for depth in range(1, depth_limit + 1):
            new_candidates: List[RankedGraphPath] = []
            
            for path in frontier:
                edges = self.graph_store.get_edges(path.terminal_place_id)
                
                for edge in edges:
                    target_id = edge.get('target_id')
                    if not target_id or target_id in path.node_ids:
                        continue
                    
                    # Compute expansion score (simplified for now, to be enriched)
                    expansion_score = self._compute_expansion_score(edge, path, constraints)
                    
                    new_path = RankedGraphPath(
                        seed_id=path.seed_id,
                        terminal_place_id=target_id,
                        node_ids=path.node_ids + [target_id],
                        edge_ids=path.edge_ids + [edge.get('edge_id', 'unknown')],
                        depth=depth,
                        graph_score=path.graph_score * expansion_score,
                        expansion_scores=path.expansion_scores + [expansion_score],
                        edge_reasons=path.edge_reasons + [edge.get('type', 'related')],
                        rank=0
                    )
                    new_candidates.append(new_path)
            
            # Sort and prune frontier to beam_width
            new_candidates.sort(key=lambda x: x.graph_score, reverse=True)
            frontier = new_candidates[:beam_width]
            
            # Record discarded
            for p in new_candidates[beam_width:]:
                discarded.append({"id": p.terminal_place_id, "reason": "beam_pruning"})
                
            all_paths.extend(frontier)

        # Final ranking
        all_paths.sort(key=lambda x: x.graph_score, reverse=True)
        for i, path in enumerate(all_paths):
            path.rank = i + 1

        return RankedSubgraph(
            paths=all_paths,
            frontier_snapshot=[p.terminal_place_id for p in frontier],
            retained_candidate_ids=list(set(p.terminal_place_id for p in all_paths)),
            discarded_candidate_ids=discarded,
            traversal_configuration={
                "depth_limit": depth_limit,
                "beam_width": beam_width
            }
        )

    def _compute_expansion_score(
        self, 
        edge: Dict, 
        path: RankedGraphPath, 
        constraints: NormalizedConstraints
    ) -> float:
        """
        Expansion score based on edge type and request style.
        """
        base_score = 0.8 # Default decay
        
        edge_type = edge.get('type', '').upper()
        if edge_type == 'NEAR':
            base_score = 0.9
        elif edge_type == 'CATEGORY' or edge_type == 'TYPE':
            base_score = 0.85
            
        # Style match (if edge reason matches style tags)
        # This is a placeholder for richer logic
        return base_score
