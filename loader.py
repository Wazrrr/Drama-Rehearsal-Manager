"""Load and validate local JSON input data."""

from __future__ import annotations

import json
from pathlib import Path

from models import Scene
from time_grid import Matrix, SLOTS_PER_DAY, validate_and_normalize_matrix


class DataValidationError(ValueError):
    """Raised for invalid input files or schemas."""


def _read_json(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise DataValidationError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataValidationError(f"invalid JSON in {path}: {exc}") from exc


def load_actor_availability(path: str | Path) -> dict[str, Matrix]:
    src = Path(path)
    raw = _read_json(src)

    if not isinstance(raw, dict):
        raise DataValidationError("actors file must be an object: {actor_name: matrix}")

    actors: dict[str, Matrix] = {}
    for actor_name, matrix in raw.items():
        if not isinstance(actor_name, str) or not actor_name.strip():
            raise DataValidationError(f"invalid actor name: {actor_name!r}")
        try:
            normalized = validate_and_normalize_matrix(matrix, actor_name=actor_name)
        except ValueError as exc:
            raise DataValidationError(str(exc)) from exc
        actors[actor_name] = normalized

    if not actors:
        raise DataValidationError("actors file is empty")

    return actors


def _validate_scene_item(item: object, known_actors: set[str], index: int) -> Scene:
    if not isinstance(item, dict):
        raise DataValidationError(f"scene at index {index} must be an object")

    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise DataValidationError(f"scene at index {index} has invalid 'name'")

    actors = item.get("actors")
    if not isinstance(actors, list) or not actors:
        raise DataValidationError(f"scene '{name}' must contain a non-empty 'actors' list")
    normalized_actor_names: list[str] = []
    for actor in actors:
        if not isinstance(actor, str) or not actor.strip():
            raise DataValidationError(f"scene '{name}' has invalid actor name: {actor!r}")
        if actor not in known_actors:
            raise DataValidationError(f"scene '{name}' references unknown actor '{actor}'")
        normalized_actor_names.append(actor)

    duration_slots = item.get("duration_slots", 1)
    if not isinstance(duration_slots, int) or duration_slots <= 0:
        raise DataValidationError(f"scene '{name}' has invalid duration_slots '{duration_slots}'")
    if duration_slots > SLOTS_PER_DAY:
        raise DataValidationError(
            f"scene '{name}' duration_slots exceeds slots per day ({SLOTS_PER_DAY})"
        )

    return Scene(name=name, actors=tuple(normalized_actor_names), duration_slots=duration_slots)


def load_scenes(path: str | Path, known_actors: set[str]) -> list[Scene]:
    src = Path(path)
    raw = _read_json(src)

    if not isinstance(raw, list):
        raise DataValidationError("scenes file must be an array")

    scenes = [_validate_scene_item(item, known_actors, idx) for idx, item in enumerate(raw)]

    if not scenes:
        raise DataValidationError("scenes file is empty")

    names = [scene.name for scene in scenes]
    if len(names) != len(set(names)):
        raise DataValidationError("scene names must be unique")

    return scenes
