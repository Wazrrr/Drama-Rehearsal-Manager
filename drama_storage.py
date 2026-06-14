"""Local drama storage for the Streamlit app and drama-aware CLI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from app_services import (
    ProjectData,
    actors_to_jsonable,
    empty_project,
    parse_project_payloads,
    scenes_to_jsonable,
    validate_project,
)
from loader import DataValidationError

DRAMA_SCHEMA_VERSION = 1
DEFAULT_LOCAL_DATA_DIR = Path(".local_data")
DRAMAS_FOLDER_NAME = "dramas"
APP_STATE_FILENAME = "app_state.json"


@dataclass(frozen=True)
class Drama:
    id: str
    name: str
    created_at: str
    updated_at: str
    project: ProjectData


@dataclass(frozen=True)
class DramaSummary:
    id: str
    name: str
    updated_at: str
    path: Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def dramas_dir(data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR) -> Path:
    return Path(data_dir) / DRAMAS_FOLDER_NAME


def app_state_path(data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR) -> Path:
    return Path(data_dir) / APP_STATE_FILENAME


def drama_path(drama_id: str, data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR) -> Path:
    return dramas_dir(data_dir) / f"{drama_id}.json"


def clean_drama_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise DataValidationError("Drama name is required.")
    return cleaned


def drama_id_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "drama"


def _unique_drama_id(name: str, data_dir: str | Path) -> str:
    base_id = drama_id_from_name(name)
    candidate = base_id
    counter = 2
    while drama_path(candidate, data_dir).exists():
        candidate = f"{base_id}-{counter}"
        counter += 1
    return candidate


def _read_json_file(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise DataValidationError(f"drama file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataValidationError(f"invalid drama JSON in {path}: {exc}") from exc


def parse_drama_payload(payload: object, *, fallback_id: str | None = None) -> Drama:
    if not isinstance(payload, dict):
        raise DataValidationError("drama file must be a JSON object")

    schema_version = payload.get("schema_version")
    if schema_version != DRAMA_SCHEMA_VERSION:
        raise DataValidationError(f"unsupported drama schema_version: {schema_version!r}")

    drama_id = str(payload.get("id") or fallback_id or "").strip()
    if not drama_id:
        raise DataValidationError("drama file is missing id")
    if drama_id != drama_id_from_name(drama_id):
        raise DataValidationError("drama id must contain only lowercase letters, numbers, and hyphens")

    name_value = payload.get("name", "")
    if not isinstance(name_value, str):
        raise DataValidationError("drama name must be a string")
    name = clean_drama_name(name_value)
    created_at = str(payload.get("created_at") or utc_now_iso())
    updated_at = str(payload.get("updated_at") or created_at)
    project = parse_project_payloads(
        payload.get("actors", {}),
        payload.get("scenes", []),
        allow_empty=True,
    )
    return Drama(
        id=drama_id,
        name=name,
        created_at=created_at,
        updated_at=updated_at,
        project=project,
    )


def drama_to_jsonable(drama: Drama) -> dict[str, object]:
    validate_project(drama.project, allow_empty=True)
    return {
        "schema_version": DRAMA_SCHEMA_VERSION,
        "id": drama.id,
        "name": drama.name,
        "created_at": drama.created_at,
        "updated_at": drama.updated_at,
        "actors": actors_to_jsonable(drama.project.actors),
        "scenes": scenes_to_jsonable(drama.project.scenes),
    }


def dump_drama_json(drama: Drama) -> str:
    return json.dumps(drama_to_jsonable(drama), ensure_ascii=False, indent=2) + "\n"


def load_drama_file(path: str | Path) -> Drama:
    src = Path(path)
    return parse_drama_payload(_read_json_file(src), fallback_id=src.stem)


def load_drama(drama_id: str, data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR) -> Drama:
    return load_drama_file(drama_path(drama_id, data_dir))


def save_drama(
    drama: Drama,
    data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR,
    *,
    refresh_updated_at: bool = True,
) -> Drama:
    saved = replace(drama, updated_at=utc_now_iso()) if refresh_updated_at else drama
    path = drama_path(saved.id, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_drama_json(saved), encoding="utf-8")
    return saved


def list_dramas(data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR) -> list[DramaSummary]:
    folder = dramas_dir(data_dir)
    if not folder.exists():
        return []

    summaries: list[DramaSummary] = []
    for path in sorted(folder.glob("*.json")):
        try:
            drama = load_drama_file(path)
        except DataValidationError:
            continue
        summaries.append(
            DramaSummary(
                id=drama.id,
                name=drama.name,
                updated_at=drama.updated_at,
                path=path,
            )
        )
    return sorted(summaries, key=lambda item: (item.name.lower(), item.id))


def drama_name_exists(
    name: str,
    data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR,
    *,
    exclude_id: str | None = None,
) -> bool:
    cleaned = clean_drama_name(name).casefold()
    return any(
        summary.name.casefold() == cleaned and summary.id != exclude_id
        for summary in list_dramas(data_dir)
    )


def create_drama(
    name: str,
    data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR,
    *,
    project: ProjectData | None = None,
) -> Drama:
    cleaned = clean_drama_name(name)
    if drama_name_exists(cleaned, data_dir):
        raise DataValidationError("Drama names must be unique.")
    now = utc_now_iso()
    drama = Drama(
        id=_unique_drama_id(cleaned, data_dir),
        name=cleaned,
        created_at=now,
        updated_at=now,
        project=project or empty_project(),
    )
    return save_drama(drama, data_dir, refresh_updated_at=False)


def rename_drama(
    drama_id: str,
    name: str,
    data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR,
) -> Drama:
    cleaned = clean_drama_name(name)
    if drama_name_exists(cleaned, data_dir, exclude_id=drama_id):
        raise DataValidationError("Drama names must be unique.")
    drama = load_drama(drama_id, data_dir)
    return save_drama(replace(drama, name=cleaned), data_dir)


def delete_drama(drama_id: str, data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR) -> None:
    path = drama_path(drama_id, data_dir)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    if read_last_drama_id(data_dir) == drama_id:
        clear_last_drama_id(data_dir)


def _read_app_state(data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR) -> dict[str, object]:
    path = app_state_path(data_dir)
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_app_state(
    payload: dict[str, object],
    data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR,
) -> None:
    path = app_state_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_last_drama_id(data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR) -> str | None:
    drama_id = str(_read_app_state(data_dir).get("last_drama_id", "")).strip()
    return drama_id or None


def remember_last_drama_id(
    drama_id: str,
    data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR,
) -> None:
    _write_app_state({"last_drama_id": drama_id}, data_dir)


def clear_last_drama_id(data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR) -> None:
    path = app_state_path(data_dir)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def choose_initial_drama(data_dir: str | Path = DEFAULT_LOCAL_DATA_DIR) -> Drama | None:
    summaries = list_dramas(data_dir)
    if not summaries:
        return None

    last_id = read_last_drama_id(data_dir)
    if last_id and any(summary.id == last_id for summary in summaries):
        try:
            return load_drama(last_id, data_dir)
        except DataValidationError:
            pass

    return load_drama(summaries[0].id, data_dir)
