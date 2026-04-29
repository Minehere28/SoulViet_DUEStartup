import random
# con vợ này để tạo ra danh sách candidates 
# nó sẽ lấy một tập điểm ra sau đó lấy một cái tâm, từ tâm đó lan ra 2 tầng là thành tập candidates
# (điểm trung tâm random phù hợp) - [relation ship near] - (điểm kề) - [near] - (điểm kề tiếp theo)
class ClusterService:

    def __init__(self, graph_service, filter_service):
        self.graph = graph_service
        self.filter = filter_service

    def generate_candidates(self, user, limit=10):

        all_places = self.graph.get_all_places()
 
        valid_places = []
#đoạn này lấy danh sách điểm(điểm trung tâm như mô tả ở trên sẽ được lấy từ 1 trong số điểm ở đây), 
# t bỏ đi mấy thằng có rating thấp và chọn mấy cái phù hợp với budget + vibe type,... 
        for p in all_places:

            if p["rating"] < 4:
                continue

            if p.get("price_max", 0) > user.budget:
                continue

            if not self.filter.match(
                user.vibe,
                p.get("vibes", []),
                p.get("types", [])
            ):
                continue

            valid_places.append(p)

        if not valid_places:
            return []
#  random trong tập mẫu 
        random.shuffle(valid_places) 
        used_cluster_signatures = set()
        clusters = []
#  lưu candidate clusters + chọn seed + call hàm expand cluster bên dưới 
        for seed in valid_places[:limit]:

            cluster = self.expand_cluster(
                seed,
                user,
                valid_places
            )

            signature = tuple(sorted(
                p["id"]
                for p in cluster["places"]
            ))

            if signature in used_cluster_signatures:
                continue

            used_cluster_signatures.add(signature)

            if len(cluster["places"]) >= 3:
                clusters.append(cluster)

        return clusters
# hàm lan truyền 
    def expand_cluster(
        self,
        seed,
        user,
        valid_places,
        max_depth=2
    ):

        valid_ids = set(p["id"] for p in valid_places)

        visited = set()

        queued = set()

        queue = [(seed["id"], 0)]

        queued.add(seed["id"])

        cluster_ids = []

        cluster_edges = []

        while queue:

            current_id, depth = queue.pop(0)

            if current_id in visited:
                continue

            visited.add(current_id)

            current_place = self.graph.get_place(current_id)

            if not current_place:
                continue
 
            if not self.is_valid_place(current_place, user):
                continue

            cluster_ids.append(current_id)

            if depth >= max_depth:
                continue

            neighbors = self.graph.get_neighbors(current_id)

            for neighbor in neighbors:

                next_id = neighbor["to"]

                if next_id in visited:
                    continue

                if next_id in queued:
                    continue

                if next_id not in valid_ids:
                    continue

                next_place = self.graph.get_place(next_id)

                if not next_place:
                    continue
 
                if not self.is_valid_place(next_place, user):
                    continue

                cluster_edges.append({
                    "from": current_id,
                    "to": next_id,
                    "distance": neighbor.get("distance", 0)
                })

                queue.append((next_id, depth + 1))

                queued.add(next_id)

        return {

            "places": [
                self.graph.get_place(pid)
                for pid in cluster_ids
            ],

            "edges": cluster_edges
        }

    def is_valid_place(self, place, user):

        if place["rating"] < 4:
            return False

        if place.get("price_max", 0) > user.budget:
            return False

        return self.filter.match(
            user.vibe,
            place.get("vibes", []),
            place.get("types", [])
        )