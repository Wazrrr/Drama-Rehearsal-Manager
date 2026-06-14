# Rehearsal Manager

Local-only rehearsal scheduling tool for matching scene requirements against actor availability.

The main interface is a Streamlit web app for creating dramas, editing actors and scenes, and viewing feasible rehearsal slots. A Python CLI is also available for scripted runs and JSON output.

Target Python version: `3.14`.

## Web App

### Install and Run

macOS/Linux:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Windows PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Streamlit opens the app in your browser. The app is local-only: drama files are written under `.local_data/`, which is ignored by Git.

### App Workflow

Start in the sidebar:

- `Create` makes a new local drama.
- `Rename` changes the displayed drama name while preserving the drama id and project data.
- `Delete` permanently removes the current local drama after confirmation.
- `Save` writes current edits to `.local_data/dramas/<drama-id>.json`.

Edits are manual-save. After changing actors, availability, scenes, or imported data, click `Save` in the sidebar. `Cmd+S` on macOS and `Ctrl+S` on Windows/Linux also trigger the app save button when it is enabled.

The app remembers the last selected drama in `.local_data/app_state.json` and reopens it on the next launch when possible.

### Actors

The `Actors` section manages actor weekly availability.

- Add actors with a 7 day x 7 time-slot checkbox grid.
- Edit an actor's name and availability.
- Delete actors only after removing them from every scene.
- View each actor's available slots as merged time ranges, such as `Mon 10:00-14:00`.

### Scenes

The `Scenes` section manages scene requirements.

- Add scenes with a name, optional description, actor list, and duration.
- Edit or delete existing scenes.
- Scene names must be unique.
- Each scene must include at least one actor.
- `duration_slots` is measured in 2-hour blocks. A value of `2` means the matcher needs a contiguous 4-hour window on the same day.

### Results

The `Results` section runs the matcher against the current in-memory drama.

- Day toggle buttons filter the visible result set.
- The status metrics show scene count and total feasible slots after filtering.
- The `Feasible Slots` table shows scene names, descriptions, and merged matching time ranges.
- The `Scene Availability Sheet` shows which scenes can rehearse in each visible day/time cell.
- The `Actor Availability Sheet` shows which actors are available in each visible day/time cell.

### Advanced

The `Advanced` section handles import, backup, and JSON inspection.

- Import a drama JSON backup. This loads the backup's actors and scenes into the current drama as unsaved edits.
- Import legacy `actors.json` and `scenes.json` together.
- Download the current drama JSON backup.
- Download legacy `actors.json` and `scenes.json`.
- View the current legacy JSON payloads in the browser.

## Scheduling Model

The project uses a fixed weekly grid:

- Days: `Mon`, `Tue`, `Wed`, `Thu`, `Fri`, `Sat`, `Sun`
- Slots: `10:00-12:00`, `12:00-14:00`, `14:00-16:00`, `16:00-18:00`, `18:00-20:00`, `20:00-22:00`, `22:00-24:00`
- Availability matrix shape: `7x7`
- Accepted availability values in JSON: `0/1`, `true/false`, `yes/no`, `y/n`

For each scene, the matcher intersects all assigned actors' availability matrices, then finds contiguous slot windows matching that scene's `duration_slots`.

## Data Formats

### Drama JSON

The web app stores one JSON file per drama under `.local_data/dramas/`.

```json
{
  "schema_version": 1,
  "id": "my-drama",
  "name": "My Drama",
  "created_at": "2026-06-14T00:00:00Z",
  "updated_at": "2026-06-14T00:00:00Z",
  "actors": {
    "Alice": [
      [1, 1, 0, 1, 0, 0, 0],
      [1, 1, 1, 0, 0, 0, 0],
      [0, 0, 0, 0, 0, 0, 0],
      [1, 1, 1, 1, 0, 0, 0],
      [0, 0, 0, 0, 1, 1, 0],
      [1, 0, 1, 0, 1, 0, 1],
      [0, 0, 0, 0, 0, 0, 0]
    ]
  },
  "scenes": [
    {
      "name": "Scene 1",
      "description": "Optional scene note",
      "actors": ["Alice"],
      "duration_slots": 1
    }
  ]
}
```

`schema_version` must be `1`. Drama ids use lowercase letters, numbers, and hyphens. The app generates ids from drama names and keeps the same id when a drama is renamed.

### Legacy JSON

The CLI and the web app's Advanced import/export also support separate legacy files.

`actors.json`:

```json
{
  "Alice": [
    [1, 1, 0, 1, 0, 0, 0],
    [1, 1, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [1, 1, 1, 1, 0, 0, 0],
    [0, 0, 0, 0, 1, 1, 0],
    [1, 0, 1, 0, 1, 0, 1],
    [0, 0, 0, 0, 0, 0, 0]
  ],
  "Bob": [
    [1, 0, 0, 1, 1, 0, 0],
    [1, 1, 1, 1, 0, 0, 0],
    [0, 0, 0, 1, 1, 0, 0],
    [1, 1, 0, 1, 0, 0, 0],
    [0, 1, 0, 0, 1, 1, 0],
    [1, 0, 1, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1]
  ]
}
```

`scenes.json`:

```json
[
  {
    "name": "Scene 1",
    "description": "Optional scene note",
    "actors": ["Alice", "Bob"],
    "duration_slots": 1
  },
  {
    "name": "Scene 2",
    "actors": ["Alice"],
    "duration_slots": 2
  }
]
```

`description` is optional. When empty, exports omit it.

## CLI

The CLI is useful for automation, quick checks, and machine-readable output. It accepts either a drama JSON file or a pair of legacy actors/scenes files.

Drama JSON input:

```bash
python3.14 main.py --drama .local_data/dramas/my-drama.json --format human
python3.14 main.py --drama .local_data/dramas/my-drama.json --format json
```

Legacy input:

```bash
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --format human
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --format json
```

Windows:

```powershell
py -3.14 main.py --drama .local_data/dramas/my-drama.json --format human
```

Do not combine `--drama` with `--actors` or `--scenes`; the CLI treats that as an input error.

### CLI Day Filtering

`--no-weekend` removes Saturday and Sunday:

```bash
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --no-weekend
```

`--choose` limits output to selected days. It accepts short or full day names, comma-separated values, space-separated values, or a mix:

```bash
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --choose Mon,Fri
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --choose Monday Friday
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --choose Mon, Fri
```

You can combine both filters; the result is the intersection. For example, `--no-weekend --choose Mon,Sat` shows only Monday.

## Validation Rules

The web app and CLI share the same validation behavior:

- Actor names must be non-empty.
- Each actor matrix must have 7 rows and 7 columns.
- Scene names must be non-empty and unique.
- Each scene actor must exist in the actor list.
- Each scene must include at least one actor.
- `duration_slots` must be a positive integer no greater than `7`.

Invalid CLI input exits with status code `2` and prints an `Input error:` message to stderr.

## Tests

```bash
python3.14 -m unittest discover -s tests -v
```

Windows:

```powershell
py -3.14 -m unittest discover -s tests -v
```

## Troubleshooting

- `python3.14: command not found`: install Python 3.14 from python.org, Homebrew, or your Windows Python launcher.
- `No module named streamlit`: activate the virtual environment and run `python -m pip install -r requirements.txt`.
- No drama appears on startup: create one in the sidebar. Existing dramas must live under `.local_data/dramas/`.
- Save is disabled: create or select a drama first, make a valid edit, and resolve any validation error shown in the sidebar.
- Import fails: check that uploaded JSON is valid UTF-8 and follows the drama or legacy schema above.
