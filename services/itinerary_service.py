from services.graph_service import GraphService

class ItineraryService:

    def __init__(self):
        self.graph = GraphService()

    def build(self, user):
 
        filtered = self.graph.filter_places(user)
 
        scored = [(p, self.graph.score_place(p, user)) for p in filtered]
        scored.sort(key=lambda x: x[1], reverse=True)

        top_places = [p for p, _ in scored[:30]]
        top_ids = [p["id"] for p in top_places]
 
        cluster_ids = self.graph.get_clusters(top_ids)

        clusters = []
        for cluster in cluster_ids:
            group = [self.graph.get_place(pid) for pid in cluster]
            if group:
                clusters.append(group)
 
        clusters = [self.graph.optimize_route(c) for c in clusters]

        return clusters[:user.duration]