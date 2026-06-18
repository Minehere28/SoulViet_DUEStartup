import torch
import os
import threading
from typing import List, Dict, Optional


class GraphStore:
    """
    Thread-safe store for graph artifacts (graph.pt).
    Matches Task T2.2 requirements.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(GraphStore, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, graph_path: str = "graph.pt"):
        if self._initialized:
            return
        
        self.graph_path = graph_path
        self.graph_data = None
        self._load_lock = threading.Lock()
        self.load_graph()
        self._initialized = True

    def load_graph(self):
        """Loads the graph.pt artifact."""
        if not os.path.exists(self.graph_path):
            # Fallback to check in data/artifacts if not at root
            alt_path = os.path.join("data", "artifacts", "graph.pt")
            if os.path.exists(alt_path):
                self.graph_path = alt_path
            else:
                raise FileNotFoundError(f"Graph artifact not found at {self.graph_path} or {alt_path}")
        
        with self._load_lock:
            # Using weights_only=False as graph.pt likely contains custom objects/tensors
            # and it's a trusted local file in this context.
            self.graph_data = torch.load(self.graph_path, map_location=torch.device('cpu'), weights_only=False)

    def get_place(self, place_id: str) -> Optional[Dict]:
        """Retrieves a single place node by ID."""
        # This assumes graph_data is a dictionary-like structure or has nodes attribute
        # Based on current MVP service, we'll adapt to the expected structure.
        if isinstance(self.graph_data, dict) and 'nodes' in self.graph_data:
            return self.graph_data['nodes'].get(place_id)
        return None

    def get_all_places(self) -> List[Dict]:
        """Returns all place nodes."""
        if isinstance(self.graph_data, dict) and 'nodes' in self.graph_data:
            return list(self.graph_data['nodes'].values())
        return []

    def get_edges(self, place_id: str) -> List[Dict]:
        """Returns edges connected to a place."""
        if isinstance(self.graph_data, dict) and 'edges' in self.graph_data:
            return self.graph_data['edges'].get(place_id, [])
        return []
