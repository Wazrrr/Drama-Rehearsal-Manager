"""Core feasibility matching logic."""

from __future__ import annotations

from collections.abc import Iterable

from models import FeasibleSlot, Scene
from time_grid import DAYS_PER_WEEK, Matrix, SLOTS_PER_DAY


def intersect_availability(matrices: Iterable[Matrix]) -> Matrix:
    iterator = iter(matrices)
    try:
        common = [row[:] for row in next(iterator)]
    except StopIteration:
        raise ValueError("at least one availability matrix is required")

    for matrix in iterator:
        for day_idx in range(DAYS_PER_WEEK):
            for slot_idx in range(SLOTS_PER_DAY):
                common[day_idx][slot_idx] = common[day_idx][slot_idx] and matrix[day_idx][slot_idx]
    return common


def find_feasible_slots_from_common(common: Matrix, duration_slots: int) -> list[FeasibleSlot]:
    if duration_slots <= 0:
        raise ValueError("duration_slots must be positive")

    feasible: list[FeasibleSlot] = []
    for day_idx in range(DAYS_PER_WEEK):
        for start in range(0, SLOTS_PER_DAY - duration_slots + 1):
            if all(common[day_idx][start + offset] for offset in range(duration_slots)):
                feasible.append(
                    FeasibleSlot(day_index=day_idx, start_slot=start, duration_slots=duration_slots)
                )
    return feasible


def find_feasible_slots_for_scene(
    scene: Scene,
    actor_availability: dict[str, Matrix],
) -> list[FeasibleSlot]:
    matrices = [actor_availability[actor_name] for actor_name in scene.actors]
    common = intersect_availability(matrices)
    return find_feasible_slots_from_common(common, scene.duration_slots)


def compute_all_scene_feasibility(
    scenes: list[Scene], actor_availability: dict[str, Matrix]
) -> dict[str, list[FeasibleSlot]]:
    results: dict[str, list[FeasibleSlot]] = {}
    for scene in scenes:
        results[scene.name] = find_feasible_slots_for_scene(scene, actor_availability)
    return results
