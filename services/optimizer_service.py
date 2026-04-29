from utils.distance import haversine

class OptimizerService:

    def optimize(
        self,
        candidates,
        edges,
        max_budget,
        max_time
    ):

        dp = {}

        trace = {}

        dp[(0, 0)] = 0

        trace[(0, 0)] = []

        for item in candidates:

            cost = item.get("cost", 0)

            time = item.get(
                "estimated_time",
                60
            )

            value = item.get("value", 0)

            current_states = list(dp.keys())

            for budget_used, time_used in current_states:

                new_budget = (
                    budget_used + cost
                )

                new_time = (
                    time_used + time
                )

                if new_budget > max_budget:
                    continue

                if new_time > max_time:
                    continue

                new_value = (
                    dp[(budget_used, time_used)]
                    + value
                )

                state = (
                    new_budget,
                    new_time
                )

                old_value = dp.get(
                    state,
                    -1
                )

                if new_value <= old_value:
                    continue

                dp[state] = new_value

                trace[state] = (
                    trace[
                        (
                            budget_used,
                            time_used
                        )
                    ] + [item]
                )

        best_state = max(
            dp,
            key=lambda s: dp[s]
        )

        ordered_places = self.order_route(
            trace[best_state],
            edges
        )

        return {
            "places": ordered_places,
            "score": dp[best_state],
            "total_cost": best_state[0],
            "total_time": best_state[1]
        }
    

    def order_route(self, places, edges):

        if not places:
            return []

        ordered = []

        remaining = places[:]

        current = remaining.pop(0)

        ordered.append(current)

        while remaining:

            nearest = min(

                remaining,

                key=lambda p: self.edge_distance(
                    current["id"],
                    p["id"],
                    edges
                )
            )

            ordered.append(nearest)

            remaining.remove(nearest)

            current = nearest

        return ordered
    
    def edge_distance(
        self,
        from_id,
        to_id,
        edges
    ):

        for edge in edges:

            if (
                edge["from"] == from_id
                and edge["to"] == to_id
            ):

                return edge.get(
                    "distance",
                    999
                )

            if (
                edge["from"] == to_id
                and edge["to"] == from_id
            ):

                return edge.get(
                    "distance",
                    999
                )

        return 999