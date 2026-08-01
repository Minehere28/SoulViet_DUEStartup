import unittest
from datetime import date
from typing import get_args

from pydantic import ValidationError

from models.user_request import RegionName, UserRequest, VibeName


class UserRequestTests(unittest.TestCase):
    def values(self, **overrides):
        values = {
            "duration": 1,
            "vibe": get_args(VibeName)[0],
            "region": get_args(RegionName)[0],
            "start_date": date(2026, 8, 2),
        }
        values.update(overrides)
        return values

    def test_accepts_up_to_eight_places(self):
        request = UserRequest(**self.values(max_places_per_day=8))
        self.assertEqual(request.max_places_per_day, 8)

    def test_requires_both_start_coordinates(self):
        with self.assertRaises(ValidationError):
            UserRequest(**self.values(start_lat=16.0544))

    def test_accepts_complete_start_location(self):
        request = UserRequest(
            **self.values(start_lat=16.0544, start_lng=108.2022)
        )
        self.assertEqual(request.start_lng, 108.2022)


if __name__ == "__main__":
    unittest.main()
