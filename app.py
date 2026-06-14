"""Streamlit web app for local rehearsal scene matching."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from app_services import (
    ProjectData,
    actors_to_jsonable,
    compute_project_results,
    dump_actors_json,
    dump_scenes_json,
    export_results_json,
    export_results_text,
    load_default_project,
    load_project,
    parse_project_payloads,
    result_rows,
    save_project,
    scenes_to_jsonable,
    validate_project,
)
from day_filters import filter_results_by_day_indexes
from loader import DataValidationError
from models import Scene
from storage_backends import GoogleSheetsConfig, GoogleSheetsStorage, StorageError
from time_grid import DAYS, SLOT_START_HOURS, slot_label

LOCAL_ACTORS_PATH = Path("private_data/actors.json")
LOCAL_SCENES_PATH = Path("private_data/scenes.json")
LOCAL_GOOGLE_CREDENTIALS_PATH = Path(".streamlit/google_service_account.json")
LOCAL_GOOGLE_CONFIG_PATH = Path(".streamlit/google_sheets.json")
PROJECT_UI_EXACT_KEYS = {"actor_selector", "scene_selector", "add_scene_actors"}
PROJECT_UI_KEY_PREFIXES = (
    "new_actor_name_",
    "actor_selector_",
    "rename_actor_",
    "availability_editor_",
    "add_scene_name_",
    "add_scene_actors_",
    "add_scene_duration_",
    "scene_selector_",
    "edit_scene_name_",
    "edit_scene_actors_",
    "edit_scene_duration_",
)


def blank_matrix() -> list[list[bool]]:
    return [[False for _ in SLOT_START_HOURS] for _ in DAYS]


def project_ui_revision() -> int:
    return int(st.session_state.get("project_ui_revision", 0))


def project_widget_key(name: str) -> str:
    return f"{name}_{project_ui_revision()}"


def reset_project_ui_state() -> None:
    st.session_state.project_ui_revision = project_ui_revision() + 1
    for key in list(st.session_state.keys()):
        key_name = str(key)
        if key_name in PROJECT_UI_EXACT_KEYS or key_name.startswith(PROJECT_UI_KEY_PREFIXES):
            del st.session_state[key]


def pop_session_value(key: str) -> object | None:
    if key not in st.session_state:
        return None
    value = st.session_state[key]
    del st.session_state[key]
    return value


def set_project(project: ProjectData, *, reset_ui_state: bool = False) -> None:
    st.session_state.project = project
    st.session_state.load_error = None
    if reset_ui_state:
        reset_project_ui_state()


def get_project() -> ProjectData:
    return st.session_state.project


def load_local_project() -> ProjectData:
    missing_paths = [
        str(path)
        for path in (LOCAL_ACTORS_PATH, LOCAL_SCENES_PATH)
        if not path.exists()
    ]
    if missing_paths:
        raise DataValidationError(f"Missing local JSON file(s): {', '.join(missing_paths)}")
    return load_project(LOCAL_ACTORS_PATH, LOCAL_SCENES_PATH)


def initialize_state() -> None:
    if "project" in st.session_state:
        return

    try:
        loaded = load_default_project()
    except DataValidationError as exc:
        st.session_state.load_error = str(exc)
        st.session_state.project = ProjectData(actors={}, scenes=[])
        st.session_state.loaded_paths = ("none", "none")
        return

    st.session_state.project = loaded.data
    st.session_state.loaded_paths = (str(loaded.actors_path), str(loaded.scenes_path))
    st.session_state.load_error = None


def rerun() -> None:
    st.rerun()


def render_shell() -> None:
    st.set_page_config(page_title="Rehearsal Manager", layout="wide")
    preserve_copy_shortcut()
    st.markdown(
        """
        <style>
          .block-container { padding-top: 1.5rem; }
          div[data-testid="stMetric"] { border: 1px solid #e5e7eb; padding: .75rem; border-radius: 8px; }
          div[data-testid="stDataFrame"] { border: 1px solid #e5e7eb; border-radius: 8px; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("Rehearsal Manager")


def preserve_copy_shortcut() -> None:
    components.html(
        """
        <script>
        (() => {
          const parentDocument = window.parent.document;
          if (parentDocument.__rehearsalCopyShortcutGuard) {
            return;
          }
          parentDocument.__rehearsalCopyShortcutGuard = true;
          parentDocument.addEventListener("keydown", (event) => {
            const key = (event.key || "").toLowerCase();
            if ((event.metaKey || event.ctrlKey) && key === "c") {
              event.stopImmediatePropagation();
            }
          }, true);
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def _load_json_file(path: Path) -> dict[str, object] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _save_json_file(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _validate_google_credentials(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("service account credentials must be a JSON object")
    missing = [
        field
        for field in ("type", "client_email", "private_key")
        if not str(payload.get(field, "")).strip()
    ]
    if missing:
        raise ValueError(f"service account JSON is missing: {', '.join(missing)}")
    if payload.get("type") != "service_account":
        raise ValueError("service account JSON must have type = service_account")
    return dict(payload)


def _parse_credentials_input(uploaded_file, pasted_json: str) -> dict[str, object]:
    if uploaded_file is not None:
        raw = uploaded_file.getvalue().decode("utf-8")
    else:
        raw = pasted_json.strip()
    if not raw:
        raise ValueError("upload or paste a Google service account JSON file")
    return _validate_google_credentials(json.loads(raw))


def local_google_credentials() -> dict[str, object] | None:
    payload = _load_json_file(LOCAL_GOOGLE_CREDENTIALS_PATH)
    if payload is None:
        return None
    try:
        return _validate_google_credentials(payload)
    except ValueError:
        return None


def local_google_spreadsheet_id() -> str:
    payload = _load_json_file(LOCAL_GOOGLE_CONFIG_PATH) or {}
    return str(payload.get("spreadsheet_id", "")).strip()


def remember_google_spreadsheet_id(spreadsheet_id: str) -> None:
    cleaned = spreadsheet_id.strip()
    if cleaned:
        _save_json_file(LOCAL_GOOGLE_CONFIG_PATH, {"spreadsheet_id": cleaned})


def google_credentials_source() -> str:
    if st.session_state.get("google_service_account_credentials"):
        return "website input"
    try:
        if "google_service_account" in st.secrets:
            return "Streamlit secrets"
    except FileNotFoundError:
        pass
    if local_google_credentials() is not None:
        return "local .streamlit file"
    return "none"


def google_service_account_credentials() -> dict[str, object] | None:
    session_credentials = st.session_state.get("google_service_account_credentials")
    if session_credentials:
        return dict(session_credentials)
    try:
        credentials = st.secrets["google_service_account"]
    except (FileNotFoundError, KeyError):
        return local_google_credentials()
    return dict(credentials)


def default_google_spreadsheet_id() -> str:
    try:
        config = st.secrets.get("google_sheets", {})
    except FileNotFoundError:
        return local_google_spreadsheet_id()
    return str(config.get("spreadsheet_id", "")).strip() or local_google_spreadsheet_id()


def google_storage(spreadsheet_id: str) -> GoogleSheetsStorage:
    credentials = google_service_account_credentials()
    if not credentials:
        raise StorageError("Missing [google_service_account] credentials in Streamlit secrets.")
    if not spreadsheet_id.strip():
        raise StorageError("Google Sheets storage requires a spreadsheet ID.")
    return GoogleSheetsStorage(
        GoogleSheetsConfig(spreadsheet_id=spreadsheet_id.strip(), credentials=credentials)
    )


def render_google_sheets_tutorial() -> None:
    with st.sidebar.expander("Google Sheets setup guide"):
        st.markdown(
            """
            1. In Google Cloud Console, enable **Google Sheets API** and **Google Drive API**.
            2. Create a **service account**.
            3. Create and download a **JSON key** for that service account.
            4. Open your Google Sheet and share it with the service account `client_email` as an editor.
            5. Copy the spreadsheet ID from the sheet URL and paste it above.
            6. Upload or paste the downloaded service account JSON below.

            Spreadsheet URL shape:

            `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`

            Required worksheets:

            - `actors`
            - `scenes`

            If the worksheets do not exist, save to Google Sheets once and the app will create them.
            """
        )
        st.code(
            """{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "your-private-key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n",
  "client_email": "your-service-account@your-project.iam.gserviceaccount.com",
  "client_id": "your-client-id",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/...",
  "universe_domain": "googleapis.com"
}""",
            language="json",
        )


def render_sidebar() -> None:
    project = get_project()
    loaded_actors, loaded_scenes = st.session_state.get("loaded_paths", ("none", "none"))

    st.sidebar.header("Storage")
    storage_backend = st.sidebar.selectbox(
        "Storage backend",
        ["Local JSON", "Google Sheets"],
        key="storage_backend",
    )
    st.sidebar.caption(f"Loaded actors: `{loaded_actors}`")
    st.sidebar.caption(f"Loaded scenes: `{loaded_scenes}`")
    sidebar_success = pop_session_value("sidebar_success")
    if sidebar_success:
        st.sidebar.success(str(sidebar_success))

    try:
        validate_project(project)
        can_save = True
    except DataValidationError as exc:
        can_save = False
        st.sidebar.error(str(exc))

    if storage_backend == "Local JSON":
        if st.sidebar.button("Load from local JSON", width="stretch"):
            try:
                loaded = load_local_project()
            except DataValidationError as exc:
                st.sidebar.error(str(exc))
            else:
                set_project(loaded, reset_ui_state=True)
                st.session_state.loaded_paths = (str(LOCAL_ACTORS_PATH), str(LOCAL_SCENES_PATH))
                st.session_state.sidebar_success = "Loaded local project files."
                rerun()

        if st.sidebar.button("Save to local JSON", disabled=not can_save, width="stretch"):
            save_project(project, LOCAL_ACTORS_PATH, LOCAL_SCENES_PATH)
            st.session_state.loaded_paths = (str(LOCAL_ACTORS_PATH), str(LOCAL_SCENES_PATH))
            st.sidebar.success("Saved private_data/actors.json and private_data/scenes.json.")

    if storage_backend == "Google Sheets":
        credentials_present = google_service_account_credentials() is not None
        spreadsheet_id = st.sidebar.text_input(
            "Spreadsheet ID",
            value=st.session_state.get("google_spreadsheet_id", default_google_spreadsheet_id()),
            key="google_spreadsheet_id",
            help=(
                "Copy the ID from a Google Sheet URL like "
                "https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit. "
                "Share the sheet with the service account client_email as an editor."
            ),
        )
        st.sidebar.caption("Uses worksheets named `actors` and `scenes`.")
        st.sidebar.caption(f"Credentials: `{google_credentials_source()}`")
        render_google_sheets_tutorial()

        with st.sidebar.expander("Google credentials"):
            uploaded_credentials = st.file_uploader(
                "Service account JSON",
                type="json",
                key="google_credentials_file",
                help=(
                    "Upload the JSON key downloaded from Google Cloud Console for a service "
                    "account. The JSON must include type, client_email, private_key, and token_uri."
                ),
            )
            pasted_credentials = st.text_area(
                "Paste service account JSON",
                height=120,
                key="google_credentials_text",
                help=(
                    "Paste the complete service account JSON object. Do not paste only the "
                    "private key. The app validates that type, client_email, and private_key exist."
                ),
            )
            save_for_refresh = st.checkbox(
                "Save locally for browser refresh",
                value=True,
                help=(
                    "Stores credentials in .streamlit/google_service_account.json and the "
                    "spreadsheet ID in .streamlit/google_sheets.json. The .streamlit directory "
                    "is ignored by Git except config.toml."
                ),
            )
            if st.button("Apply Google credentials", width="stretch"):
                try:
                    credentials = _parse_credentials_input(uploaded_credentials, pasted_credentials)
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                    st.error(str(exc))
                else:
                    st.session_state.google_service_account_credentials = credentials
                    if save_for_refresh:
                        _save_json_file(LOCAL_GOOGLE_CREDENTIALS_PATH, credentials)
                        if spreadsheet_id.strip():
                            remember_google_spreadsheet_id(spreadsheet_id)
                    st.success("Google credentials applied.")
                    rerun()

        if not credentials_present:
            st.sidebar.error("Add Google service account credentials first.")

        google_ready = credentials_present and bool(spreadsheet_id.strip())
        if st.sidebar.button("Load from Google Sheets", disabled=not google_ready, width="stretch"):
            try:
                set_project(google_storage(spreadsheet_id).load_project(), reset_ui_state=True)
            except (StorageError, DataValidationError, ValueError) as exc:
                st.sidebar.error(str(exc))
            else:
                st.session_state.loaded_paths = ("Google Sheets: actors", "Google Sheets: scenes")
                remember_google_spreadsheet_id(spreadsheet_id)
                st.session_state.sidebar_success = "Loaded project from Google Sheets."
                rerun()

        if st.sidebar.button(
            "Save to Google Sheets",
            disabled=not google_ready or not can_save,
            width="stretch",
        ):
            try:
                google_storage(spreadsheet_id).save_project(project)
            except (StorageError, DataValidationError, ValueError) as exc:
                st.sidebar.error(str(exc))
            else:
                st.session_state.loaded_paths = ("Google Sheets: actors", "Google Sheets: scenes")
                remember_google_spreadsheet_id(spreadsheet_id)
                st.sidebar.success("Saved project to Google Sheets.")

    st.sidebar.download_button(
        "Download actors.json",
        data=dump_actors_json(project.actors),
        file_name="actors.json",
        mime="application/json",
        width="stretch",
    )
    st.sidebar.download_button(
        "Download scenes.json",
        data=dump_scenes_json(project.scenes),
        file_name="scenes.json",
        mime="application/json",
        width="stretch",
    )


def rename_actor(project: ProjectData, old_name: str, new_name: str) -> None:
    renamed_actors: dict[str, list[list[bool]]] = {}
    for actor_name, matrix in project.actors.items():
        renamed_actors[new_name if actor_name == old_name else actor_name] = matrix

    renamed_scenes = [
        Scene(
            name=scene.name,
            actors=tuple(new_name if actor == old_name else actor for actor in scene.actors),
            duration_slots=scene.duration_slots,
        )
        for scene in project.scenes
    ]
    project.actors = renamed_actors
    project.scenes = renamed_scenes


def render_actors_tab() -> None:
    project = get_project()
    actor_names = list(project.actors)

    st.subheader("Actors")
    add_col, _ = st.columns([1, 2])
    with add_col.form("add_actor"):
        new_actor = st.text_input("New actor name", key=project_widget_key("new_actor_name"))
        submitted = st.form_submit_button("Add actor", width="stretch")
        if submitted:
            cleaned = new_actor.strip()
            if not cleaned:
                st.error("Actor name is required.")
            elif cleaned in project.actors:
                st.error("Actor names must be unique.")
            else:
                project.actors[cleaned] = blank_matrix()
                st.success(f"Added {cleaned}.")
                rerun()

    if not actor_names:
        st.info("Add an actor to start building availability.")
        return

    selected = st.selectbox("Actor", actor_names, key=project_widget_key("actor_selector"))
    used_in = [scene.name for scene in project.scenes if selected in scene.actors]

    rename_col, delete_col = st.columns([2, 1])
    with rename_col.form("rename_actor"):
        updated_name = st.text_input(
            "Actor name",
            value=selected,
            key=project_widget_key(f"rename_actor_{selected}"),
        )
        renamed = st.form_submit_button("Rename actor", width="stretch")
        if renamed:
            cleaned = updated_name.strip()
            if not cleaned:
                st.error("Actor name is required.")
            elif cleaned != selected and cleaned in project.actors:
                st.error("Actor names must be unique.")
            elif cleaned != selected:
                rename_actor(project, selected, cleaned)
                st.success("Actor renamed and scene references updated.")
                rerun()

    with delete_col:
        st.write("")
        st.write("")
        if used_in:
            st.warning("Remove this actor from scenes before deleting.")
            st.button("Delete actor", disabled=True, width="stretch")
        elif st.button("Delete actor", width="stretch"):
            del project.actors[selected]
            st.success("Actor deleted.")
            rerun()

    st.markdown("#### Availability")
    columns = [slot_label(slot_idx) for slot_idx in range(len(SLOT_START_HOURS))]
    source = pd.DataFrame(project.actors[selected], columns=columns)
    source.insert(0, "Day", DAYS)
    edited = st.data_editor(
        source,
        hide_index=True,
        disabled=["Day"],
        num_rows="fixed",
        width="stretch",
        column_config={
            column: st.column_config.CheckboxColumn(column)
            for column in columns
        },
        key=project_widget_key(f"availability_editor_{selected}"),
    )
    if st.button("Apply availability", width="stretch"):
        project.actors[selected] = [
            [bool(edited.loc[row_index, column]) for column in columns]
            for row_index in range(len(DAYS))
        ]
        st.success("Availability updated.")
        rerun()


def scene_summary(project: ProjectData) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Scene": scene.name,
                "Actors": ", ".join(scene.actors),
                "Duration": f"{scene.duration_slots} slot(s) / {scene.duration_slots * 2} hour(s)",
            }
            for scene in project.scenes
        ]
    )


def render_scenes_tab() -> None:
    project = get_project()
    actor_names = list(project.actors)

    st.subheader("Scenes")
    if project.scenes:
        st.dataframe(scene_summary(project), hide_index=True, width="stretch")
    else:
        st.info("Add a scene to start matching rehearsal slots.")

    with st.form("add_scene"):
        st.markdown("#### Add Scene")
        name = st.text_input("Scene name", key=project_widget_key("add_scene_name"))
        actors = st.multiselect("Actors", actor_names, key=project_widget_key("add_scene_actors"))
        duration = st.number_input(
            "Duration slots",
            min_value=1,
            max_value=7,
            value=1,
            step=1,
            key=project_widget_key("add_scene_duration"),
        )
        submitted = st.form_submit_button("Add scene", width="stretch")
        if submitted:
            cleaned = name.strip()
            if not cleaned:
                st.error("Scene name is required.")
            elif any(scene.name == cleaned for scene in project.scenes):
                st.error("Scene names must be unique.")
            elif not actors:
                st.error("Choose at least one actor.")
            else:
                project.scenes.append(
                    Scene(name=cleaned, actors=tuple(actors), duration_slots=int(duration))
                )
                st.success("Scene added.")
                rerun()

    if not project.scenes:
        return

    st.markdown("#### Edit Scene")
    scene_names = [scene.name for scene in project.scenes]
    selected_name = st.selectbox("Scene", scene_names, key=project_widget_key("scene_selector"))
    selected_index = scene_names.index(selected_name)
    selected_scene = project.scenes[selected_index]

    with st.form("edit_scene"):
        edited_name = st.text_input(
            "Scene name",
            value=selected_scene.name,
            key=project_widget_key(f"edit_scene_name_{selected_name}"),
        )
        edited_actors = st.multiselect(
            "Actors",
            actor_names,
            default=list(selected_scene.actors),
            key=project_widget_key(f"edit_scene_actors_{selected_name}"),
        )
        edited_duration = st.number_input(
            "Duration slots",
            min_value=1,
            max_value=7,
            value=selected_scene.duration_slots,
            step=1,
            key=project_widget_key(f"edit_scene_duration_{selected_name}"),
        )
        saved = st.form_submit_button("Save scene", width="stretch")
        if saved:
            cleaned = edited_name.strip()
            duplicate = any(
                scene.name == cleaned and idx != selected_index
                for idx, scene in enumerate(project.scenes)
            )
            if not cleaned:
                st.error("Scene name is required.")
            elif duplicate:
                st.error("Scene names must be unique.")
            elif not edited_actors:
                st.error("Choose at least one actor.")
            else:
                project.scenes[selected_index] = Scene(
                    name=cleaned,
                    actors=tuple(edited_actors),
                    duration_slots=int(edited_duration),
                )
                st.success("Scene updated.")
                rerun()

    if st.button("Delete selected scene", width="stretch"):
        del project.scenes[selected_index]
        st.success("Scene deleted.")
        rerun()


def render_results_tab() -> None:
    project = get_project()
    st.subheader("Results")

    filter_col, metric_col = st.columns([2, 1])
    with filter_col:
        chosen_days = st.multiselect("Days", list(DAYS), default=list(DAYS))
        no_weekend = st.checkbox("Exclude weekends")

    allowed_day_indexes = {DAYS.index(day) for day in chosen_days}
    if no_weekend:
        allowed_day_indexes -= {5, 6}

    try:
        results = compute_project_results(project)
    except DataValidationError as exc:
        st.error(str(exc))
        return

    filtered = filter_results_by_day_indexes(results, allowed_day_indexes)
    rows = result_rows(filtered)
    total_slots = sum(len(slots) for slots in filtered.values())
    scenes_with_slots = sum(1 for slots in filtered.values() if slots)

    with metric_col:
        st.metric("Scenes", len(project.scenes))
        st.metric("Scenes with slots", scenes_with_slots)
        st.metric("Feasible slots", total_slots)

    if not allowed_day_indexes:
        st.warning("No days are selected.")

    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    dl_col1, dl_col2 = st.columns(2)
    dl_col1.download_button(
        "Download results JSON",
        data=export_results_json(filtered),
        file_name="rehearsal-results.json",
        mime="application/json",
        width="stretch",
    )
    dl_col2.download_button(
        "Download results text",
        data=export_results_text(filtered),
        file_name="rehearsal-results.txt",
        mime="text/plain",
        width="stretch",
    )


def render_json_tab() -> None:
    project = get_project()
    st.subheader("JSON")

    upload_col1, upload_col2 = st.columns(2)
    actors_file = upload_col1.file_uploader("Actors JSON", type="json")
    scenes_file = upload_col2.file_uploader("Scenes JSON", type="json")

    if st.button("Import uploaded JSON", width="stretch"):
        if actors_file is None or scenes_file is None:
            st.error("Upload both actors and scenes JSON files.")
        else:
            try:
                actors_payload = json.loads(actors_file.getvalue().decode("utf-8"))
                scenes_payload = json.loads(scenes_file.getvalue().decode("utf-8"))
                set_project(parse_project_payloads(actors_payload, scenes_payload), reset_ui_state=True)
            except (UnicodeDecodeError, json.JSONDecodeError, DataValidationError) as exc:
                st.error(f"Import failed: {exc}")
            else:
                st.session_state.main_success = "Imported project JSON."
                rerun()

    view_col1, view_col2 = st.columns(2)
    with view_col1:
        st.markdown("#### actors.json")
        st.code(
            json.dumps(actors_to_jsonable(project.actors), ensure_ascii=False, indent=2),
            language="json",
        )
    with view_col2:
        st.markdown("#### scenes.json")
        st.code(
            json.dumps(scenes_to_jsonable(project.scenes), ensure_ascii=False, indent=2),
            language="json",
        )


def main() -> None:
    render_shell()
    initialize_state()
    render_sidebar()

    load_error = st.session_state.get("load_error")
    if load_error:
        st.error(load_error)
    main_success = pop_session_value("main_success")
    if main_success:
        st.success(str(main_success))

    actors_tab, scenes_tab, results_tab, json_tab = st.tabs(
        ["Actors", "Scenes", "Results", "JSON"]
    )
    with actors_tab:
        render_actors_tab()
    with scenes_tab:
        render_scenes_tab()
    with results_tab:
        render_results_tab()
    with json_tab:
        render_json_tab()


if __name__ == "__main__":
    main()
