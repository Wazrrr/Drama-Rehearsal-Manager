from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from loader import DataValidationError, load_actor_availability, load_scenes
from matcher import compute_all_scene_feasibility
from models import Scene
from time_grid import DAYS_PER_WEEK, SLOTS_PER_DAY, interval_label


def blank_matrix() -> list[list[int]]:
    return [[0 for _ in range(SLOTS_PER_DAY)] for _ in range(DAYS_PER_WEEK)]


def write_drama_file(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "cli-drama",
                "name": "CLI Drama",
                "created_at": "2026-06-14T00:00:00Z",
                "updated_at": "2026-06-14T00:00:00Z",
                "actors": {"Alice": blank_matrix()},
                "scenes": [{"name": "Scene", "actors": ["Alice"], "duration_slots": 1}],
            }
        ),
        encoding="utf-8",
    )


class RehearsalManagementTests(unittest.TestCase):
    def test_single_slot_intersection(self) -> None:
        alice = blank_matrix()
        bob = blank_matrix()

        alice[0] = [1, 1, 0, 1, 0, 0, 0]
        bob[0] = [1, 0, 0, 1, 1, 0, 0]

        scenes = [Scene(name="Scene_1", actors=("Alice", "Bob"), duration_slots=1)]
        result = compute_all_scene_feasibility(scenes, {"Alice": alice, "Bob": bob})

        labels = [interval_label(s.day_index, s.start_slot, s.duration_slots) for s in result["Scene_1"]]
        self.assertEqual(labels, ["Mon 10:00-12:00", "Mon 16:00-18:00"])

    def test_multi_slot_contiguous_window(self) -> None:
        matrix = blank_matrix()
        matrix[0] = [0, 0, 0, 0, 0, 1, 1]
        matrix[1] = [1, 1, 0, 0, 0, 0, 0]

        scenes = [Scene(name="Long", actors=("Alice",), duration_slots=2)]
        result = compute_all_scene_feasibility(scenes, {"Alice": matrix})

        labels = [interval_label(s.day_index, s.start_slot, s.duration_slots) for s in result["Long"]]
        self.assertEqual(labels, ["Mon 20:00-24:00", "Tue 10:00-14:00"])

    def test_no_overlap(self) -> None:
        alice = blank_matrix()
        bob = blank_matrix()
        alice[2][0] = 1
        bob[2][1] = 1

        scenes = [Scene(name="None", actors=("Alice", "Bob"), duration_slots=1)]
        result = compute_all_scene_feasibility(scenes, {"Alice": alice, "Bob": bob})

        self.assertEqual(result["None"], [])

    def test_loader_rejects_bad_matrix_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            actors_path = Path(tmp) / "actors.json"
            actors_path.write_text(json.dumps({"Alice": [[1, 0]]}), encoding="utf-8")
            with self.assertRaises(DataValidationError):
                load_actor_availability(actors_path)

    def test_loader_rejects_unknown_actor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            actors_path = Path(tmp) / "actors.json"
            scenes_path = Path(tmp) / "scenes.json"

            actors_path.write_text(
                json.dumps({"Alice": blank_matrix()}),
                encoding="utf-8",
            )
            scenes_path.write_text(
                json.dumps([
                    {"name": "Scene", "actors": ["Alice", "Bob"], "duration_slots": 1}
                ]),
                encoding="utf-8",
            )

            actors = load_actor_availability(actors_path)
            with self.assertRaises(DataValidationError):
                load_scenes(scenes_path, set(actors))

    def test_cli_human_and_json_output(self) -> None:
        root = Path(__file__).resolve().parent.parent
        actors_path = root / "data" / "actors.sample.json"
        scenes_path = root / "data" / "scenes.sample.json"

        proc_human = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--actors",
                str(actors_path),
                "--scenes",
                str(scenes_path),
                "--format",
                "human",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc_human.returncode, 0, msg=proc_human.stderr)
        self.assertIn("Scene 01 - Arrival Drill:", proc_human.stdout)
        self.assertIn("Scene 10 - Final Reckoning:", proc_human.stdout)

        proc_json = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--actors",
                str(actors_path),
                "--scenes",
                str(scenes_path),
                "--format",
                "json",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc_json.returncode, 0, msg=proc_json.stderr)
        payload = json.loads(proc_json.stdout)
        self.assertIn("Scene 01 - Arrival Drill", payload)
        self.assertIsInstance(payload["Scene 01 - Arrival Drill"], list)

    def test_cli_drama_input(self) -> None:
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            drama_path = Path(tmp) / "cli-drama.json"
            write_drama_file(drama_path)

            proc = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--drama",
                    str(drama_path),
                    "--format",
                    "json",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("Scene", payload)

    def test_cli_rejects_mixed_drama_and_legacy_inputs(self) -> None:
        root = Path(__file__).resolve().parent.parent
        actors_path = root / "data" / "actors.sample.json"
        scenes_path = root / "data" / "scenes.sample.json"
        with tempfile.TemporaryDirectory() as tmp:
            drama_path = Path(tmp) / "cli-drama.json"
            write_drama_file(drama_path)

            proc = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "--drama",
                    str(drama_path),
                    "--actors",
                    str(actors_path),
                    "--scenes",
                    str(scenes_path),
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 2)
        self.assertIn("provide either --drama", proc.stderr)

    def test_cli_rejects_incomplete_legacy_input(self) -> None:
        root = Path(__file__).resolve().parent.parent
        actors_path = root / "data" / "actors.sample.json"

        proc = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--actors",
                str(actors_path),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 2)
        self.assertIn("provide --drama, or both --actors and --scenes", proc.stderr)

    def test_cli_no_weekend_filter(self) -> None:
        root = Path(__file__).resolve().parent.parent
        actors_path = root / "data" / "actors.sample.json"
        scenes_path = root / "data" / "scenes.sample.json"

        proc = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--actors",
                str(actors_path),
                "--scenes",
                str(scenes_path),
                "--format",
                "human",
                "--no-weekend",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertNotIn("Sat ", proc.stdout)
        self.assertNotIn("Sun ", proc.stdout)
        self.assertIn("Fri ", proc.stdout)

    def test_cli_choose_days_filter_accepts_spaced_comma_values(self) -> None:
        root = Path(__file__).resolve().parent.parent
        actors_path = root / "data" / "actors.sample.json"
        scenes_path = root / "data" / "scenes.sample.json"

        proc = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--actors",
                str(actors_path),
                "--scenes",
                str(scenes_path),
                "--format",
                "human",
                "--choose",
                "Mon,",
                "Fri",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        for line in proc.stdout.splitlines():
            if not line.startswith("  - ") or "No feasible slots" in line:
                continue
            self.assertTrue(
                "Mon " in line or "Fri " in line,
                msg=f"unexpected day in line: {line}",
            )

    def test_cli_choose_days_filter_in_json(self) -> None:
        root = Path(__file__).resolve().parent.parent
        actors_path = root / "data" / "actors.sample.json"
        scenes_path = root / "data" / "scenes.sample.json"

        proc = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--actors",
                str(actors_path),
                "--scenes",
                str(scenes_path),
                "--format",
                "json",
                "--choose",
                "Mon,Fri",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        payload = json.loads(proc.stdout)
        for slots in payload.values():
            for slot in slots:
                self.assertIn(slot["day_index"], (0, 4))

    def test_cli_combined_no_weekend_and_choose_intersects(self) -> None:
        root = Path(__file__).resolve().parent.parent
        actors_path = root / "data" / "actors.sample.json"
        scenes_path = root / "data" / "scenes.sample.json"

        proc = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--actors",
                str(actors_path),
                "--scenes",
                str(scenes_path),
                "--format",
                "human",
                "--no-weekend",
                "--choose",
                "Mon,Sat",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("Mon ", proc.stdout)
        self.assertNotIn("Sat ", proc.stdout)

    def test_cli_choose_days_filter_rejects_invalid_day(self) -> None:
        root = Path(__file__).resolve().parent.parent
        actors_path = root / "data" / "actors.sample.json"
        scenes_path = root / "data" / "scenes.sample.json"

        proc = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--actors",
                str(actors_path),
                "--scenes",
                str(scenes_path),
                "--choose",
                "Funday",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("invalid day 'Funday'", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
