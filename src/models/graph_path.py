from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class RankedGraphPath:
    """
    Represents a ranked path in the graph.
    Matches Section 7 of the Design Doc.
    """
    seed_id: str
    terminal_place_id: str
    node_ids: List[str]
    edge_ids: List[str]
    depth: int
    graph_score: float
    expansion_scores: List[float]
    edge_reasons: List[str]
    rank: int


@dataclass
class RankedSubgraph:
    """
    Represents a set of ranked paths forming a subgraph.
    Matches Section 7 of the Design Doc.
    """
    paths: List[RankedGraphPath]
    frontier_snapshot: List[str]
    retained_candidate_ids: List[str]
    discarded_candidate_ids: List[Dict[str, str]]  # ID and reason
    traversal_configuration: Dict
