# Development
Build, test and extend the tool.

## Setup

```bash
git clone https://github.com/USER/pvp-team-builder
cd pvp-team-builder
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

Node is needed only for the exact engine and for `validate`. Without it the test suite skips the engine test and the CLI falls back to estimates.

## Layout
- `pvp.py`: data layer, `Meta`, `Mon`, the type chart, alias resolution and the cache.
- `engine.py`: Node bridge, `MatchupMatrix`, per-cup result cache.
- `harness.js`: runs PvPoke's battle scripts in a Node `vm` sandbox.
- `scoring.py`: `TeamEvaluator`, coverage grade, role assignment, search.
- `report.py`: self-contained HTML report.
- `validate.py`: re-simulates PvPoke's published ratings and diffs them.
- `cli.py`: argparse front end.
- `cpm.json`: CP multipliers, level 1 to 51.
- `tests/test_builder.py`: unit suite.
- `examples/`: sample boxes and the Mega Catch Cup report.

## Tests

```bash
pytest                                              # unit tests, about 1 s
pvp-team-builder validate -l great -l ultra --n 40   # engine exactness
```

`validate` is the meaningful integration check: it re-simulates the ratings PvPoke published and expects zero error. Run it after touching `engine.py`, `harness.js` or anything that changes how movesets or stats are built.

The unit tests cover the type chart, stat maths against known PvPoke values, name resolution including Shadow and regional forms, letter grades, the distinct-threat filter, role assignment, evolution expansion, cup aliasing, the Mega limit and search ordering.

## Engine bridge
`harness.js` loads PvPoke's scripts into a Node `vm` context with a stub jQuery whose `$.ajax` serves the local gamemaster. Two behaviours are load-bearing.

- The ajax success callback must be deferred with `setTimeout(..., 0)`. `GameMaster.js` assigns its own methods after issuing the request, so a synchronous callback throws `createSearchMaps is not a function`.
- Battle end state must be read before the Pokemon are reset for the next pair. Reading after the reset returns full HP and makes every matchup look even.

Movesets are always set explicitly with `selectMove('fast'|'charged', ...)`. `selectRecommendedMoveset()` picks by usage volume and silently gives a different answer than PvPoke's own rankings.

To debug a single pair:

```bash
python - <<'PY'
import json, sys
from pvp_team_builder.pvp import Meta
from pvp_team_builder.engine import run_pairs
meta = Meta("great", quiet=True)
print(run_pairs(meta.store.file("gamemaster.json"), [("raichu","wigglytuff")],
                1500, movesets={"raichu": meta.get("raichu").moveset,
                                "wigglytuff": meta.get("wigglytuff").moveset}))
PY
```

## Style
Ruff at line length 110, targeting Python 3.10, with type hints on public functions. Comments explain why a non-obvious line exists; the code is meant to be readable without them.

## Adding a cup
Cups come from the gamemaster, so a newly published PvPoke cup needs no code. Add an entry to `CUP_ALIASES` in `pvp.py` only when the friendly name differs from the slug, and to `CUP_CP` only when the cap is not the league default. Check the result with `pvp-team-builder cups` and a `threats --cup <name>` run.

## Release checklist
1. `pytest` and `validate` both clean.
2. `python -m build`, then install the wheel in a clean venv to confirm `cpm.json` and `harness.js` are packaged.
3. Bump `version` in `pyproject.toml` and `__init__.py`.
4. Tag `vX.Y.Z`.
