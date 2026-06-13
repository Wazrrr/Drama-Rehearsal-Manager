# Rehearsal Management

Local-only rehearsal slot matcher using actor weekly availability matrices. The project now supports both:

- a tested Python CLI for scripted runs
- a local browser app for visual editing and matching

## Time Grid

- 7 days: `Mon-Sun`
- 7 slots/day: `10-12`, `12-14`, `14-16`, `16-18`, `18-20`, `20-22`, `22-24`
- Availability matrix shape: `7x7`
- Cell values accepted: `0/1`, `true/false`, `yes/no`

## Input Format

`actors.json` (object mapping actor name -> 7x7 matrix):

```json
{
  "Alice": [[1,1,0,1,0,0,0], [1,1,1,0,0,0,0], [0,0,0,0,0,0,0], [1,1,1,1,0,0,0], [0,0,0,0,1,1,0], [1,0,1,0,1,0,1], [0,0,0,0,0,0,0]],
  "Bob":   [[1,0,0,1,1,0,0], [1,1,1,1,0,0,0], [0,0,0,1,1,0,0], [1,1,0,1,0,0,0], [0,1,0,0,1,1,0], [1,0,1,0,0,0,1], [1,1,1,1,1,1,1]]
}
```

`scenes.json` (array of scenes):

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

Use `python3` on macOS/Linux and `py -3` on Windows if `python` is not available on your PATH.

### CLI

```bash
python3 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --format human
python3 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --format json
python3 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --no-weekend
python3 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --choose Mon,Fri
python3 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --choose Mon, Fri
```

Windows:

```powershell
py -3 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --format human
```

### Web App

Create and activate a virtual environment, then install dependencies.

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3 -m pip install -r requirements.txt
py -3 -m streamlit run app.py
```

The app opens in a browser and lets you:

- add, rename, and delete actors
- edit actor availability in a 7 day x 7 slot grid
- add and edit scenes with actor pickers and duration slots
- run the matcher with day filters
- download actors, scenes, and result reports as JSON/text
- save the current project to `data/actors.json` and `data/scenes.json`

On startup, the app loads `data/actors.json` and `data/scenes.json` if both exist. Otherwise it loads the sample files.

## Day Filtering

- `--no-weekend`: remove `Sat` and `Sun` from reported slots.
- `--choose DAY...`: only show selected days. Accepts:
  - comma-separated: `--choose Mon,Fri`
  - space-separated: `--choose Mon Fri`
  - mixed: `--choose Mon, Fri`
- You can combine both flags; filters are intersected (example: `--no-weekend --choose Mon,Sat` results in `Mon` only).

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Windows:

```powershell
py -3 -m unittest discover -s tests -v
```

## Troubleshooting

- `python: command not found`: use `python3` on macOS/Linux or `py -3` on Windows.
- `No module named streamlit`: activate the virtual environment and run `python3 -m pip install -r requirements.txt`.
- Invalid project data: the CLI and web app both use the same validation rules, so fix the actor matrix shape, scene names, actor references, or duration values reported in the error.
