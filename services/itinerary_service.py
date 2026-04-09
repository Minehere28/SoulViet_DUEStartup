from services.filter_service import FilterService
from services.scoring_service import ScoringService
from services.routing_service import RoutingService
from services.neo4j_service import Neo4jService

class ItineraryService:

    def __init__(self, places):
        self.places = places
        self.filter = FilterService()
        self.scoring = ScoringService()
        self.routing = RoutingService()

        self.neo4j = Neo4jService()

    def build(self, user): 
        filtered = self.filter.filter(self.places, user)
 
        scored = [(p, self.scoring.calculate(p, user)) for p in filtered]
        scored.sort(key=lambda x: x[1], reverse=True)

        top_places = [p for p, _ in scored[:30]]
        top_ids = [p.id for p in top_places]
 
        cluster_ids = self.neo4j.get_clusters(top_ids)
 
        clusters = []
        for cluster in cluster_ids:
            group = [p for p in top_places if p.id in cluster]
            if group:
                clusters.append(group)
 # routing
        clusters = [self.routing.optimize(c) for c in clusters]

        return clusters[:user.duration]