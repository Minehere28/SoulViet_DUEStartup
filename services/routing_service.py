import json
import math
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from utils.distance import haversine


class RoutingService:
    """Road distance and duration matrix backed by the OSRM Table API."""

    DEFAULT_BASE_URL = "http://router.project-osrm.org"
    FALLBACK_SPEED_KMH = 25.0

    def __init__(self, base_url=None, timeout=None, opener=None):
        self.base_url = (
            base_url
            or os.getenv("OSRM_BASE_URL")
            or self.DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout = float(timeout or os.getenv("OSRM_TIMEOUT_SECONDS", "15"))
        self.opener = opener or urlopen

    @staticmethod
    def _coordinate(place):
        return f"{float(place['lng']):.6f},{float(place['lat']):.6f}"

    @classmethod
    def _fallback_metric(cls, source, destination):
        distance_km = haversine(
            source["lat"], source["lng"], destination["lat"], destination["lng"]
        )
        duration_minutes = (
            0
            if distance_km <= 0
            else max(1, math.ceil(distance_km / cls.FALLBACK_SPEED_KMH * 60))
        )
        return {
            "distance_km": distance_km,
            "duration_minutes": duration_minutes,
            "source": "haversine_fallback",
        }

    @classmethod
    def _fallback_matrix(cls, places, reason):
        metrics = {}
        for source in places:
            for destination in places:
                metrics[(source["id"], destination["id"])] = (
                    cls._fallback_metric(source, destination)
                )
        return {
            "metrics": metrics,
            "source": "haversine_fallback",
            "fallback_reason": reason,
        }

    def build_matrix(self, places):
        if not places:
            return {
                "metrics": {},
                "source": "osrm_table",
                "fallback_reason": None,
            }

        coordinates = ";".join(self._coordinate(place) for place in places)
        query = urlencode(
            {"annotations": "duration,distance", "skip_waypoints": "true"}
        )
        url = f"{self.base_url}/table/v1/driving/{coordinates}?{query}"
        request = Request(
            url,
            headers={"User-Agent": "SoulViet-RAG/1.0"},
            method="GET",
        )

        try:
            with self.opener(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self._validate_payload(payload, len(places))
        except Exception as error:
            return self._fallback_matrix(places, error.__class__.__name__)

        metrics = {}
        used_fallback = False
        for source_index, source in enumerate(places):
            for destination_index, destination in enumerate(places):
                duration_seconds = payload["durations"][source_index][destination_index]
                distance_meters = payload["distances"][source_index][destination_index]
                key = (source["id"], destination["id"])
                if duration_seconds is None or distance_meters is None:
                    metrics[key] = self._fallback_metric(source, destination)
                    used_fallback = True
                    continue
                metrics[key] = {
                    "distance_km": float(distance_meters) / 1000,
                    "duration_minutes": (
                        0
                        if duration_seconds <= 0
                        else max(1, math.ceil(float(duration_seconds) / 60))
                    ),
                    "source": "osrm_table",
                }

        return {
            "metrics": metrics,
            "source": "mixed" if used_fallback else "osrm_table",
            "fallback_reason": "NoRoute" if used_fallback else None,
        }

    @staticmethod
    def _validate_payload(payload, expected_size):
        if payload.get("code") != "Ok":
            raise ValueError(payload.get("message") or payload.get("code"))
        for field in ("durations", "distances"):
            matrix = payload.get(field)
            if not isinstance(matrix, list) or len(matrix) != expected_size:
                raise ValueError(f"OSRM returned an invalid {field} matrix")
            if any(
                not isinstance(row, list) or len(row) != expected_size
                for row in matrix
            ):
                raise ValueError(f"OSRM returned an invalid {field} matrix")
