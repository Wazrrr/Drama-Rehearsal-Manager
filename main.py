"""CLI for local rehearsal scene feasibility matching."""

from __future__ import annotations

import argparse
import sys

from day_filters import filter_results_by_day_indexes, resolve_allowed_day_indexes
from loader import DataValidationError, load_actor_availability, load_scenes
from matcher import compute_all_scene_feasibility
from report import format_human_readable, format_json


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


def resolve_day_filter(args: argparse.Namespace) -> set[int]:
    return resolve_allowed_day_indexes(no_weekend=args.no_weekend, chosen_days=args.choose)


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
