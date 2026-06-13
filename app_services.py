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

DEFAULT_ACTORS_PATH = Path("data/actors.json")
DEFAULT_SCENES_PATH = Path("data/scenes.json")
SAMPLE_ACTORS_PATH = Path("data/actors.sample.json")
SAMPLE_SCENES_PATH = Path("data/scenes.sample.json")


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
    if DEFAULT_ACTORS_PATH.exists() and DEFAULT_SCENES_PATH.exists():
        return DEFAULT_ACTORS_PATH, DEFAULT_SCENES_PATH
    return SAMPLE_ACTORS_PATH, SAMPLE_SCENES_PATH


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


def parse_project_payloads(actor_payload: object, scene_payload: object) -> ProjectData:
    actors = parse_actor_availability(actor_payload)
    scenes = parse_scenes(scene_payload, set(actors))
    return ProjectData(actors=actors, scenes=scenes)


def matrix_to_ints(matrix: Matrix) -> list[list[int]]:
    return [[1 if cell else 0 for cell in row] for row in matrix]


def actors_to_jsonable(actors: dict[str, Matrix]) -> dict[str, list[list[int]]]:
    return {actor_name: matrix_to_ints(matrix) for actor_name, matrix in actors.items()}


def scenes_to_jsonable(scenes: list[Scene]) -> list[dict[str, object]]:
    return [
        {
            "name": scene.name,
            "actors": list(scene.actors),
            "duration_slots": scene.duration_slots,
        }
        for scene in scenes
    ]


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


def validate_project(project: ProjectData) -> ProjectData:
    return parse_project_payloads(
        actors_to_jsonable(project.actors),
        scenes_to_jsonable(project.scenes),
    )


def compute_project_results(project: ProjectData) -> dict[str, list[FeasibleSlot]]:
    validated = validate_project(project)
    return compute_all_scene_feasibility(validated.scenes, validated.actors)


def result_rows(results: dict[str, list[FeasibleSlot]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for scene_name, slots in results.items():
        if not slots:
            rows.append(
                {
                    "Scene": scene_name,
                    "Slot": "No feasible slots",
                    "Day index": None,
                    "Start slot": None,
                    "Duration slots": None,
                }
            )
            continue
        for slot in slots:
            rows.append(
                {
                    "Scene": scene_name,
                    "Slot": interval_label(slot.day_index, slot.start_slot, slot.duration_slots),
                    "Day index": slot.day_index,
                    "Start slot": slot.start_slot,
                    "Duration slots": slot.duration_slots,
                }
            )
    return rows


def export_results_json(results: dict[str, list[FeasibleSlot]]) -> str:
    return format_json(results) + "\n"


def export_results_text(results: dict[str, list[FeasibleSlot]]) -> str:
    return format_human_readable(results) + "\n"
