import os

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from utils.opening_hours import visit_start_windows


class RouteOptimizer:
    """Minimize one day's travel time under routing constraints."""

    DROP_PENALTY = 10_000_000

    def __init__(self, time_limit_milliseconds=None):
        self.time_limit_milliseconds = int(
            time_limit_milliseconds
            or os.getenv("ROUTE_OPTIMIZER_TIME_LIMIT_MS", "500")
        )

    @staticmethod
    def _metric(route_matrix, source, destination):
        if source is None or destination is None:
            return {"distance_km": 0.0, "duration_minutes": 0}
        return route_matrix["metrics"][(source["id"], destination["id"])]

    @staticmethod
    def _feasible_windows(
        place,
        day_schedule,
        day_start_minutes,
        day_end_minutes,
    ):
        return visit_start_windows(
            day_schedule,
            place.get("visit_duration_minutes", 90),
            day_start_minutes,
            day_end_minutes,
        )

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
            return int(
                manager.IndexToNode(from_index) >= first_place_node
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

            routing.AddDisjunction(
                [index],
                self.DROP_PENALTY,
            )

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
