import re

from utils.place_matching import normalize_command_text, normalize_text


class PlaceRequirementService:
    """Resolve explicit must-visit place mentions without guessing a POI."""

    REQUIREMENT_PATTERNS = (
        r"\bthem\b",
        r"\bcho\b.+\bvao\b",
        r"\bcan\s+co\b",
        r"\bmuon\s+co\b",
        r"\bphai\s+co\b",
        r"\bbat\s+buoc\b",
        r"\bnhat\s+dinh\b",
        r"\bphai\s+(?:di|ghe)\b",
        r"\bmuon\s+(?:di|ghe)\b",
        r"\bghe\b",
    )
    NEGATION_PATTERN = re.compile(
        r"\b(?:khong(?:\s+muon)?\s+(?:di|ghe|co)|dung\s+them|"
        r"bo|xoa|loai)\b"
    )

    def __init__(self, graph):
        self.graph = graph

    @classmethod
    def has_requirement_intent(cls, message):
        normalized = normalize_command_text(message)
        if cls.NEGATION_PATTERN.search(normalized):
            return False
        return any(
            re.search(pattern, normalized)
            for pattern in cls.REQUIREMENT_PATTERNS
        )

    @staticmethod
    def _is_exact_mention(message, place_name):
        return bool(place_name and re.search(
            rf"(?:^|\s){re.escape(place_name)}(?:$|\s)", message
        ))

    @staticmethod
    def _fuzzy_score(message_tokens, place_name):
        name_tokens = set(place_name.split())
        if len(name_tokens) < 2:
            return 0
        overlap = len(message_tokens & name_tokens)
        coverage = overlap / len(name_tokens)
        # Requiring two tokens prevents a generic request such as "đi biển"
        # from being converted into an arbitrary named beach.
        return coverage if overlap >= 2 and coverage >= 0.75 else 0

    def resolve(self, message, region):
        if not self.has_requirement_intent(message):
            return []

        normalized = normalize_command_text(message)
        message_tokens = set(normalized.split())
        ranked = []
        for place in self.graph.get_all_places():
            if place.get("region") != region:
                continue
            name = normalize_text(place.get("name"))
            exact = self._is_exact_mention(normalized, name)
            fuzzy_score = self._fuzzy_score(message_tokens, name)
            if not exact and not fuzzy_score:
                continue
            ranked.append((
                int(exact),
                fuzzy_score,
                len(name),
                float(place.get("rating", 0)),
                place,
            ))

        ranked.sort(key=lambda item: item[:4], reverse=True)
        if not ranked:
            return []
        if ranked[0][0]:
            longest_exact = ranked[0][2]
            return [
                item[4] for item in ranked
                if item[0] and item[2] == longest_exact
            ][:3]
        best_score = ranked[0][1]
        return [
            item[4] for item in ranked if item[1] == best_score
        ][:1]
