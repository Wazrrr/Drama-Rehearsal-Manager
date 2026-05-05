# Rehearsal Management (Local CLI)

Local-only rehearsal slot matcher using actor weekly availability matrices.

## Time Grid

- 7 days: Mon-Sun
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

`sessions.json` (array of sessions):

```json
[
  { "name": "Scene_1", "actors": ["Alice", "Bob"], "duration_slots": 1 },
  { "name": "Scene_2", "actors": ["Alice"], "duration_slots": 2 }
]
```

## Run

```bash
python main.py --actors examples/actors.sample.json --sessions examples/sessions.sample.json --format human
python main.py --actors examples/actors.sample.json --sessions examples/sessions.sample.json --format json
```

## Tests

```bash
python -m unittest discover -s tests -v
```
