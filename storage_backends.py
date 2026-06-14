"""Storage backends for project data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app_services import ProjectData, actors_to_jsonable, parse_project_payloads, scenes_to_jsonable
from loader import DataValidationError
from time_grid import DAYS, SLOT_START_HOURS, slot_label

ACTORS_WORKSHEET = "actors"
SCENES_WORKSHEET = "scenes"
ACTOR_NAME_HEADER = "actor_name"
SCENE_HEADERS = ("name", "actors", "duration_slots")


class StorageError(RuntimeError):
    """Raised when a storage backend cannot read or write project data."""


@dataclass(frozen=True)
class GoogleSheetsConfig:
    spreadsheet_id: str
    credentials: dict[str, Any]


def availability_headers() -> list[str]:
    return [
        f"{day} {slot_label(slot_idx)}"
        for day in DAYS
        for slot_idx in range(len(SLOT_START_HOURS))
    ]


def project_to_sheet_values(project: ProjectData) -> tuple[list[list[str]], list[list[str]]]:
    actors_header = [ACTOR_NAME_HEADER, *availability_headers()]
    actor_rows = [actors_header]
    for actor_name, matrix in actors_to_jsonable(project.actors).items():
        actor_rows.append(
            [
                actor_name,
                *[
                    "TRUE" if matrix[day_idx][slot_idx] else "FALSE"
                    for day_idx in range(len(DAYS))
                    for slot_idx in range(len(SLOT_START_HOURS))
                ],
            ]
        )

    scene_rows = [list(SCENE_HEADERS)]
    for scene in scenes_to_jsonable(project.scenes):
        scene_rows.append(
            [
                str(scene["name"]),
                ", ".join(str(actor) for actor in scene["actors"]),
                str(scene["duration_slots"]),
            ]
        )

    return actor_rows, scene_rows


def _row_dict(headers: list[str], row: list[str]) -> dict[str, str]:
    return {
        header: row[index].strip() if index < len(row) else ""
        for index, header in enumerate(headers)
    }


def _parse_actor_names(value: str) -> list[str]:
    cleaned = value.strip()
    if not cleaned:
        return []
    if cleaned.startswith("["):
        import json

        parsed = json.loads(cleaned)
        if not isinstance(parsed, list):
            raise DataValidationError("scene actors JSON must be an array")
        return [str(actor).strip() for actor in parsed if str(actor).strip()]
    return [actor.strip() for actor in cleaned.split(",") if actor.strip()]


def _required_headers(headers: list[str], required: list[str], worksheet_name: str) -> None:
    missing = [header for header in required if header not in headers]
    if missing:
        missing_list = ", ".join(missing)
        raise DataValidationError(f"{worksheet_name} worksheet is missing columns: {missing_list}")


def project_from_sheet_values(
    actor_rows: list[list[str]],
    scene_rows: list[list[str]],
) -> ProjectData:
    if not actor_rows:
        raise DataValidationError("actors worksheet is empty")
    if not scene_rows:
        raise DataValidationError("scenes worksheet is empty")

    actor_headers = [header.strip() for header in actor_rows[0]]
    slot_headers = availability_headers()
    _required_headers(actor_headers, [ACTOR_NAME_HEADER, *slot_headers], ACTORS_WORKSHEET)

    actors: dict[str, list[list[str | int]]] = {}
    for row in actor_rows[1:]:
        row_data = _row_dict(actor_headers, row)
        actor_name = row_data[ACTOR_NAME_HEADER].strip()
        if not actor_name:
            continue
        actors[actor_name] = [
            [
                row_data.get(f"{day} {slot_label(slot_idx)}", "").strip() or 0
                for slot_idx in range(len(SLOT_START_HOURS))
            ]
            for day in DAYS
        ]

    scene_headers = [header.strip() for header in scene_rows[0]]
    _required_headers(scene_headers, list(SCENE_HEADERS), SCENES_WORKSHEET)

    scenes: list[dict[str, object]] = []
    for row in scene_rows[1:]:
        row_data = _row_dict(scene_headers, row)
        scene_name = row_data["name"].strip()
        if not scene_name:
            continue
        scene: dict[str, object] = {
            "name": scene_name,
            "actors": _parse_actor_names(row_data["actors"]),
        }
        duration = row_data["duration_slots"].strip()
        if duration:
            scene["duration_slots"] = int(duration)
        scenes.append(scene)

    return parse_project_payloads(actors, scenes)


class GoogleSheetsStorage:
    def __init__(self, config: GoogleSheetsConfig):
        self.config = config

    def load_project(self) -> ProjectData:
        spreadsheet = self._spreadsheet()
        try:
            actors_ws = spreadsheet.worksheet(ACTORS_WORKSHEET)
            scenes_ws = spreadsheet.worksheet(SCENES_WORKSHEET)
        except Exception as exc:
            if exc.__class__.__name__ == "WorksheetNotFound":
                raise StorageError(
                    "Google Sheet must contain worksheets named 'actors' and 'scenes'. "
                    "Use 'Save to Google Sheets' once to create them."
                ) from exc
            raise

        return project_from_sheet_values(
            actors_ws.get_all_values(),
            scenes_ws.get_all_values(),
        )

    def save_project(self, project: ProjectData) -> None:
        actor_rows, scene_rows = project_to_sheet_values(project)
        spreadsheet = self._spreadsheet()
        self._write_worksheet(spreadsheet, ACTORS_WORKSHEET, actor_rows)
        self._write_worksheet(spreadsheet, SCENES_WORKSHEET, scene_rows)

    def _spreadsheet(self):
        try:
            import gspread
        except ModuleNotFoundError as exc:
            raise StorageError(
                "Google Sheets support requires gspread. Install dependencies with "
                "`python3 -m pip install -r requirements.txt`."
            ) from exc

        credentials = dict(self.config.credentials)
        private_key = credentials.get("private_key")
        if isinstance(private_key, str):
            credentials["private_key"] = private_key.replace("\\n", "\n")

        try:
            client = gspread.service_account_from_dict(credentials)
            return client.open_by_key(self.config.spreadsheet_id.strip())
        except Exception as exc:
            raise StorageError(f"Could not open Google Sheet: {exc}") from exc

    @staticmethod
    def _write_worksheet(spreadsheet, title: str, values: list[list[str]]) -> None:
        try:
            worksheet = spreadsheet.worksheet(title)
        except Exception as exc:
            if exc.__class__.__name__ != "WorksheetNotFound":
                raise
            worksheet = spreadsheet.add_worksheet(
                title=title,
                rows=max(len(values), 1),
                cols=max(len(values[0]) if values else 1, 1),
            )

        worksheet.clear()
        if values:
            worksheet.update(values, "A1")
