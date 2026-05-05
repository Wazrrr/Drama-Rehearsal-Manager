"""Rendering output for CLI."""

from __future__ import annotations

import json

from models import FeasibleSlot
from time_grid import interval_label


def _slot_to_dict(slot: FeasibleSlot) -> dict[str, int | str]:
    return {
        "day_index": slot.day_index,
        "start_slot": slot.start_slot,
        "duration_slots": slot.duration_slots,
        "label": interval_label(slot.day_index, slot.start_slot, slot.duration_slots),
    }


def format_human_readable(results: dict[str, list[FeasibleSlot]]) -> str:
    lines: list[str] = []
    for session_name, slots in results.items():
        lines.append(f"{session_name}:")
        if not slots:
            lines.append("  - No feasible slots")
            continue
        for slot in slots:
            lines.append(f"  - {interval_label(slot.day_index, slot.start_slot, slot.duration_slots)}")
    return "\n".join(lines)


def format_json(results: dict[str, list[FeasibleSlot]]) -> str:
    data = {session_name: [_slot_to_dict(slot) for slot in slots] for session_name, slots in results.items()}
    return json.dumps(data, indent=2)
