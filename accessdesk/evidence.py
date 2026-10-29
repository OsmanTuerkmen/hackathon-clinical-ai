"""Evidence phrase selection shared by applicant prechecks and decision letters."""


def drop_contained_evidence(items):
    indexed = list(enumerate(items))
    field_order = {}
    for index, item in indexed:
        field_order.setdefault(item.get("field", ""), index)
    ordered = sorted(
        indexed,
        key=lambda pair: (
            field_order[pair[1].get("field", "")],
            -(pair[1]["end"] - pair[1]["start"]),
            pair[1]["start"],
            pair[0],
        ),
    )
    kept = []
    for _, candidate in ordered:
        field = candidate.get("field", "")
        if any(
            existing.get("field", "") == field
            and existing["start"] <= candidate["start"]
            and existing["end"] >= candidate["end"]
            for existing in kept
        ):
            continue
        kept.append(candidate)
    return sorted(
        kept,
        key=lambda item: (field_order[item.get("field", "")], item["start"]),
    )
