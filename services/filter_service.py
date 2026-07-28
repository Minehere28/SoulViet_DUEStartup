class FilterService:

    def filter(self, places, user):
        result = []

        for p in places:
            if p.rating < 4:
                continue

            result.append(p)

        return result
