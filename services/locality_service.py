from dataclasses import dataclass
from statistics import median

from utils.distance import haversine
from utils.place_matching import normalize_text


def _administrative_match(place, focus):
    needle = normalize_text(focus)
    if not needle:
        return False
    strong_fields = (
        place.get("locality"),
        place.get("district"),
        place.get("address"),
    )
    return any(
        needle in normalize_text(value or "")
        for value in strong_fields
    )


def _name_match(place, focus):
    needle = normalize_text(focus)
    return bool(
        needle
        and needle in normalize_text(place.get("name") or "")
    )


def _name_anchor_matches(places, focus):
    matches = [place for place in places if _name_match(place, focus)]
    if len(matches) != 1:
        return matches
    place = matches[0]
    exact = normalize_text(place.get("name") or "") == normalize_text(focus)
    has_administrative_data = any(
        normalize_text(place.get(field) or "")
        for field in ("locality", "district", "address")
    )
    # One partial name hit with a conflicting address is too weak to define a
    # locality. An exact-name anchor or multiple corroborating anchors is safe.
    return matches if exact or not has_administrative_data else []


def _field_match(place, focus):
    """Prefer administrative evidence and reject POI-name false positives."""
    if _administrative_match(place, focus):
        return True
    has_administrative_data = any(
        normalize_text(place.get(field) or "")
        for field in ("locality", "district", "address")
    )
    if has_administrative_data:
        return False
    return _name_match(place, focus)


@dataclass(frozen=True)
class ResolvedLocality:
    focus: str
    mode: str
    radius_km: float
    direct_ids: frozenset
    nearby_ids: frozenset
    center: tuple[float, float] | None

    @classmethod
    def resolve_scope(cls, places, focus):
        """Resolve a locality against the whole graph, independent of stale region."""
        all_places = list(places)
        matches = [
            place for place in all_places
            if _administrative_match(place, focus)
        ]
        match_source = "administrative"
        if not matches:
            matches = _name_anchor_matches(all_places, focus)
            match_source = "name_fallback"

        counts = {}
        for place in matches:
            region = str(place.get("region") or "").strip()
            if region:
                counts[region] = counts.get(region, 0) + 1
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        resolved_region = None
        ambiguous_regions = []
        if ranked:
            highest = ranked[0][1]
            leaders = [region for region, count in ranked if count == highest]
            if len(leaders) == 1:
                resolved_region = leaders[0]
            else:
                ambiguous_regions = leaders
        return {
            "focus": str(focus or ""),
            "region": resolved_region,
            "candidate_count": (
                counts.get(resolved_region, 0) if resolved_region else 0
            ),
            "region_counts": counts,
            "ambiguous_regions": ambiguous_regions,
            "match_source": match_source,
        }

    @classmethod
    def resolve(
        cls, places, focus, mode="strict", radius_km=8.0,
        neighbor_lookup=None,
    ):
        regional = list(places)
        direct = [
            place for place in regional
            if _administrative_match(place, focus)
        ]
        if not direct:
            direct = _name_anchor_matches(regional, focus)
        regional_ids = {place["id"] for place in regional}
        nearby_ids = set()
        if mode == "nearby" and neighbor_lookup is not None:
            for place in direct:
                for edge in neighbor_lookup(place["id"]):
                    neighbor_id = edge.get("to")
                    try:
                        within_radius = float(edge.get("distance", 0)) <= float(
                            radius_km
                        )
                    except (TypeError, ValueError):
                        within_radius = False
                    if neighbor_id in regional_ids and within_radius:
                        nearby_ids.add(neighbor_id)
        center = None
        coordinates = [
            (float(place["lat"]), float(place["lng"]))
            for place in direct
            if place.get("lat") is not None and place.get("lng") is not None
        ]
        if coordinates:
            center = (
                median(point[0] for point in coordinates),
                median(point[1] for point in coordinates),
            )
        return cls(
            focus=str(focus or ""),
            mode=mode,
            radius_km=float(radius_km),
            direct_ids=frozenset(place["id"] for place in direct),
            nearby_ids=frozenset(nearby_ids),
            center=center,
        )

    @property
    def found(self):
        return bool(self.direct_ids)

    def is_direct(self, place):
        return place.get("id") in self.direct_ids or _field_match(place, self.focus)

    def contains(self, place):
        if self.is_direct(place):
            return True
        if self.mode != "nearby":
            return False
        if place.get("id") in self.nearby_ids:
            return True
        if self.center is None:
            return False
        try:
            return haversine(
                self.center[0], self.center[1],
                float(place["lat"]), float(place["lng"]),
            ) <= self.radius_km
        except (KeyError, TypeError, ValueError):
            return False

    def filter(self, places):
        return [place for place in places if self.contains(place)]
