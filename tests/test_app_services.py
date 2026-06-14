from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app_services import (
    ProjectData,
    compute_project_results,
    dump_actors_json,
    dump_scenes_json,
    load_project,
    parse_project_payloads,
    save_project,
)
from day_filters import filter_results_by_day_indexes, resolve_allowed_day_indexes
from loader import DataValidationError
from models import Scene
from storage_backends import (
    ACTOR_NAME_HEADER,
    SCENE_HEADERS,
    availability_headers,
    project_from_sheet_values,
    project_to_sheet_values,
)
from time_grid import DAYS_PER_WEEK, SLOTS_PER_DAY


def blank_matrix(value: int = 0) -> list[list[int]]:
    return [[value for _ in range(SLOTS_PER_DAY)] for _ in range(DAYS_PER_WEEK)]


class AppServicesTests(unittest.TestCase):
    def test_parse_project_payloads_accepts_unicode_names(self) -> None:
        actors = {"Actor A": blank_matrix(1)}
        scenes = [{"name": "Scene One", "actors": ["Actor A"], "duration_slots": 1}]

        project = parse_project_payloads(actors, scenes)

        self.assertIn("Actor A", project.actors)
        self.assertEqual(project.scenes[0].name, "Scene One")

    def test_parse_project_payloads_rejects_unknown_scene_actor(self) -> None:
        actors = {"Alice": blank_matrix(1)}
        scenes = [{"name": "Scene", "actors": ["Bob"], "duration_slots": 1}]

        with self.assertRaises(DataValidationError):
            parse_project_payloads(actors, scenes)

    def test_dump_json_preserves_schema_and_unicode(self) -> None:
        project = ProjectData(
            actors={"Actor A": [[True for _ in range(SLOTS_PER_DAY)] for _ in range(DAYS_PER_WEEK)]},
            scenes=[Scene(name="Scene One", actors=("Actor A",), duration_slots=2)],
        )

        actors_payload = json.loads(dump_actors_json(project.actors))
        scenes_payload = json.loads(dump_scenes_json(project.scenes))

        self.assertEqual(actors_payload["Actor A"][0][0], 1)
        self.assertEqual(scenes_payload[0]["actors"], ["Actor A"])
        self.assertEqual(scenes_payload[0]["duration_slots"], 2)

    def test_save_and_load_project_round_trips(self) -> None:
        project = ProjectData(
            actors={"Alice": blank_matrix(1)},
            scenes=[Scene(name="Scene", actors=("Alice",), duration_slots=1)],
        )

        with tempfile.TemporaryDirectory() as tmp:
            actors_path = Path(tmp) / "actors.json"
            scenes_path = Path(tmp) / "scenes.json"
            save_project(project, actors_path, scenes_path)

            loaded = load_project(actors_path, scenes_path)

        self.assertEqual(loaded.scenes, project.scenes)
        self.assertEqual(loaded.actors["Alice"][0][0], True)

    def test_compute_and_filter_results_match_cli_day_filter(self) -> None:
        matrix = blank_matrix(0)
        matrix[0][0] = 1
        matrix[5][0] = 1
        project = ProjectData(
            actors={"Alice": matrix},
            scenes=[Scene(name="Scene", actors=("Alice",), duration_slots=1)],
        )

        results = compute_project_results(project)
        allowed = resolve_allowed_day_indexes(no_weekend=True, chosen_days=["Mon,Sat"])
        filtered = filter_results_by_day_indexes(results, allowed)

        self.assertEqual(len(filtered["Scene"]), 1)
        self.assertEqual(filtered["Scene"][0].day_index, 0)

    def test_project_to_sheet_values_uses_editable_headers(self) -> None:
        project = ProjectData(
            actors={"Alice": blank_matrix(1)},
            scenes=[Scene(name="Scene", actors=("Alice",), duration_slots=1)],
        )

        actor_rows, scene_rows = project_to_sheet_values(project)

        self.assertEqual(actor_rows[0], [ACTOR_NAME_HEADER, *availability_headers()])
        self.assertEqual(actor_rows[1][0], "Alice")
        self.assertEqual(scene_rows[0], list(SCENE_HEADERS))
        self.assertEqual(scene_rows[1], ["Scene", "Alice", "1"])

    def test_project_from_sheet_values_accepts_blank_availability_as_false(self) -> None:
        actor_rows = [[ACTOR_NAME_HEADER, *availability_headers()]]
        actor_rows.append(["Alice", *["" for _ in availability_headers()]])
        scene_rows = [list(SCENE_HEADERS), ["Scene", "Alice", "1"]]

        project = project_from_sheet_values(actor_rows, scene_rows)

        self.assertEqual(list(project.actors), ["Alice"])
        self.assertFalse(project.actors["Alice"][0][0])
        self.assertEqual(project.scenes, [Scene(name="Scene", actors=("Alice",), duration_slots=1)])

    def test_project_from_sheet_values_accepts_json_actor_list(self) -> None:
        actor_rows = [
            [ACTOR_NAME_HEADER, *availability_headers()],
            ["Alice", *["TRUE" for _ in availability_headers()]],
            ["Bob", *["TRUE" for _ in availability_headers()]],
        ]
        scene_rows = [list(SCENE_HEADERS), ["Scene", '["Alice", "Bob"]', "2"]]

        project = project_from_sheet_values(actor_rows, scene_rows)

        self.assertEqual(project.scenes, [Scene(name="Scene", actors=("Alice", "Bob"), duration_slots=2)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
