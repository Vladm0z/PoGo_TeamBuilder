# Contributing
Bug reports and pull requests are welcome. This is a small tool with a narrow purpose, so useful contributions are usually one of three things: a matchup or team result that disagrees with pvpoke.com, with the exact team, cup and settings; a cup or format handled incorrectly; or a bug in the engine bridge.

## Before opening an issue
Run these and include the output, which answers most questions.

```bash
pvp-team-builder validate -l great -l ultra --n 40
pytest -q
```

If a specific team looks wrong, `pvp-team-builder rate` prints the full per-threat scorecard from both sides, which is usually enough to locate the disagreement.

## Pull requests
1. Open an issue first for anything larger than a fix. The design is deliberately minimal and that is worth keeping.
2. Keep the dependency list empty: the Python standard library plus Node, nothing else.
3. Add a test for behaviour changes. Anything touching grading, ranking order, role assignment or evolution expansion needs one.
4. `pytest` and `pvp-team-builder validate` must pass. If you change `harness.js` or `engine.py`, `validate` is the real test.
5. Do not commit anything from the cache directory. That data is downloaded and it is PvPoke's.

## Scope
In scope: team search for 3v3 Great, Ultra and Master League and cups, scoring fidelity with PvPoke, data and cache handling.

Out of scope by design: ABB and BAB lineup planning, 3v3 battle simulation, IV optimisation, account or collection management, and anything that needs a login.
