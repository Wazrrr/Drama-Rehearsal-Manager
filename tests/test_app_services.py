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
    empty_project,
    load_project,
    parse_project_payloads,
    save_project,
)
from day_filters import filter_results_by_day_indexes, resolve_allowed_day_indexes
from drama_storage import (
    Drama,
    choose_initial_drama,
    create_drama,
    delete_drama,
    dump_drama_json,
    list_dramas,
    load_drama,
    load_drama_file,
    parse_drama_payload,
    read_last_drama_id,
    remember_last_drama_id,
    rename_drama,
    save_drama,
)
from loader import DataValidationError
from models import Scene
from time_grid import DAYS_PER_WEEK, SLOTS_PER_DAY


def blank_matrix(value: int = 0) -> list[list[int]]:
    return [[value for _ in range(SLOTS_PER_DAY)] for _ in range(DAYS_PER_WEEK)]


def project_fixture() -> ProjectData:
    return ProjectData(
        actors={"Alice": blank_matrix(1)},
        scenes=[Scene(name="Scene", actors=("Alice",), duration_slots=1)],
    )


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

    def test_parse_project_payloads_allows_empty_when_requested(self) -> None:
        project = parse_project_payloads({}, [], allow_empty=True)

        self.assertEqual(project, empty_project())

    def test_drama_json_preserves_project_data(self) -> None:
        drama = Drama(
            id="my-drama",
            name="My Drama",
            created_at="2026-06-14T00:00:00Z",
            updated_at="2026-06-14T00:00:00Z",
            project=project_fixture(),
        )

        parsed = parse_drama_payload(json.loads(dump_drama_json(drama)))

        self.assertEqual(parsed.id, "my-drama")
        self.assertEqual(parsed.name, "My Drama")
        self.assertEqual(parsed.project.scenes, drama.project.scenes)
        self.assertEqual(parsed.project.actors["Alice"][0][0], True)

    def test_create_list_load_and_save_drama_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            drama = create_drama("My Drama", data_dir, project=project_fixture())
            summaries = list_dramas(data_dir)

            self.assertEqual([summary.name for summary in summaries], ["My Drama"])

            loaded = load_drama(drama.id, data_dir)
            loaded.project.scenes.append(
                Scene(name="Second", actors=("Alice",), duration_slots=2)
            )
            saved = save_drama(loaded, data_dir)
            reloaded = load_drama(saved.id, data_dir)

        self.assertEqual(reloaded.project.scenes[-1].name, "Second")

    def test_rename_drama_preserves_id_and_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            drama = create_drama("Old Name", data_dir, project=project_fixture())

            renamed = rename_drama(drama.id, "New Name", data_dir)

        self.assertEqual(renamed.id, drama.id)
        self.assertEqual(renamed.name, "New Name")
        self.assertEqual(renamed.project.scenes, drama.project.scenes)

    def test_delete_drama_clears_last_selected_drama(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            drama = create_drama("Delete Me", data_dir)
            remember_last_drama_id(drama.id, data_dir)

            delete_drama(drama.id, data_dir)

            self.assertEqual(list_dramas(data_dir), [])
            self.assertIsNone(read_last_drama_id(data_dir))

    def test_choose_initial_drama_falls_back_from_invalid_last_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            drama = create_drama("Fallback", data_dir)
            remember_last_drama_id("missing-drama", data_dir)

            chosen = choose_initial_drama(data_dir)

        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.id, drama.id)

    def test_broken_drama_json_raises_validation_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text("{broken", encoding="utf-8")

            with self.assertRaises(DataValidationError):
                load_drama_file(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
