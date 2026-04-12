import torch

class Neo4jService:

    def __init__(self):
        data = torch.load("graph.pt")
        self.edges = data["edges"]

    def close(self):
        pass

    def get_clusters(self, place_ids):
        visited = set()
        clusters = []

        adjacency = {}
 # fake graph từ cái file pt 
        for edge in self.edges:
            src = edge["src"]
            dst = edge["dst"]

            if src not in adjacency:
                adjacency[src] = []

            adjacency[src].append(dst)

        # BFS 
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

                for neighbor in adjacency.get(cur, []):
                    if neighbor in place_ids:
                        stack.append(neighbor)

            clusters.append(cluster)

        return clusters