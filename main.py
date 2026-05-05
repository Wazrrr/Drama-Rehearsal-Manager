"""CLI for local rehearsal session feasibility matching."""

from __future__ import annotations

import argparse
import sys

from loader import DataValidationError, load_actor_availability, load_sessions
from matcher import compute_all_session_feasibility
from report import format_human_readable, format_json


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find feasible rehearsal slots by intersecting actor availability matrices "
            "(Mon-Sun, 10:00-24:00, 2-hour intervals)."
        )
    )
    parser.add_argument("--actors", required=True, help="Path to actors JSON file")
    parser.add_argument("--sessions", required=True, help="Path to sessions JSON file")
    parser.add_argument(
        "--format",
        default="human",
        choices=("human", "json"),
        help="Output format",
    )
    return parser.parse_args(argv)


def run(argv: list[str]) -> int:
    args = parse_args(argv)

    try:
        actor_availability = load_actor_availability(args.actors)
        sessions = load_sessions(args.sessions, set(actor_availability))
    except DataValidationError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    results = compute_all_session_feasibility(sessions, actor_availability)

    if args.format == "json":
        print(format_json(results))
    else:
        print(format_human_readable(results))

    return 0


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
