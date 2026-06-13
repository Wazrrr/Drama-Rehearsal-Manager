"""Streamlit web app for local rehearsal scene matching."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from app_services import (
    DEFAULT_ACTORS_PATH,
    DEFAULT_SCENES_PATH,
    ProjectData,
    actors_to_jsonable,
    compute_project_results,
    dump_actors_json,
    dump_scenes_json,
    export_results_json,
    export_results_text,
    load_default_project,
    parse_project_payloads,
    result_rows,
    save_project,
    scenes_to_jsonable,
    validate_project,
)
from day_filters import filter_results_by_day_indexes
from loader import DataValidationError
from models import Scene
from time_grid import DAYS, SLOT_START_HOURS, slot_label


def blank_matrix() -> list[list[bool]]:
    return [[False for _ in SLOT_START_HOURS] for _ in DAYS]


def set_project(project: ProjectData) -> None:
    st.session_state.project = project


def get_project() -> ProjectData:
    return st.session_state.project


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


def render_sidebar() -> None:
    project = get_project()
    loaded_actors, loaded_scenes = st.session_state.get("loaded_paths", ("none", "none"))

    st.sidebar.header("Project")
    st.sidebar.caption(f"Loaded actors: `{loaded_actors}`")
    st.sidebar.caption(f"Loaded scenes: `{loaded_scenes}`")

    if st.sidebar.button("Reload from files", width="stretch"):
        loaded = load_default_project()
        set_project(loaded.data)
        st.session_state.loaded_paths = (str(loaded.actors_path), str(loaded.scenes_path))
        st.sidebar.success("Reloaded project files.")
        rerun()

    try:
        validate_project(project)
        can_save = True
    except DataValidationError as exc:
        can_save = False
        st.sidebar.error(str(exc))

    if st.sidebar.button("Save to data files", disabled=not can_save, width="stretch"):
        save_project(project, DEFAULT_ACTORS_PATH, DEFAULT_SCENES_PATH)
        st.session_state.loaded_paths = (str(DEFAULT_ACTORS_PATH), str(DEFAULT_SCENES_PATH))
        st.sidebar.success("Saved data/actors.json and data/scenes.json.")

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
        new_actor = st.text_input("New actor name")
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

    selected = st.selectbox("Actor", actor_names, key="actor_selector")
    used_in = [scene.name for scene in project.scenes if selected in scene.actors]

    rename_col, delete_col = st.columns([2, 1])
    with rename_col.form("rename_actor"):
        updated_name = st.text_input("Actor name", value=selected, key=f"rename_actor_{selected}")
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
        key=f"availability_editor_{selected}",
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
        name = st.text_input("Scene name")
        actors = st.multiselect("Actors", actor_names, key="add_scene_actors")
        duration = st.number_input("Duration slots", min_value=1, max_value=7, value=1, step=1)
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
    selected_name = st.selectbox("Scene", scene_names, key="scene_selector")
    selected_index = scene_names.index(selected_name)
    selected_scene = project.scenes[selected_index]

    with st.form("edit_scene"):
        edited_name = st.text_input(
            "Scene name",
            value=selected_scene.name,
            key=f"edit_scene_name_{selected_name}",
        )
        edited_actors = st.multiselect(
            "Actors",
            actor_names,
            default=list(selected_scene.actors),
            key=f"edit_scene_actors_{selected_name}",
        )
        edited_duration = st.number_input(
            "Duration slots",
            min_value=1,
            max_value=7,
            value=selected_scene.duration_slots,
            step=1,
            key=f"edit_scene_duration_{selected_name}",
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
                set_project(parse_project_payloads(actors_payload, scenes_payload))
            except (UnicodeDecodeError, json.JSONDecodeError, DataValidationError) as exc:
                st.error(f"Import failed: {exc}")
            else:
                st.success("Imported project JSON.")
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
