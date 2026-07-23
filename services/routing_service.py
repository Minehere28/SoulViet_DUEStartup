from utils.distance import haversine

class RoutingService:

    def optimize(self, places):
        if not places:
            return []

        visited = [places[0]]
        unvisited = places[1:]

        while unvisited:
            last = visited[-1]

            next_place = min(
                unvisited,
                key=lambda p: haversine(last.lat, last.lng, p.lat, p.lng)
            )

            visited.append(next_place)
            unvisited.remove(next_place)

        return visited