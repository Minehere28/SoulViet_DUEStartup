class FilterService:

    def filter(self, places, user):
        result = []

        for p in places:
            if p.rating < 4:
                continue

            if p.price_max > user.budget:
                continue

            result.append(p)

        return result