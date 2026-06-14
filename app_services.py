"""Reusable project helpers for the local web app."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from loader import load_actor_availability, load_scenes, parse_actor_availability, parse_scenes
from matcher import compute_all_scene_feasibility
from models import FeasibleSlot, Scene
from report import format_human_readable, format_json
from time_grid import Matrix, interval_label

SAMPLE_ACTORS_PATH = Path("data/actors.sample.json")
SAMPLE_SCENES_PATH = Path("data/scenes.sample.json")
DEFAULT_ACTORS_PATH = SAMPLE_ACTORS_PATH
DEFAULT_SCENES_PATH = SAMPLE_SCENES_PATH


@dataclass
class ProjectData:
    actors: dict[str, Matrix]
    scenes: list[Scene]


@dataclass(frozen=True)
class LoadedProject:
    data: ProjectData
    actors_path: Path
    scenes_path: Path


def choose_default_project_paths() -> tuple[Path, Path]:
    return DEFAULT_ACTORS_PATH, DEFAULT_SCENES_PATH


def load_project(actors_path: str | Path, scenes_path: str | Path) -> ProjectData:
    actors = load_actor_availability(actors_path)
    scenes = load_scenes(scenes_path, set(actors))
    return ProjectData(actors=actors, scenes=scenes)


def load_default_project() -> LoadedProject:
    actors_path, scenes_path = choose_default_project_paths()
    return LoadedProject(
        data=load_project(actors_path, scenes_path),
        actors_path=actors_path,
        scenes_path=scenes_path,
    )


def empty_project() -> ProjectData:
    return ProjectData(actors={}, scenes=[])


def parse_project_payloads(
    actor_payload: object,
    scene_payload: object,
    *,
    allow_empty: bool = False,
) -> ProjectData:
    actors = parse_actor_availability(actor_payload, allow_empty=allow_empty)
    scenes = parse_scenes(scene_payload, set(actors), allow_empty=allow_empty)
    return ProjectData(actors=actors, scenes=scenes)


def matrix_to_ints(matrix: Matrix) -> list[list[int]]:
    return [[1 if cell else 0 for cell in row] for row in matrix]


def actors_to_jsonable(actors: dict[str, Matrix]) -> dict[str, list[list[int]]]:
    return {actor_name: matrix_to_ints(matrix) for actor_name, matrix in actors.items()}


def scenes_to_jsonable(scenes: list[Scene]) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for scene in scenes:
        item: dict[str, object] = {
            "name": scene.name,
            "actors": list(scene.actors),
            "duration_slots": scene.duration_slots,
        }
        if scene.description:
            item["description"] = scene.description
        payload.append(item)
    return payload


def dump_actors_json(actors: dict[str, Matrix]) -> str:
    return json.dumps(actors_to_jsonable(actors), ensure_ascii=False, indent=2) + "\n"


def dump_scenes_json(scenes: list[Scene]) -> str:
    return json.dumps(scenes_to_jsonable(scenes), ensure_ascii=False, indent=2) + "\n"


def save_project(
    project: ProjectData,
    actors_path: str | Path = DEFAULT_ACTORS_PATH,
    scenes_path: str | Path = DEFAULT_SCENES_PATH,
) -> None:
    actors_dst = Path(actors_path)
    scenes_dst = Path(scenes_path)
    actors_dst.parent.mkdir(parents=True, exist_ok=True)
    scenes_dst.parent.mkdir(parents=True, exist_ok=True)
    actors_dst.write_text(dump_actors_json(project.actors), encoding="utf-8")
    scenes_dst.write_text(dump_scenes_json(project.scenes), encoding="utf-8")


def validate_project(project: ProjectData, *, allow_empty: bool = False) -> ProjectData:
    return parse_project_payloads(
        actors_to_jsonable(project.actors),
        scenes_to_jsonable(project.scenes),
        allow_empty=allow_empty,
    )


def compute_project_results(project: ProjectData) -> dict[str, list[FeasibleSlot]]:
    validated = validate_project(project, allow_empty=True)
    return compute_all_scene_feasibility(validated.scenes, validated.actors)


def merged_slot_labels(slots: list[FeasibleSlot]) -> list[str]:
    merged: list[tuple[int, int, int]] = []
    for slot in sorted(slots, key=lambda item: (item.day_index, item.start_slot)):
        start = slot.start_slot
        end = slot.start_slot + slot.duration_slots
        if merged:
            last_day, last_start, last_end = merged[-1]
            if last_day == slot.day_index and start <= last_end:
                merged[-1] = (last_day, last_start, max(last_end, end))
                continue
        merged.append((slot.day_index, start, end))

    return [
        interval_label(day_index, start_slot, end_slot - start_slot)
        for day_index, start_slot, end_slot in merged
    ]


def result_rows(
    results: dict[str, list[FeasibleSlot]],
    scenes: list[Scene],
) -> list[dict[str, object]]:
    descriptions = {scene.name: scene.description for scene in scenes}
    rows: list[dict[str, object]] = []
    for scene_name, slots in results.items():
        if not slots:
            rows.append(
                {
                    "Scene": scene_name,
                    "Description": descriptions.get(scene_name, ""),
                    "Slots": "No feasible slots",
                }
            )
            continue
        for slot_label in merged_slot_labels(slots):
            rows.append(
                {
                    "Scene": scene_name,
                    "Description": descriptions.get(scene_name, ""),
                    "Slots": slot_label,
                }
            )
    return rows


def export_results_json(results: dict[str, list[FeasibleSlot]]) -> str:
    return format_json(results) + "\n"


def export_results_text(results: dict[str, list[FeasibleSlot]]) -> str:
    return format_human_readable(results) + "\n"
