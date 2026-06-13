"""Day selection helpers shared by CLI and web UI."""

from __future__ import annotations

from models import FeasibleSlot
from time_grid import DAYS

DAY_NAME_TO_INDEX = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}


def parse_chosen_day_indexes(raw_values: list[str]) -> set[int]:
    chosen: set[int] = set()
    for token in raw_values:
        for part in token.split(","):
            cleaned = part.strip().strip(".").lower()
            if not cleaned:
                continue
            day_index = DAY_NAME_TO_INDEX.get(cleaned)
            if day_index is None:
                valid_days = ", ".join(DAYS)
                raise ValueError(f"invalid day '{part}'. Use day names like: {valid_days}")
            chosen.add(day_index)

    if not chosen:
        raise ValueError("no valid days were provided to --choose")

    return chosen


def resolve_allowed_day_indexes(
    *,
    no_weekend: bool = False,
    chosen_days: list[str] | None = None,
) -> set[int]:
    allowed = set(range(len(DAYS)))

    if no_weekend:
        allowed -= {5, 6}
    if chosen_days:
        allowed &= parse_chosen_day_indexes(chosen_days)

    return allowed


def filter_results_by_day_indexes(
    results: dict[str, list[FeasibleSlot]],
    allowed_day_indexes: set[int],
) -> dict[str, list[FeasibleSlot]]:
    return {
        scene_name: [slot for slot in slots if slot.day_index in allowed_day_indexes]
        for scene_name, slots in results.items()
    }
