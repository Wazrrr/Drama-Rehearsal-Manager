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
    export_results_json,
    export_results_text,
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
from models import Scene
from time_grid import DAYS, SLOT_START_HOURS, slot_label

LOCAL_DATA_DIR = DEFAULT_LOCAL_DATA_DIR
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


def render_sidebar() -> None:
    project = get_project()

    st.sidebar.header("Dramas")
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

    if has_current_drama():
        st.sidebar.caption(f"Current drama: `{st.session_state.current_drama_name}`")
        if dirty:
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
    if st.sidebar.button("Save drama", disabled=save_disabled, width="stretch"):
        try:
            save_current_drama()
        except DataValidationError as exc:
            st.sidebar.error(str(exc))
        else:
            st.session_state.sidebar_success = "Drama saved."
            rerun()

    with st.sidebar.expander("Create drama", expanded=not has_current_drama()):
        with st.form("create_drama"):
            new_drama_name = st.text_input("Drama name")
            submitted = st.form_submit_button("Create drama", width="stretch")
            if submitted:
                if dirty:
                    st.error("Save or discard the current drama before creating another.")
                else:
                    try:
                        drama = create_drama(new_drama_name, LOCAL_DATA_DIR)
                    except DataValidationError as exc:
                        st.error(str(exc))
                    else:
                        set_current_drama(drama, reset_ui_state=True)
                        st.session_state.sidebar_success = "Drama created."
                        rerun()

    if not has_current_drama():
        return

    with st.sidebar.expander("Rename drama"):
        with st.form("rename_drama"):
            renamed_drama = st.text_input(
                "Drama name",
                value=str(st.session_state.current_drama_name),
            )
            submitted = st.form_submit_button(
                "Rename drama",
                disabled=dirty,
                width="stretch",
            )
            if submitted:
                try:
                    drama = rename_drama(str(current_id), renamed_drama, LOCAL_DATA_DIR)
                except DataValidationError as exc:
                    st.error(str(exc))
                else:
                    set_current_drama(drama, reset_ui_state=False)
                    st.session_state.sidebar_success = "Drama renamed."
                    rerun()
        if dirty:
            st.caption("Save or discard changes before renaming.")

    with st.sidebar.expander("Delete drama"):
        confirm_delete = st.checkbox(
            "Delete this drama permanently",
            key="confirm_delete_drama",
            disabled=dirty,
        )
        if dirty:
            st.caption("Save or discard changes before deleting.")
        if st.button(
            "Delete drama",
            disabled=dirty or not confirm_delete,
            width="stretch",
        ):
            delete_drama(str(current_id), LOCAL_DATA_DIR)
            next_drama = choose_initial_drama(LOCAL_DATA_DIR)
            if next_drama is None:
                clear_current_drama()
                st.session_state.sidebar_success = "Drama deleted."
            else:
                set_current_drama(next_drama, reset_ui_state=True)
                st.session_state.sidebar_success = "Drama deleted."
            rerun()


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
                set_project_dirty()
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
                set_project_dirty()
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
            set_project_dirty()
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
        set_project_dirty()
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
                set_project_dirty()
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
                set_project_dirty()
                st.success("Scene updated.")
                rerun()

    if st.button("Delete selected scene", width="stretch"):
        del project.scenes[selected_index]
        set_project_dirty()
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


def render_advanced_tab() -> None:
    project = get_project()
    st.subheader("Advanced")

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

    with st.expander("Import backup"):
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

    actors_tab, scenes_tab, results_tab, advanced_tab = st.tabs(
        ["Actors", "Scenes", "Results", "Advanced"]
    )
    with actors_tab:
        render_actors_tab()
    with scenes_tab:
        render_scenes_tab()
    with results_tab:
        render_results_tab()
    with advanced_tab:
        render_advanced_tab()


if __name__ == "__main__":
    main()
