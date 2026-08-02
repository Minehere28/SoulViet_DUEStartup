import os

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from utils.opening_hours import visit_start_windows


class RouteOptimizer:
    """Minimize one day's travel time under routing constraints."""

    DROP_PENALTY = 10_000_000
    MEAL_DROP_PENALTY = 100_000_000

    def __init__(self, time_limit_milliseconds=None):
        self.time_limit_milliseconds = int(
            time_limit_milliseconds
            or os.getenv("ROUTE_OPTIMIZER_TIME_LIMIT_MS", "500")
        )

    @staticmethod
    def _metric(route_matrix, source, destination):
        if source is None or destination is None:
            return {"distance_km": 0.0, "duration_minutes": 0}
        source_id = source.get("routing_id", source["id"])
        destination_id = destination.get("routing_id", destination["id"])
        return route_matrix["metrics"][(source_id, destination_id)]

    @staticmethod
    def _feasible_windows(
        place,
        day_schedule,
        day_start_minutes,
        day_end_minutes,
    ):
        windows = visit_start_windows(
            day_schedule,
            place.get("visit_duration_minutes", 90),
            day_start_minutes,
            day_end_minutes,
        )
        fixed_start = place.get("fixed_start_minutes")
        if fixed_start is None:
            return windows
        return [
            (fixed_start, fixed_start)
            for start, end in windows
            if start <= fixed_start <= end
        ]

    def optimize(
        self,
        places,
        day_schedules,
        route_matrix,
        max_places,
        max_distance_km,
        day_start_minutes,
        day_end_minutes,
        start_place=None,
    ):
        feasible = [
            place
            for place in places
            if self._feasible_windows(
                place,
                day_schedules[place["id"]],
                day_start_minutes,
                day_end_minutes,
            )
        ]
        if not feasible:
            return []

        # Separate start/end nodes model an open route. When start_place is
        # supplied, its OSRM legs are real; the synthetic end has zero cost.
        nodes = [start_place, None, *feasible]
        first_place_node = 2
        manager = pywrapcp.RoutingIndexManager(
            len(nodes),
            1,
            [0],
            [1],
        )
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            metric = self._metric(
                route_matrix,
                nodes[manager.IndexToNode(from_index)],
                nodes[manager.IndexToNode(to_index)],
            )
            return round(metric["distance_km"] * 1000)

        distance_callback_index = routing.RegisterTransitCallback(
            distance_callback
        )
        routing.AddDimension(
            distance_callback_index,
            0,
            round(max_distance_km * 1000),
            True,
            "Distance",
        )

        def time_callback(from_index, to_index):
            source = nodes[manager.IndexToNode(from_index)]
            metric = self._metric(
                route_matrix,
                source,
                nodes[manager.IndexToNode(to_index)],
            )
            service_minutes = (
                source.get("visit_duration_minutes", 90) if source else 0
            )
            return service_minutes + metric["duration_minutes"]

        time_callback_index = routing.RegisterTransitCallback(time_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(time_callback_index)
        horizon = day_end_minutes - day_start_minutes
        routing.AddDimension(
            time_callback_index,
            horizon,
            horizon,
            True,
            "Time",
        )
        time_dimension = routing.GetDimensionOrDie("Time")

        def count_callback(from_index):
            node = manager.IndexToNode(from_index)
            return int(
                node >= first_place_node
                and nodes[node].get("item_type") != "meal"
            )

        count_callback_index = routing.RegisterUnaryTransitCallback(
            count_callback
        )
        routing.AddDimension(
            count_callback_index,
            0,
            max_places,
            True,
            "PlaceCount",
        )

        meal_indices = {}
        restaurant_indices = {}
        for node, place in enumerate(
            feasible,
            start=first_place_node,
        ):
            index = manager.NodeToIndex(node)
            windows = self._feasible_windows(
                place,
                day_schedules[place["id"]],
                day_start_minutes,
                day_end_minutes,
            )
            relative_windows = [
                (start - day_start_minutes, end - day_start_minutes)
                for start, end in windows
            ]
            cumul = time_dimension.CumulVar(index)
            cumul.SetRange(relative_windows[0][0], relative_windows[-1][1])
            for previous, current in zip(
                relative_windows,
                relative_windows[1:],
            ):
                gap_start = previous[1] + 1
                gap_end = current[0] - 1
                if gap_start <= gap_end:
                    cumul.RemoveInterval(gap_start, gap_end)

            if place.get("item_type") == "meal":
                meal_indices.setdefault(place["meal_slot"], []).append(index)
                restaurant_indices.setdefault(
                    place.get("routing_id", place["id"]), []
                ).append(index)
            else:
                routing.AddDisjunction([index], self.DROP_PENALTY)

        for indices in meal_indices.values():
            routing.AddDisjunction(indices, self.MEAL_DROP_PENALTY, 1)

        solver = routing.solver()
        for indices in restaurant_indices.values():
            if len(indices) > 1:
                solver.Add(sum(routing.ActiveVar(index) for index in indices) <= 1)

        search = pywrapcp.DefaultRoutingSearchParameters()
        search.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
        )
        search.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search.time_limit.FromMilliseconds(
            max(50, self.time_limit_milliseconds)
        )
        solution = routing.SolveWithParameters(search)
        if solution is None:
            return None

        ordered = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node >= first_place_node:
                ordered.append(nodes[node])
            index = solution.Value(routing.NextVar(index))
        return ordered
