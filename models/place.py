class Place:
    def __init__(self, row):
        self.id = row.get("PlaceId")
        self.name = row.get("Name")

        self.lat = float(row.get("Lat", 0))
        self.lng = float(row.get("Lng", 0))

        self.rating = float(row.get("RatingScore", 0))
        self.review_count = int(row.get("ReviewCount", 0))

        self.vibe = row.get("VibeTag", "")

        self.price_min = float(row.get("PriceMin", 0))
        self.price_max = float(row.get("PriceMax", 0))

        self.description = row.get("Generated_Description", "") 