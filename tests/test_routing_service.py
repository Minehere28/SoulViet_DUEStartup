import io
import json
import unittest

from services.routing_service import RoutingService


PLACES = [
    {"id": "a", "lat": 16.0544, "lng": 108.2022},
    {"id": "b", "lat": 16.0678, "lng": 108.2208},
]


class FakeResponse:
    def __init__(self, payload):
        self.body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body.read()


class RoutingServiceTests(unittest.TestCase):
    def test_uses_osrm_distance_and_duration(self):
        payload = {
            "code": "Ok",
            "durations": [[0, 420.2], [390.1, 0]],
            "distances": [[0, 3500.0], [3400.0, 0]],
        }
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return FakeResponse(payload)

        result = RoutingService(timeout=3, opener=opener).build_matrix(PLACES)
        metric = result["metrics"][("a", "b")]

        self.assertEqual(result["source"], "osrm_table")
        self.assertEqual(metric["distance_km"], 3.5)
        self.assertEqual(metric["duration_minutes"], 8)
        self.assertIn("/table/v1/driving/", captured["url"])
        self.assertIn("annotations=duration%2Cdistance", captured["url"])
        self.assertEqual(captured["timeout"], 3)

    def test_falls_back_when_osrm_is_unavailable(self):
        def opener(_request, timeout):
            self.assertGreater(timeout, 0)
            raise TimeoutError("OSRM unavailable")

        result = RoutingService(opener=opener).build_matrix(PLACES)
        metric = result["metrics"][("a", "b")]

        self.assertEqual(result["source"], "haversine_fallback")
        self.assertEqual(result["fallback_reason"], "TimeoutError")
        self.assertEqual(metric["source"], "haversine_fallback")
        self.assertGreater(metric["distance_km"], 0)
        self.assertGreater(metric["duration_minutes"], 0)


if __name__ == "__main__":
    unittest.main()
