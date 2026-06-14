"""Streamlit web app for local rehearsal scene matching."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from app_services import (
    ProjectData,
    actors_to_jsonable,
    compute_project_results,
    dump_actors_json,
    dump_scenes_json,
    empty_project,
    merged_slot_labels,
    parse_project_payloads,
    result_rows,
    scenes_to_jsonable,
    validate_project,
)
from day_filters import filter_results_by_day_indexes
from drama_storage import (
    DEFAULT_LOCAL_DATA_DIR,
    Drama,
    choose_initial_drama,
    create_drama,
    delete_drama,
    dump_drama_json,
    list_dramas,
    load_drama,
    parse_drama_payload,
    remember_last_drama_id,
    rename_drama,
    save_drama,
)
from loader import DataValidationError
from models import FeasibleSlot, Scene
from time_grid import DAYS, SLOT_START_HOURS, slot_label

LOCAL_DATA_DIR = DEFAULT_LOCAL_DATA_DIR
APP_SECTIONS = ("Actors", "Scenes", "Results", "Advanced")
DAY_LABELS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
ACTIVE_SECTION_KEY = "active_section"
ACTIVE_SECTION_CONTROL_KEY = "active_section_control"
ACTIVE_SECTION_QUERY_PARAM = "section"
ACTION_BUTTON_WIDTH = 112
AVAILABILITY_ROW_HEIGHT = 84
AVAILABILITY_DAY_WIDTH = 116
AVAILABILITY_TIME_SLOT_WIDTH = 104
PROJECT_UI_EXACT_KEYS = {"actor_selector", "scene_selector", "add_scene_actors"}
PROJECT_UI_KEY_PREFIXES = (
    "new_actor_name_",
    "actor_selector_",
    "rename_actor_",
    "availability_editor_",
    "add_scene_name_",
    "add_scene_description_",
    "add_scene_dialog_name_",
    "add_scene_dialog_description_",
    "add_scene_dialog_actors_",
    "add_scene_dialog_duration_",
    "add_scene_actors_",
    "add_scene_duration_",
    "scene_selector_",
    "edit_scene_name_",
    "edit_scene_description_",
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


def normalize_active_section(value: object, *, fallback: object = "Actors") -> str:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value in APP_SECTIONS:
        return str(value)
    if fallback in APP_SECTIONS:
        return str(fallback)
    return "Actors"


def active_section_from_query_params() -> str:
    return normalize_active_section(st.query_params.get(ACTIVE_SECTION_QUERY_PARAM))


def persist_active_section(active_section: str) -> None:
    if st.query_params.get(ACTIVE_SECTION_QUERY_PARAM) != active_section:
        st.query_params[ACTIVE_SECTION_QUERY_PARAM] = active_section


def set_active_section(value: object, *, fallback: object = "Actors") -> str:
    active_section = normalize_active_section(value, fallback=fallback)
    st.session_state[ACTIVE_SECTION_KEY] = active_section
    persist_active_section(active_section)
    return active_section


def sync_active_section_from_control() -> None:
    set_active_section(
        st.session_state.get(ACTIVE_SECTION_CONTROL_KEY),
        fallback=st.session_state.get(ACTIVE_SECTION_KEY),
    )


def ensure_active_section_state() -> None:
    active_section = set_active_section(
        st.session_state.get(ACTIVE_SECTION_KEY),
        fallback=active_section_from_query_params(),
    )
    if st.session_state.get(ACTIVE_SECTION_CONTROL_KEY) != active_section:
        st.session_state[ACTIVE_SECTION_CONTROL_KEY] = active_section


def set_project(project: ProjectData, *, reset_ui_state: bool = False) -> None:
    st.session_state.project = project
    st.session_state.load_error = None
    if reset_ui_state:
        reset_project_ui_state()


def get_project() -> ProjectData:
    return st.session_state.project


def has_current_drama() -> bool:
    return bool(st.session_state.get("current_drama_id"))


def set_project_dirty() -> None:
    st.session_state.project_dirty = True


def clear_project_dirty() -> None:
    st.session_state.project_dirty = False


def project_is_dirty() -> bool:
    return bool(st.session_state.get("project_dirty", False))


def current_drama() -> Drama:
    if not has_current_drama():
        raise DataValidationError("Create or select a drama first.")
    return Drama(
        id=str(st.session_state.current_drama_id),
        name=str(st.session_state.current_drama_name),
        created_at=str(st.session_state.current_drama_created_at),
        updated_at=str(st.session_state.current_drama_updated_at),
        project=get_project(),
    )


def set_current_drama(drama: Drama, *, reset_ui_state: bool = False) -> None:
    st.session_state.current_drama_id = drama.id
    st.session_state.current_drama_name = drama.name
    st.session_state.current_drama_created_at = drama.created_at
    st.session_state.current_drama_updated_at = drama.updated_at
    set_project(drama.project, reset_ui_state=reset_ui_state)
    clear_project_dirty()
    remember_last_drama_id(drama.id, LOCAL_DATA_DIR)


def clear_current_drama() -> None:
    for key in (
        "current_drama_id",
        "current_drama_name",
        "current_drama_created_at",
        "current_drama_updated_at",
    ):
        st.session_state.pop(key, None)
    set_project(empty_project(), reset_ui_state=True)
    clear_project_dirty()


def save_current_drama() -> Drama:
    saved = save_drama(current_drama(), LOCAL_DATA_DIR)
    st.session_state.current_drama_updated_at = saved.updated_at
    clear_project_dirty()
    remember_last_drama_id(saved.id, LOCAL_DATA_DIR)
    return saved


def parse_uploaded_project_files(actors_file, scenes_file) -> ProjectData:
    actors_payload = json.loads(actors_file.getvalue().decode("utf-8"))
    scenes_payload = json.loads(scenes_file.getvalue().decode("utf-8"))
    return parse_project_payloads(actors_payload, scenes_payload)


def parse_uploaded_drama_file(drama_file) -> Drama:
    payload = json.loads(drama_file.getvalue().decode("utf-8"))
    return parse_drama_payload(payload)


def initialize_state() -> None:
    if "project" in st.session_state:
        return

    try:
        drama = choose_initial_drama(LOCAL_DATA_DIR)
    except DataValidationError as exc:
        st.session_state.load_error = str(exc)
        st.session_state.project = empty_project()
        clear_project_dirty()
        return

    st.session_state.load_error = None
    if drama is None:
        st.session_state.project = empty_project()
        clear_project_dirty()
    else:
        set_current_drama(drama, reset_ui_state=True)


def rerun() -> None:
    st.rerun()


def render_shell() -> None:
    st.set_page_config(page_title="Rehearsal Manager", layout="wide")
    install_keyboard_shortcuts()
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
    st.markdown(
        """
        <style>
          .st-key-delete_dialog_action button:not(:disabled),
          .st-key-delete_actor_action button:not(:disabled),
          .st-key-delete_scene_action button:not(:disabled) {
            background-color: #da3633 !important;
            border-color: #da3633 !important;
            color: white !important;
          }
          .st-key-delete_dialog_action button:not(:disabled):hover,
          .st-key-delete_actor_action button:not(:disabled):hover,
          .st-key-delete_scene_action button:not(:disabled):hover {
            background-color: #b62324 !important;
            border-color: #b62324 !important;
            color: white !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def install_keyboard_shortcuts() -> None:
    components.html(
        """
        <script>
        (() => {
          const parentDocument = window.parent.document;
          if (parentDocument.__rehearsalShortcutGuard) {
            return;
          }
          parentDocument.__rehearsalShortcutGuard = true;
          parentDocument.addEventListener("keydown", (event) => {
            const key = (event.key || "").toLowerCase();
            if ((event.metaKey || event.ctrlKey) && key === "c") {
              event.stopImmediatePropagation();
              return;
            }

            const platform = (
              navigator.userAgentData?.platform
              || navigator.platform
              || ""
            ).toLowerCase();
            const isMac = platform.includes("mac")
              || platform.includes("iphone")
              || platform.includes("ipad")
              || platform.includes("ipod");
            const saveModifier = isMac ? event.metaKey : event.ctrlKey;
            if (saveModifier && key === "s" && !event.altKey && !event.shiftKey) {
              event.preventDefault();
              event.stopImmediatePropagation();
              const saveButton = parentDocument.querySelector(
                ".st-key-save_drama_action button:not(:disabled)"
              );
              if (saveButton) {
                saveButton.click();
              }
            }
          }, true);
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def open_drama_dialog(name: str) -> None:
    st.session_state.active_drama_dialog = name


def close_drama_dialog() -> None:
    st.session_state.pop("active_drama_dialog", None)


def render_active_drama_dialog() -> None:
    active_dialog = st.session_state.get("active_drama_dialog")
    if active_dialog == "create":
        create_drama_dialog()
    elif active_dialog == "rename":
        rename_drama_dialog()
    elif active_dialog == "delete":
        delete_drama_dialog()


@st.dialog("Create drama", on_dismiss=close_drama_dialog)
def create_drama_dialog() -> None:
    if project_is_dirty():
        st.warning("Save or discard the current drama before creating another.")
        action_col1, action_col2 = st.columns(2)
        if action_col1.button(
            "Save current",
            icon=":material/save:",
            key="create_dialog_save_current",
            width="stretch",
        ):
            try:
                save_current_drama()
            except DataValidationError as exc:
                st.error(str(exc))
            else:
                close_drama_dialog()
                st.session_state.sidebar_success = "Drama saved."
                rerun()
        if action_col2.button(
            "Discard changes",
            icon=":material/undo:",
            key="create_dialog_discard_changes",
            width="stretch",
        ):
            if has_current_drama():
                set_current_drama(
                    load_drama(str(st.session_state.current_drama_id), LOCAL_DATA_DIR),
                    reset_ui_state=True,
                )
            else:
                clear_project_dirty()
            close_drama_dialog()
            st.session_state.sidebar_success = "Changes discarded."
            rerun()
        return

    with st.form("create_drama_dialog_form"):
        st.markdown("##### Drama name")
        name = st.text_input(
            "Drama name",
            key="create_dialog_drama_name",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            "Create drama",
            icon=":material/add:",
            key="create_dialog_submit",
            type="primary",
            width="stretch",
        )
        if submitted:
            try:
                drama = create_drama(name, LOCAL_DATA_DIR)
            except DataValidationError as exc:
                st.error(str(exc))
            else:
                set_current_drama(drama, reset_ui_state=True)
                close_drama_dialog()
                st.session_state.sidebar_success = "Drama created."
                rerun()


@st.dialog("Rename drama", on_dismiss=close_drama_dialog)
def rename_drama_dialog() -> None:
    if not has_current_drama():
        st.warning("Create or select a drama first.")
        return

    if project_is_dirty():
        st.warning("Save or discard changes before renaming this drama.")
        action_col1, action_col2 = st.columns(2)
        if action_col1.button(
            "Save current",
            icon=":material/save:",
            key="rename_dialog_save_current",
            width="stretch",
        ):
            try:
                save_current_drama()
            except DataValidationError as exc:
                st.error(str(exc))
            else:
                close_drama_dialog()
                st.session_state.sidebar_success = "Drama saved."
                rerun()
        if action_col2.button(
            "Discard changes",
            icon=":material/undo:",
            key="rename_dialog_discard_changes",
            width="stretch",
        ):
            set_current_drama(
                load_drama(str(st.session_state.current_drama_id), LOCAL_DATA_DIR),
                reset_ui_state=True,
            )
            close_drama_dialog()
            st.session_state.sidebar_success = "Changes discarded."
            rerun()
        return

    with st.form("rename_drama_dialog_form"):
        st.markdown("##### Drama name")
        name = st.text_input(
            "Drama name",
            value=str(st.session_state.current_drama_name),
            key="rename_dialog_drama_name",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            "Rename drama",
            icon=":material/edit:",
            key="rename_dialog_submit",
            width="stretch",
        )
        if submitted:
            try:
                drama = rename_drama(str(st.session_state.current_drama_id), name, LOCAL_DATA_DIR)
            except DataValidationError as exc:
                st.error(str(exc))
            else:
                set_current_drama(drama, reset_ui_state=False)
                close_drama_dialog()
                st.session_state.sidebar_success = "Drama renamed."
                rerun()


@st.dialog("Delete drama", on_dismiss=close_drama_dialog)
def delete_drama_dialog() -> None:
    if not has_current_drama():
        st.warning("Create or select a drama first.")
        return

    if project_is_dirty():
        st.warning("Save or discard changes before deleting this drama.")
        action_col1, action_col2 = st.columns(2)
        if action_col1.button(
            "Save current",
            icon=":material/save:",
            key="delete_dialog_save_current",
            width="stretch",
        ):
            try:
                save_current_drama()
            except DataValidationError as exc:
                st.error(str(exc))
            else:
                close_drama_dialog()
                st.session_state.sidebar_success = "Drama saved."
                rerun()
        if action_col2.button(
            "Discard changes",
            icon=":material/undo:",
            key="delete_dialog_discard_changes",
            width="stretch",
        ):
            set_current_drama(
                load_drama(str(st.session_state.current_drama_id), LOCAL_DATA_DIR),
                reset_ui_state=True,
            )
            close_drama_dialog()
            st.session_state.sidebar_success = "Changes discarded."
            rerun()
        return

    st.warning(f"Delete `{st.session_state.current_drama_name}` permanently?")
    st.markdown("##### Type the drama name to confirm")
    confirm_name = st.text_input(
        "Type the drama name to confirm",
        key="delete_dialog_confirm_name",
        label_visibility="collapsed",
    )
    delete_disabled = confirm_name != str(st.session_state.current_drama_name)
    with st.container(key="delete_dialog_action"):
        if st.button(
            "Delete drama",
            icon=":material/delete:",
            key="delete_dialog_submit",
            disabled=delete_disabled,
            width="stretch",
        ):
            delete_drama(str(st.session_state.current_drama_id), LOCAL_DATA_DIR)
            next_drama = choose_initial_drama(LOCAL_DATA_DIR)
            if next_drama is None:
                clear_current_drama()
            else:
                set_current_drama(next_drama, reset_ui_state=True)
            close_drama_dialog()
            st.session_state.sidebar_success = "Drama deleted."
            rerun()


def render_sidebar() -> None:
    project = get_project()

    st.sidebar.header("Drama")
    sidebar_success = pop_session_value("sidebar_success")
    if sidebar_success:
        st.sidebar.success(str(sidebar_success))

    try:
        validate_project(project, allow_empty=True)
        can_save = True
    except DataValidationError as exc:
        can_save = False
        st.sidebar.error(str(exc))

    summaries = list_dramas(LOCAL_DATA_DIR)
    current_id = st.session_state.get("current_drama_id")
    dirty = project_is_dirty()

    if has_current_drama() and dirty:
        st.sidebar.warning("This drama has unsaved changes.")

    if summaries and has_current_drama():
        options = [summary.id for summary in summaries]
        labels = {summary.id: summary.name for summary in summaries}
        index = options.index(current_id) if current_id in options else 0
        selected_id = st.sidebar.selectbox(
            "Drama",
            options,
            index=index,
            format_func=lambda drama_id: labels.get(drama_id, drama_id),
            key="drama_selector",
            label_visibility="collapsed",
        )
        if selected_id != current_id:
            if dirty:
                st.sidebar.warning("Save or discard changes before switching dramas.")
                switch_col1, switch_col2 = st.sidebar.columns(2)
                if switch_col1.button("Save and switch", width="stretch"):
                    try:
                        save_current_drama()
                        set_current_drama(
                            load_drama(selected_id, LOCAL_DATA_DIR),
                            reset_ui_state=True,
                        )
                    except DataValidationError as exc:
                        st.sidebar.error(str(exc))
                    else:
                        st.session_state.sidebar_success = "Saved and switched drama."
                        rerun()
                if switch_col2.button("Discard and switch", width="stretch"):
                    try:
                        set_current_drama(
                            load_drama(selected_id, LOCAL_DATA_DIR),
                            reset_ui_state=True,
                        )
                    except DataValidationError as exc:
                        st.sidebar.error(str(exc))
                    else:
                        st.session_state.sidebar_success = "Switched drama."
                        rerun()
            else:
                try:
                    set_current_drama(load_drama(selected_id, LOCAL_DATA_DIR), reset_ui_state=True)
                except DataValidationError as exc:
                    st.sidebar.error(str(exc))
                else:
                    st.session_state.sidebar_success = "Switched drama."
                    rerun()

    save_disabled = not has_current_drama() or not can_save or not dirty
    with st.sidebar.container(horizontal=True, gap="small"):
        if st.button(
            "Create",
            icon=":material/add:",
            help="Create drama",
            key="create_drama_action",
            type="primary",
            width=ACTION_BUTTON_WIDTH,
        ):
            open_drama_dialog("create")
        if st.button(
            "Rename",
            icon=":material/edit:",
            help="Rename drama",
            key="rename_drama_action",
            disabled=not has_current_drama(),
            width=ACTION_BUTTON_WIDTH,
        ):
            open_drama_dialog("rename")
        if st.button(
            "Delete",
            icon=":material/delete:",
            help="Delete drama",
            key="delete_drama_action",
            disabled=not has_current_drama(),
            width=ACTION_BUTTON_WIDTH,
        ):
            open_drama_dialog("delete")
        if st.button(
            "Save",
            icon=":material/save:",
            help="Save drama",
            key="save_drama_action",
            disabled=save_disabled,
            width=ACTION_BUTTON_WIDTH,
        ):
            try:
                save_current_drama()
            except DataValidationError as exc:
                st.sidebar.error(str(exc))
            else:
                st.session_state.sidebar_success = "Drama saved."
                rerun()

    render_active_drama_dialog()


def rename_actor(project: ProjectData, old_name: str, new_name: str) -> None:
    renamed_actors: dict[str, list[list[bool]]] = {}
    for actor_name, matrix in project.actors.items():
        renamed_actors[new_name if actor_name == old_name else actor_name] = matrix

    renamed_scenes = [
        Scene(
            name=scene.name,
            actors=tuple(new_name if actor == old_name else actor for actor in scene.actors),
            duration_slots=scene.duration_slots,
            description=scene.description,
        )
        for scene in project.scenes
    ]
    project.actors = renamed_actors
    project.scenes = renamed_scenes


def open_actor_dialog(name: str) -> None:
    st.session_state.active_actor_dialog = name


def close_actor_dialog() -> None:
    st.session_state.pop("active_actor_dialog", None)


def render_active_actor_dialog() -> None:
    active_dialog = st.session_state.get("active_actor_dialog")
    if active_dialog == "add":
        add_actor_dialog()
    elif active_dialog == "edit":
        edit_actor_dialog()


@st.dialog("Add actor", width="large", on_dismiss=close_actor_dialog)
def add_actor_dialog() -> None:
    project = get_project()
    with st.form("add_actor_dialog_form"):
        st.markdown("##### Actor name")
        new_actor = st.text_input(
            "Actor name",
            key="add_actor_dialog_name",
            label_visibility="collapsed",
        )
        st.markdown("##### Availability")
        columns = [slot_label(slot_idx) for slot_idx in range(len(SLOT_START_HOURS))]
        source = pd.DataFrame(blank_matrix(), columns=columns)
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
            key=project_widget_key("add_actor_dialog_availability"),
        )
        submitted = st.form_submit_button(
            "Add actor",
            icon=":material/add:",
            key="add_actor_dialog_submit",
            type="primary",
            width="stretch",
        )
        if submitted:
            cleaned = new_actor.strip()
            if not cleaned:
                st.error("Actor name is required.")
            elif cleaned in project.actors:
                st.error("Actor names must be unique.")
            else:
                project.actors[cleaned] = [
                    [bool(edited.loc[row_index, column]) for column in columns]
                    for row_index in range(len(DAYS))
                ]
                set_project_dirty()
                close_actor_dialog()
                st.session_state.main_success = f"Added {cleaned}."
                rerun()


@st.dialog("Edit actor", width="large", on_dismiss=close_actor_dialog)
def edit_actor_dialog() -> None:
    project = get_project()
    actor_names = list(project.actors)
    if not actor_names:
        st.warning("Add an actor before editing.")
        return

    with st.container(border=True):
        actor_col, name_col = st.columns(2)
        with actor_col:
            st.markdown("##### Select actor")
            selected = st.selectbox(
                "Choose Actor",
                actor_names,
                label_visibility="collapsed",
                key=project_widget_key("actor_selector"),
            )
        with name_col:
            st.markdown("##### Actor name")
            updated_name = st.text_input(
                "Actor name",
                value=selected,
                label_visibility="collapsed",
                key=project_widget_key(f"rename_actor_{selected}"),
            )

        st.markdown("##### Availability")
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
        if st.button("Save actor", type="primary", width="stretch"):
            cleaned = updated_name.strip()
            if not cleaned:
                st.error("Actor name is required.")
            elif cleaned != selected and cleaned in project.actors:
                st.error("Actor names must be unique.")
            else:
                updated_matrix = [
                    [bool(edited.loc[row_index, column]) for column in columns]
                    for row_index in range(len(DAYS))
                ]
                if cleaned != selected:
                    rename_actor(project, selected, cleaned)
                project.actors[cleaned] = updated_matrix
                set_project_dirty()
                reset_project_ui_state()
                close_actor_dialog()
                st.session_state.main_success = "Actor saved."
                rerun()

        used_in = [scene.name for scene in project.scenes if selected in scene.actors]
        with st.container(key="delete_actor_action"):
            if used_in:
                st.button("Delete actor", disabled=True, width="stretch")
                st.warning("Remove this actor from scenes before deleting.")
            elif st.button("Delete actor", width="stretch"):
                del project.actors[selected]
                set_project_dirty()
                reset_project_ui_state()
                close_actor_dialog()
                st.session_state.main_success = "Actor deleted."
                rerun()


def actor_summary(project: ProjectData) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Actor": actor_name,
                "Time slots": "\n".join(
                    merged_slot_labels(
                        [
                            FeasibleSlot(
                                day_index=day_index,
                                start_slot=slot_index,
                                duration_slots=1,
                            )
                            for day_index, day_slots in enumerate(matrix)
                            for slot_index, available in enumerate(day_slots)
                            if available
                        ]
                    )
                )
                or "none",
            }
            for actor_name, matrix in project.actors.items()
        ]
    )


def availability_column_config(dataframe: pd.DataFrame) -> dict[str, object]:
    day_columns = [column for column in dataframe.columns if column != "Time slot"]
    return {
        "Time slot": st.column_config.TextColumn(
            "Time slot",
            width=AVAILABILITY_TIME_SLOT_WIDTH,
        ),
        **{
            column: st.column_config.TextColumn(
                column,
                width=AVAILABILITY_DAY_WIDTH,
            )
            for column in day_columns
        },
    }


def actor_availability_sheet(
    project: ProjectData,
    allowed_day_indexes: set[int],
) -> pd.DataFrame:
    day_columns = [
        (day_index, DAY_LABELS[day_index])
        for day_index in range(len(DAYS))
        if day_index in allowed_day_indexes
    ]
    rows: list[dict[str, str]] = []
    for slot_index in range(len(SLOT_START_HOURS)):
        row = {"Time slot": slot_label(slot_index)}
        for day_index, column in day_columns:
            row[column] = "\n".join(
                actor_name
                for actor_name, matrix in project.actors.items()
                if bool(matrix[day_index][slot_index])
            )
        rows.append(row)
    return pd.DataFrame(rows, columns=["Time slot", *[column for _, column in day_columns]])


def scene_availability_sheet(
    results: dict[str, list[FeasibleSlot]],
    allowed_day_indexes: set[int],
) -> pd.DataFrame:
    day_columns = [
        (day_index, DAY_LABELS[day_index])
        for day_index in range(len(DAYS))
        if day_index in allowed_day_indexes
    ]
    rows: list[dict[str, str]] = []
    for slot_index in range(len(SLOT_START_HOURS)):
        row = {"Time slot": slot_label(slot_index)}
        for day_index, column in day_columns:
            row[column] = "\n".join(
                scene_name
                for scene_name, slots in results.items()
                for slot in slots
                if slot.day_index == day_index and slot.start_slot == slot_index
            )
        rows.append(row)
    return pd.DataFrame(rows, columns=["Time slot", *[column for _, column in day_columns]])


def render_availability_dataframe(dataframe: pd.DataFrame) -> None:
    st.dataframe(
        dataframe,
        hide_index=True,
        column_config=availability_column_config(dataframe),
        row_height=AVAILABILITY_ROW_HEIGHT,
        width="stretch",
    )


def render_actors_tab() -> None:
    project = get_project()
    actor_names = list(project.actors)

    list_header_col, actor_action_col = st.columns(
        [0.68, 0.32],
        vertical_alignment="center",
    )
    with list_header_col:
        st.markdown("#### Actor-Time Slots List")
    with actor_action_col.container(
        horizontal=True,
        horizontal_alignment="right",
        gap="small",
    ):
        if st.button(
            "Edit",
            icon=":material/edit:",
            help="Edit actor",
            key="open_edit_actor_dialog",
            disabled=not actor_names,
            width=ACTION_BUTTON_WIDTH,
        ):
            open_actor_dialog("edit")
        if st.button(
            "Add",
            icon=":material/add:",
            help="Add Actor",
            key="open_add_actor_dialog",
            type="primary",
            width=ACTION_BUTTON_WIDTH,
        ):
            open_actor_dialog("add")
    render_active_actor_dialog()

    if actor_names:
        st.dataframe(actor_summary(project), hide_index=True, width="stretch")
    else:
        st.info("Add an actor to start building scene assignments.")

    if not actor_names:
        return


def scene_name_exists(
    project: ProjectData,
    scene_name: str,
    *,
    exclude_position: int | None = None,
) -> bool:
    return any(
        scene.name == scene_name and position != exclude_position
        for position, scene in enumerate(project.scenes)
    )


def scene_summary(project: ProjectData) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Scene": scene.name,
                "Description": scene.description,
                "Actors": ", ".join(scene.actors),
                "Duration": f"{scene.duration_slots} slot(s) / {scene.duration_slots * 2} hour(s)",
            }
            for scene in project.scenes
        ]
    )


def open_scene_dialog(name: str) -> None:
    st.session_state.active_scene_dialog = name


def close_scene_dialog() -> None:
    st.session_state.pop("active_scene_dialog", None)


def render_active_scene_dialog() -> None:
    active_dialog = st.session_state.get("active_scene_dialog")
    if active_dialog == "add":
        add_scene_dialog()
    elif active_dialog == "edit":
        edit_scene_dialog()


@st.dialog("Add scene", on_dismiss=close_scene_dialog)
def add_scene_dialog() -> None:
    project = get_project()
    actor_names = list(project.actors)
    if not actor_names:
        st.warning("Add an actor before creating scenes.")
        return

    with st.form("add_scene_dialog_form"):
        st.markdown("##### Scene")
        name = st.text_input(
            "Scene",
            key=project_widget_key("add_scene_dialog_name"),
            label_visibility="collapsed",
        )
        st.markdown("##### Description")
        description = st.text_input(
            "Description",
            placeholder="Optional",
            key=project_widget_key("add_scene_dialog_description"),
            label_visibility="collapsed",
        )
        st.markdown("##### Actors")
        actors = st.multiselect(
            "Actors",
            actor_names,
            key=project_widget_key("add_scene_dialog_actors"),
            label_visibility="collapsed",
        )
        st.markdown("#####  Duration slots")
        duration = st.number_input(
            "Duration slots",
            min_value=1,
            max_value=7,
            value=1,
            step=1,
            key=project_widget_key("add_scene_dialog_duration"),
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            "Add scene",
            icon=":material/add:",
            key="add_scene_dialog_submit",
            type="primary",
            width="stretch",
        )
        if submitted:
            cleaned_name = name.strip()
            cleaned_description = description.strip()
            if not cleaned_name:
                st.error("Scene is required.")
            elif scene_name_exists(project, cleaned_name):
                st.error("Scenes must be unique.")
            elif not actors:
                st.error("Choose at least one actor.")
            else:
                project.scenes.append(
                    Scene(
                        name=cleaned_name,
                        actors=tuple(actors),
                        duration_slots=int(duration),
                        description=cleaned_description,
                    )
                )
                set_project_dirty()
                close_scene_dialog()
                st.session_state.main_success = "Scene added."
                rerun()


@st.dialog("Edit scene", on_dismiss=close_scene_dialog)
def edit_scene_dialog() -> None:
    project = get_project()
    actor_names = list(project.actors)
    if not project.scenes:
        st.warning("Add a scene before editing.")
        return

    with st.container(border=True):
        scene_names = [scene.name for scene in project.scenes]
        st.markdown("##### Select scene")
        selected_name = st.selectbox(
            "Scene",
            scene_names,
            label_visibility="collapsed",
            key=project_widget_key("scene_selector"),
        )
        selected_index = scene_names.index(selected_name)
        selected_scene = project.scenes[selected_index]

        with st.form("edit_scene", border=False):
            st.markdown("##### Scene")
            edited_name = st.text_input(
                "Scene",
                value=selected_scene.name,
                key=project_widget_key(f"edit_scene_name_{selected_name}"),
                label_visibility="collapsed",
            )
            st.markdown("##### Description")
            edited_description = st.text_input(
                "Description",
                value=selected_scene.description,
                key=project_widget_key(f"edit_scene_description_{selected_name}"),
                label_visibility="collapsed",
            )
            st.markdown("##### Actors")
            edited_actors = st.multiselect(
                "Actors",
                actor_names,
                default=list(selected_scene.actors),
                key=project_widget_key(f"edit_scene_actors_{selected_name}"),
                label_visibility="collapsed",
            )
            st.markdown("##### Duration slots")
            edited_duration = st.number_input(
                "Duration slots",
                min_value=1,
                max_value=7,
                value=selected_scene.duration_slots,
                step=1,
                key=project_widget_key(f"edit_scene_duration_{selected_name}"),
                label_visibility="collapsed",
            )
            saved = st.form_submit_button("Save scene", type="primary", width="stretch")
            if saved:
                cleaned_name = edited_name.strip()
                cleaned_description = edited_description.strip()
                duplicate = scene_name_exists(
                    project,
                    cleaned_name,
                    exclude_position=selected_index,
                )
                if not cleaned_name:
                    st.error("Scene is required.")
                elif duplicate:
                    st.error("Scenes must be unique.")
                elif not edited_actors:
                    st.error("Choose at least one actor.")
                else:
                    project.scenes[selected_index] = Scene(
                        name=cleaned_name,
                        actors=tuple(edited_actors),
                        duration_slots=int(edited_duration),
                        description=cleaned_description,
                    )
                    set_project_dirty()
                    reset_project_ui_state()
                    close_scene_dialog()
                    st.session_state.main_success = "Scene updated."
                    rerun()

        with st.container(key="delete_scene_action"):
            if st.button(
                "Delete Selected Scene",
                icon=":material/delete:",
                width="stretch",
            ):
                del project.scenes[selected_index]
                set_project_dirty()
                reset_project_ui_state()
                close_scene_dialog()
                st.session_state.main_success = "Scene deleted."
                rerun()


def render_scenes_tab() -> None:
    project = get_project()

    list_header_col, scene_action_col = st.columns(
        [0.68, 0.32],
        vertical_alignment="center",
    )
    with list_header_col:
        st.markdown("#### Scene-Actor List")
    with scene_action_col.container(
        horizontal=True,
        horizontal_alignment="right",
        gap="small",
    ):
        if st.button(
            "Edit",
            icon=":material/edit:",
            help="Edit Scene",
            key="open_edit_scene_dialog",
            disabled=not project.scenes,
            width=ACTION_BUTTON_WIDTH,
        ):
            open_scene_dialog("edit")
        if st.button(
            "Add",
            icon=":material/add:",
            help="Add Scene",
            key="open_add_scene_dialog",
            type="primary",
            width=ACTION_BUTTON_WIDTH,
        ):
            open_scene_dialog("add")
    render_active_scene_dialog()

    if project.scenes:
        st.dataframe(scene_summary(project), hide_index=True, width="stretch")
    else:
        st.info("Add a scene to start matching rehearsal slots.")

    if not project.scenes:
        return


def render_results_tab() -> None:
    project = get_project()
    st.markdown("#### Status & Filters")
    if "results_days_filter" not in st.session_state:
        st.session_state.results_days_filter = list(DAYS)
    chosen_days = [
        day
        for day in st.session_state.get("results_days_filter", list(DAYS))
        if day in DAYS
    ]
    allowed_day_indexes = {DAYS.index(day) for day in chosen_days}

    try:
        results = compute_project_results(project)
    except DataValidationError as exc:
        st.error(str(exc))
        return

    filtered = filter_results_by_day_indexes(results, allowed_day_indexes)
    rows = result_rows(filtered, project.scenes)
    total_slots = sum(len(slots) for slots in filtered.values())

    metric_col1, metric_col2 = st.columns(2)
    metric_col1.metric("Scenes", len(project.scenes))
    metric_col2.metric("Feasible slots", total_slots)

    current_days = set(chosen_days)
    day_cols = st.columns(len(DAYS))
    for day, day_col in zip(DAYS, day_cols):
        active = day in current_days
        with day_col:
            if st.button(
                day,
                icon=":material/calendar_today:",
                type="primary" if active else "secondary",
                key=f"results_day_toggle_{day}",
                width="stretch",
            ):
                if active:
                    current_days.remove(day)
                else:
                    current_days.add(day)
                st.session_state.results_days_filter = [
                    candidate for candidate in DAYS if candidate in current_days
                ]
                rerun()

    if not allowed_day_indexes:
        st.warning("No days are selected.")

    st.markdown("#### Feasible Slots")
    st.dataframe(
        pd.DataFrame(rows, columns=["Scene", "Description", "Slots"]),
        hide_index=True,
        width="stretch",
    )

    st.markdown("#### Scene Availability Sheet")
    if project.scenes:
        render_availability_dataframe(scene_availability_sheet(filtered, allowed_day_indexes))
    else:
        st.info("Add a scene to start matching rehearsal slots.")

    st.markdown("#### Actor Availability Sheet")
    if project.actors:
        render_availability_dataframe(actor_availability_sheet(project, allowed_day_indexes))
    else:
        st.info("Add an actor to start building availability.")


def render_advanced_tab() -> None:
    project = get_project()

    st.markdown("#### Import")
    drama_file = st.file_uploader("Drama JSON backup", type="json")
    if st.button("Import drama backup", width="stretch"):
        if drama_file is None:
            st.error("Upload a drama JSON backup.")
        else:
            try:
                drama = parse_uploaded_drama_file(drama_file)
            except (UnicodeDecodeError, json.JSONDecodeError, DataValidationError) as exc:
                st.error(f"Import failed: {exc}")
            else:
                set_project(drama.project, reset_ui_state=True)
                set_project_dirty()
                st.session_state.main_success = "Imported drama backup."
                rerun()

    upload_col1, upload_col2 = st.columns(2)
    actors_file = upload_col1.file_uploader("Legacy actors.json", type="json")
    scenes_file = upload_col2.file_uploader("Legacy scenes.json", type="json")

    if st.button("Import legacy actors/scenes JSON", width="stretch"):
        if actors_file is None or scenes_file is None:
            st.error("Upload both actors and scenes JSON files.")
        else:
            try:
                set_project(
                    parse_uploaded_project_files(actors_file, scenes_file),
                    reset_ui_state=True,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, DataValidationError) as exc:
                st.error(f"Import failed: {exc}")
            else:
                set_project_dirty()
                st.session_state.main_success = "Imported legacy project JSON."
                rerun()

    st.markdown("#### Backup")
    backup_col1, backup_col2, backup_col3 = st.columns(3)
    backup_col1.download_button(
        "Download drama JSON",
        data=dump_drama_json(current_drama()),
        file_name=f"{st.session_state.current_drama_id}.json",
        mime="application/json",
        width="stretch",
    )
    backup_col2.download_button(
        "Download actors.json",
        data=dump_actors_json(project.actors),
        file_name="actors.json",
        mime="application/json",
        width="stretch",
    )
    backup_col3.download_button(
        "Download scenes.json",
        data=dump_scenes_json(project.scenes),
        file_name="scenes.json",
        mime="application/json",
        width="stretch",
    )

    with st.expander("View current JSON"):
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
    ensure_active_section_state()
    render_sidebar()

    load_error = st.session_state.get("load_error")
    if load_error:
        st.error(load_error)
    main_success = pop_session_value("main_success")
    if main_success:
        st.success(str(main_success))

    if not has_current_drama():
        st.info("Create a drama in the sidebar to start managing actors and scenes.")
        return

    st.caption(f"Drama: {st.session_state.current_drama_name}")

    active_section = st.segmented_control(
        "Section",
        APP_SECTIONS,
        key=ACTIVE_SECTION_CONTROL_KEY,
        on_change=sync_active_section_from_control,
        label_visibility="collapsed",
        width="stretch",
    )
    active_section = set_active_section(
        active_section,
        fallback=st.session_state.get(ACTIVE_SECTION_KEY),
    )

    if active_section == "Actors":
        render_actors_tab()
    elif active_section == "Scenes":
        render_scenes_tab()
    elif active_section == "Results":
        render_results_tab()
    elif active_section == "Advanced":
        render_advanced_tab()


if __name__ == "__main__":
    main()
