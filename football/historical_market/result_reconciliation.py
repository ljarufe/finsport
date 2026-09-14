FINAL_STATUSES = {"FT", "AET", "PEN"}
RECOVERABLE_STATUSES = {"", "NS", "TBD"}
RECOVERABLE_STATUS_LONG = {"", "Not Started", "Time to be defined"}
RESULT_FIELDS = (
    "home_score",
    "away_score",
    "fulltime_home_score",
    "fulltime_away_score",
    "outcome",
)


def final_result_conflicts(match, values):
    if any(
        getattr(match, field) not in (None, "", values[field])
        for field in RESULT_FIELDS
    ):
        return True
    if match.status_short in FINAL_STATUSES:
        return False
    if match.status_short not in RECOVERABLE_STATUSES:
        return True
    return match.status_long not in RECOVERABLE_STATUS_LONG


def fill_compatible_final_result(match, values):
    """Fill result gaps and perform only the approved pre-match-to-final transition."""
    if final_result_conflicts(match, values):
        return "CONFLICT"
    changed = []
    for field in RESULT_FIELDS:
        if getattr(match, field) in (None, ""):
            setattr(match, field, values[field])
            changed.append(field)
    if match.status_short in RECOVERABLE_STATUSES:
        if match.status_short != values["status_short"]:
            match.status_short = values["status_short"]
            changed.append("status_short")
        if match.status_long != values["status_long"]:
            match.status_long = values["status_long"]
            changed.append("status_long")
    elif not match.status_long and values["status_long"]:
        match.status_long = values["status_long"]
        changed.append("status_long")
    if not changed:
        return "PRESERVED"
    match.full_clean()
    match.save(update_fields=[*changed, "modified"])
    return "FILLED"
