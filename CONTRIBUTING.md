# Contributing

Bug reports and pull requests are welcome. This is a small tool with a narrow
purpose, so the useful contributions are usually one of:

- a matchup or team result that disagrees with pvpoke.com, with the exact team,
  cup and settings;
- a cup or format the tool handles incorrectly;
- a bug in the engine bridge.

## Before opening an issue

Run these and include the output - they answer most questions:

```bash
pvp-team-builder validate -l great -l ultra --n 40
pytest -q
```

If a specific team looks wrong, `pvp-team-builder rate` prints the full
per-threat scorecard with both perspectives, which is usually enough to locate
the disagreement.

## Pull requests

1. Open an issue first for anything larger than a fix; the design is
   deliberately minimal and that is worth preserving.
2. Keep the dependency list empty. Python standard library plus Node, nothing
   else.
3. Add a test for behaviour changes. Anything touching grading, ranking order,
   role assignment or evolution expansion needs one.
4. `pytest` and `pvp-team-builder validate` must pass. If you change
   `harness.js` or `engine.py`, `validate` is the real test.
5. Do not commit anything from `data/` or `engine/`. Those are downloaded, and
   they are PvPoke's.

## Scope

In scope: team search for 3v3 Great/Ultra/Master and cups, scoring fidelity with
PvPoke, data and cache handling.

Out of scope, by design: ABB/BAB lineup planning, 3v3 battle simulation, IV
optimisation, account or collection management, anything requiring login.
