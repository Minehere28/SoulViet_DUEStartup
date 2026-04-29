from utils.type_duration import TYPE_DURATION_MAP


def estimate_time(place):

    main_type = place.get("type")

    if main_type in TYPE_DURATION_MAP:
        return TYPE_DURATION_MAP[main_type]

    types = place.get("types", [])

    durations = []

    for t in types:

        if t not in TYPE_DURATION_MAP:
            continue

        durations.append(
            TYPE_DURATION_MAP[t]
        )

    if not durations:
        return 60

    return int(
        sum(durations) / len(durations)
    )