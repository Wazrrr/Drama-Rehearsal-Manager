"""Time grid utilities for weekly 2-hour rehearsal slots."""

from __future__ import annotations

from typing import Sequence

DAYS: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
SLOT_START_HOURS: tuple[int, ...] = (10, 12, 14, 16, 18, 20, 22)
SLOTS_PER_DAY = len(SLOT_START_HOURS)
DAYS_PER_WEEK = len(DAYS)

Matrix = list[list[bool]]


def hour_to_label(hour: int) -> str:
    return f"{hour:02d}:00"


def slot_label(slot_index: int) -> str:
    start = SLOT_START_HOURS[slot_index]
    end = start + 2
    return f"{hour_to_label(start)}-{hour_to_label(end)}"


def interval_label(day_index: int, start_slot: int, duration_slots: int) -> str:
    start_hour = SLOT_START_HOURS[start_slot]
    end_hour = start_hour + (2 * duration_slots)
    return f"{DAYS[day_index]} {hour_to_label(start_hour)}-{hour_to_label(end_hour)}"


def normalize_cell(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in {"1", "true", "yes", "y"}:
            return True
        if cleaned in {"0", "false", "no", "n"}:
            return False
    raise ValueError(f"invalid availability cell value: {value!r}")


def validate_and_normalize_matrix(raw_matrix: Sequence[Sequence[object]], *, actor_name: str) -> Matrix:
    if len(raw_matrix) != DAYS_PER_WEEK:
        raise ValueError(
            f"actor '{actor_name}' matrix must have {DAYS_PER_WEEK} rows (got {len(raw_matrix)})"
        )

    matrix: Matrix = []
    for day_idx, row in enumerate(raw_matrix):
        if len(row) != SLOTS_PER_DAY:
            raise ValueError(
                f"actor '{actor_name}' row {day_idx} must have {SLOTS_PER_DAY} slots (got {len(row)})"
            )
        matrix.append([normalize_cell(cell) for cell in row])

    return matrix
