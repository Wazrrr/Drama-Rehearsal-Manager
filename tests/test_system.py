from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from loader import DataValidationError, load_actor_availability, load_sessions
from matcher import compute_all_session_feasibility
from models import Session
from time_grid import DAYS_PER_WEEK, SLOTS_PER_DAY, interval_label


def blank_matrix() -> list[list[int]]:
    return [[0 for _ in range(SLOTS_PER_DAY)] for _ in range(DAYS_PER_WEEK)]


class RehearsalManagementTests(unittest.TestCase):
    def test_single_slot_intersection(self) -> None:
        alice = blank_matrix()
        bob = blank_matrix()

        alice[0] = [1, 1, 0, 1, 0, 0, 0]
        bob[0] = [1, 0, 0, 1, 1, 0, 0]

        sessions = [Session(name="Scene_1", actors=("Alice", "Bob"), duration_slots=1)]
        result = compute_all_session_feasibility(sessions, {"Alice": alice, "Bob": bob})

        labels = [interval_label(s.day_index, s.start_slot, s.duration_slots) for s in result["Scene_1"]]
        self.assertEqual(labels, ["Mon 10:00-12:00", "Mon 16:00-18:00"])

    def test_multi_slot_contiguous_window(self) -> None:
        matrix = blank_matrix()
        matrix[0] = [0, 0, 0, 0, 0, 1, 1]
        matrix[1] = [1, 1, 0, 0, 0, 0, 0]

        sessions = [Session(name="Long", actors=("Alice",), duration_slots=2)]
        result = compute_all_session_feasibility(sessions, {"Alice": matrix})

        labels = [interval_label(s.day_index, s.start_slot, s.duration_slots) for s in result["Long"]]
        self.assertEqual(labels, ["Mon 20:00-24:00", "Tue 10:00-14:00"])

    def test_no_overlap(self) -> None:
        alice = blank_matrix()
        bob = blank_matrix()
        alice[2][0] = 1
        bob[2][1] = 1

        sessions = [Session(name="None", actors=("Alice", "Bob"), duration_slots=1)]
        result = compute_all_session_feasibility(sessions, {"Alice": alice, "Bob": bob})

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
            sessions_path = Path(tmp) / "sessions.json"

            actors_path.write_text(
                json.dumps({"Alice": blank_matrix()}),
                encoding="utf-8",
            )
            sessions_path.write_text(
                json.dumps([
                    {"name": "Scene", "actors": ["Alice", "Bob"], "duration_slots": 1}
                ]),
                encoding="utf-8",
            )

            actors = load_actor_availability(actors_path)
            with self.assertRaises(DataValidationError):
                load_sessions(sessions_path, set(actors))

    def test_cli_human_and_json_output(self) -> None:
        root = Path(__file__).resolve().parent.parent
        actors_path = root / "examples" / "actors.sample.json"
        sessions_path = root / "examples" / "sessions.sample.json"

        proc_human = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--actors",
                str(actors_path),
                "--sessions",
                str(sessions_path),
                "--format",
                "human",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc_human.returncode, 0, msg=proc_human.stderr)
        self.assertIn("Scene_1:", proc_human.stdout)
        self.assertIn("Finale:", proc_human.stdout)

        proc_json = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--actors",
                str(actors_path),
                "--sessions",
                str(sessions_path),
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
        self.assertIn("Scene_1", payload)
        self.assertIsInstance(payload["Scene_1"], list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
