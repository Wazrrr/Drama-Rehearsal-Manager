from __future__ import annotations

import unittest

from app import actor_availability_sheet, scene_availability_sheet
from app_services import ProjectData
from models import FeasibleSlot
from time_grid import DAYS_PER_WEEK, SLOTS_PER_DAY


def blank_matrix(value: int = 0) -> list[list[int]]:
    return [[value for _ in range(SLOTS_PER_DAY)] for _ in range(DAYS_PER_WEEK)]


class AvailabilitySheetTests(unittest.TestCase):
    def test_actor_availability_uses_weekdays_as_columns(self) -> None:
        matrix = blank_matrix()
        matrix[0][0] = 1
        matrix[1][1] = 1
        project = ProjectData(actors={"Alice": matrix}, scenes=[])

        dataframe = actor_availability_sheet(project, {0, 1})

        self.assertEqual(list(dataframe.columns), ["Time slot", "Monday", "Tuesday"])
        self.assertEqual(dataframe.loc[0, "Time slot"], "10:00-12:00")
        self.assertEqual(dataframe.loc[0, "Monday"], "Alice")
        self.assertEqual(dataframe.loc[0, "Tuesday"], "")
        self.assertEqual(dataframe.loc[1, "Tuesday"], "Alice")

    def test_scene_availability_uses_weekdays_as_columns(self) -> None:
        dataframe = scene_availability_sheet(
            {
                "Scene": [
                    FeasibleSlot(day_index=0, start_slot=0, duration_slots=1),
                    FeasibleSlot(day_index=1, start_slot=1, duration_slots=1),
                ]
            },
            {0, 1},
        )

        self.assertEqual(list(dataframe.columns), ["Time slot", "Monday", "Tuesday"])
        self.assertEqual(dataframe.loc[0, "Time slot"], "10:00-12:00")
        self.assertEqual(dataframe.loc[0, "Monday"], "Scene")
        self.assertEqual(dataframe.loc[0, "Tuesday"], "")
        self.assertEqual(dataframe.loc[1, "Tuesday"], "Scene")


if __name__ == "__main__":
    unittest.main(verbosity=2)
