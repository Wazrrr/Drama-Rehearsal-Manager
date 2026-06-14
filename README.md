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

Use Python `3.14` for local development and deployment. On macOS/Linux, this is usually `python3.14`. On Windows, use `py -3.14`.

### CLI

```bash
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --format human
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --format json
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --no-weekend
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --choose Mon,Fri
python3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --choose Mon, Fri
```

Windows:

```powershell
py -3.14 main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --format human
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

- add, rename, and delete actors
- edit actor availability in a 7 day x 7 slot grid
- add and edit scenes with actor pickers and duration slots
- run the matcher with day filters
- choose Local JSON or Google Sheets storage
- download actors, scenes, and result reports as JSON/text
- save the current project to `private_data/actors.json` and `private_data/scenes.json`

On startup, the app loads `data/actors.sample.json` and `data/scenes.sample.json`. Use the `Local JSON` sidebar controls to load from or save to `private_data/actors.json` and `private_data/scenes.json`.

## Google Sheets Storage

The web app can read from and save to Google Sheets when you choose `Google Sheets` in the sidebar.

Credential options:

- Upload or paste the Google service account JSON in the website under `Google credentials`.
- Check `Save locally for browser refresh` if you want `Command+R` / `Ctrl+R` to keep working without pasting credentials again.
- Or configure Streamlit secrets manually.

Local website-entered credentials are saved to:

```text
.streamlit/google_service_account.json
.streamlit/google_sheets.json
```

The `.streamlit/` directory is ignored by Git. Do not commit credentials.

Expected workbook shape:

- worksheet `actors`
  - column `actor_name`
  - one availability column for each day/slot, for example `Mon 10:00-12:00`
  - cell values can be `TRUE/FALSE`, `1/0`, or blank (`blank` means unavailable)
- worksheet `scenes`
  - columns: `name`, `actors`, `duration_slots`
  - `actors` accepts comma-separated actor names like `Alice, Bob`

If the worksheets do not exist yet, choose `Google Sheets` and click `Save to Google Sheets` once. The app will create/update the `actors` and `scenes` worksheets.

### Google Setup

1. In Google Cloud Console, enable the Google Sheets API and Google Drive API.
2. Create a service account and download its JSON key.
3. Open the target spreadsheet in Google Sheets.
4. Share the spreadsheet with the service account `client_email` as an editor.
5. Add the service account JSON in the website, or store it in Streamlit secrets. Do not commit credentials to Git.

Local secrets file:

```text
.streamlit/secrets.toml
```

Example:

```toml
[google_sheets]
spreadsheet_id = "your-spreadsheet-id"

[google_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = """-----BEGIN PRIVATE KEY-----
your-private-key
-----END PRIVATE KEY-----
"""
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "your-client-cert-url"
universe_domain = "googleapis.com"
```

For Streamlit Community Cloud, add the same TOML in the app's `Secrets` settings. Do not commit `.streamlit/secrets.toml`.

Streamlit's built-in `st.secrets` requires a server restart if `.streamlit/secrets.toml` is created while the server is already running. The website upload/paste option avoids that locally because it stores credentials in JSON files that the app reads on each refresh.

## Streamlit Cloud Python Version

When deploying on Streamlit Community Cloud, choose Python `3.14` in `Advanced settings` during deployment.

Streamlit Cloud uses `requirements.txt` for Python dependencies. Python itself is selected in the deployment UI. If you need to change Python after deployment, delete and redeploy the app with the desired Python version.

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
- `No module named gspread`: reinstall dependencies with `python -m pip install -r requirements.txt`.
- Google Sheets `SpreadsheetNotFound`: share the spreadsheet with the service account `client_email`.
- Invalid project data: the CLI and web app both use the same validation rules, so fix the actor matrix shape, scene names, actor references, or duration values reported in the error.
