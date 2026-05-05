"""CLI for local rehearsal scene feasibility matching."""

from __future__ import annotations

import argparse
import sys

from loader import DataValidationError, load_actor_availability, load_scenes
from matcher import compute_all_scene_feasibility
from models import FeasibleSlot
from report import format_human_readable, format_json
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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find feasible rehearsal slots by intersecting actor availability matrices "
            "(Mon-Sun, 10:00-24:00, 2-hour intervals)."
        )
    )
    parser.add_argument("--actors", required=True, help="Path to actors JSON file")
    parser.add_argument("--scenes", required=True, help="Path to scenes JSON file")
    parser.add_argument(
        "--format",
        default="human",
        choices=("human", "json"),
        help="Output format",
    )

    parser.add_argument(
        "--no-weekend",
        action="store_true",
        help="Exclude Saturday and Sunday from output",
    )
    parser.add_argument(
        "--choose",
        nargs="+",
        metavar="DAY",
        help=(
            "Only include selected days in output. Accepts comma-separated and/or spaced "
            "day names, e.g. --choose Mon,Fri or --choose Mon Fri."
        ),
    )
    return parser.parse_args(argv)


def _parse_chosen_day_indexes(raw_values: list[str]) -> set[int]:
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


def resolve_day_filter(args: argparse.Namespace) -> set[int]:
    all_days = set(range(len(DAYS)))
    allowed = set(all_days)

    if args.no_weekend:
        allowed -= {5, 6}
    if args.choose:
        allowed &= _parse_chosen_day_indexes(args.choose)

    return allowed


def filter_results_by_day_indexes(
    results: dict[str, list[FeasibleSlot]],
    allowed_day_indexes: set[int],
) -> dict[str, list[FeasibleSlot]]:
    return {
        scene_name: [slot for slot in slots if slot.day_index in allowed_day_indexes]
        for scene_name, slots in results.items()
    }


def run(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        allowed_day_indexes = resolve_day_filter(args)
        actor_availability = load_actor_availability(args.actors)
        scenes = load_scenes(args.scenes, set(actor_availability))
    except (DataValidationError, ValueError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    results = compute_all_scene_feasibility(scenes, actor_availability)
    results = filter_results_by_day_indexes(results, allowed_day_indexes)

    if args.format == "json":
        print(format_json(results))
    else:
        print(format_human_readable(results))

    return 0


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
