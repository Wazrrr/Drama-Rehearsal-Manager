# Rehearsal Management

Local-only rehearsal slot matcher using actor weekly availability matrices. The project now supports both:

- a tested Python CLI for scripted runs
- a local browser app for visual editing and matching

Target Python version: `3.14`.

## Time Grid

- 7 days: `Mon-Sun`
- 7 slots/day: `10-12`, `12-14`, `14-16`, `16-18`, `18-20`, `20-22`, `22-24`
- Availability matrix shape: `7x7`
- Cell values accepted: `0/1`, `true/false`, `yes/no`

## Data Format

The web app stores each local drama as one JSON file under `.local_data/dramas/`.
Users normally create and select dramas in the app instead of managing files directly.

`drama.json`:

```json
{
  "schema_version": 1,
  "id": "my-drama",
  "name": "My Drama",
  "created_at": "2026-06-14T00:00:00Z",
  "updated_at": "2026-06-14T00:00:00Z",
  "actors": {
    "Alice": [[1,1,0,1,0,0,0], [1,1,1,0,0,0,0], [0,0,0,0,0,0,0], [1,1,1,1,0,0,0], [0,0,0,0,1,1,0], [1,0,1,0,1,0,1], [0,0,0,0,0,0,0]]
  },
  "scenes": [
    { "name": "Scene_1", "actors": ["Alice"], "duration_slots": 1 }
  ]
}
```

The CLI still supports legacy separate JSON files.

`actors.json`:

```json
{
  "Alice": [[1,1,0,1,0,0,0], [1,1,1,0,0,0,0], [0,0,0,0,0,0,0], [1,1,1,1,0,0,0], [0,0,0,0,1,1,0], [1,0,1,0,1,0,1], [0,0,0,0,0,0,0]],
  "Bob":   [[1,0,0,1,1,0,0], [1,1,1,1,0,0,0], [0,0,0,1,1,0,0], [1,1,0,1,0,0,0], [0,1,0,0,1,1,0], [1,0,1,0,0,0,1], [1,1,1,1,1,1,1]]
}
```

`scenes.json`:

```json
[
  { "name": "Scene_1", "actors": ["Alice", "Bob"], "duration_slots": 1 },
  { "name": "Scene_2", "actors": ["Alice"], "duration_slots": 2 }
]
```

Reminder: `duration_slots` is the number of 2-hour slots.
- `duration_slots: 1` means `2 hours`
- `duration_slots: 2` means `4 hours`

## Run

Use Python `3.14` for local development and deployment. On macOS/Linux, this is usually `python3.14`. On Windows, use `py -3.14`.

### CLI

```bash
python3.14 main.py --drama .local_data/dramas/my-drama.json --format human
python3.14 main.py --drama .local_data/dramas/my-drama.json --format json
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --format human
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --format json
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --no-weekend
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --choose Mon,Fri
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --choose Mon, Fri
```

Windows:

```powershell
py -3.14 main.py --drama .local_data/dramas/my-drama.json --format human
```

### Web App

Create and activate a virtual environment, then install dependencies.

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

The app opens in a browser and lets you:

- create, select, rename, delete, and save dramas
- add, rename, and delete actors
- edit actor availability in a 7 day x 7 slot grid
- add and edit scenes with actor pickers and duration slots
- run the matcher with day filters
- download drama backups, legacy actors/scenes JSON, and result reports
- import drama backups or legacy actors/scenes JSON from the Advanced tab

On first startup, create a drama in the sidebar. The app stores drama files under `.local_data/`, which is ignored by Git. Returning launches reopen the last selected drama when possible.

Edits are manual-save: after changing actors, availability, scenes, or importing backup data, click `Save drama` in the sidebar.

## Day Filtering

- `--no-weekend`: remove `Sat` and `Sun` from reported slots.
- `--choose DAY...`: only show selected days. Accepts:
  - comma-separated: `--choose Mon,Fri`
  - space-separated: `--choose Mon Fri`
  - mixed: `--choose Mon, Fri`
- You can combine both flags; filters are intersected (example: `--no-weekend --choose Mon,Sat` results in `Mon` only).

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
- Invalid project data: the CLI and web app both use the same validation rules, so fix the actor matrix shape, scene names, actor references, or duration values reported in the error.
