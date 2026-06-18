from typing import Any, Tuple, Optional


class PriceNormalizer:
    """
    Normalizes price ranges and categories.
    Matches Task T2.3 requirements.
    """

    @staticmethod
    def normalize_price_range(price_range_str: str) -> Tuple[Optional[float], Optional[float], str]:
        """
        Parses price range strings into min, max, and category.
        Example: "100k - 200k" -> (100000.0, 200000.0, "budget")
        """
        if not price_range_str or not isinstance(price_range_str, str):
            return None, None, "unknown"

        # Basic parsing logic for SoulViet data
        # Data often looks like "10.000 - 50.000" or "Miễn phí"
        clean_str = price_range_str.lower().replace('.', '').replace(',', '').strip()
        
        if "miễn phí" in clean_str or "free" in clean_str:
            return 0.0, 0.0, "free"

        parts = clean_str.split('-')
        try:
            if len(parts) == 2:
                p_min = float(''.join(filter(str.isdigit, parts[0])))
                p_max = float(''.join(filter(str.isdigit, parts[1])))
                category = PriceNormalizer.determine_category(p_max)
                return p_min, p_max, category
            elif len(parts) == 1:
                val = float(''.join(filter(str.isdigit, parts[0])))
                category = PriceNormalizer.determine_category(val)
                return val, val, category
        except (ValueError, StopIteration):
            pass

        return None, None, "unknown"

    @staticmethod
    def determine_category(max_price: float) -> str:
        if max_price == 0:
            return "free"
        if max_price < 100000:
            return "budget"
        if max_price < 500000:
            return "mid_range"
        return "luxury"
