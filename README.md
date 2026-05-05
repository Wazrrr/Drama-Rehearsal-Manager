# Rehearsal Management (Local CLI)

Local-only rehearsal slot matcher using actor weekly availability matrices.

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

```bash
python main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --format human
python main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --format json
python main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --no-weekend
python main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --choose Mon,Fri
python main.py --actors data/actors.sample.json --scenes data/scenes.sample.json --choose Mon, Fri
```

## Day Filtering

- `--no-weekend`: remove `Sat` and `Sun` from reported slots.
- `--choose DAY...`: only show selected days. Accepts:
  - comma-separated: `--choose Mon,Fri`
  - space-separated: `--choose Mon Fri`
  - mixed: `--choose Mon, Fri`
- You can combine both flags; filters are intersected (example: `--no-weekend --choose Mon,Sat` results in `Mon` only).

## Tests

```bash
python -m unittest discover -s tests -v
```
