# Data
All data comes from pvpoke.com at runtime. Nothing is vendored in this repository.

## What is cached
- `gamemaster.json` (from `/data/gamemaster.json`): species, base stats, moves, cups, formats and tags.
- `rankings-<cup>-<cp>-<slug>.json` (from `/data/rankings/...`): the `overall` ranking plus `leads`, `switches`, `closers`, `chargers`, `attackers` and `consistency`.
- `group-<name>.json` (from `/data/groups/<name>.json`): PvPoke's meta groups such as `great` and `megagreat`.
- `matrix-<cup>-<cp>.json` (generated locally): simulated ratings keyed `attacker|defender`.
- `engine/*.js` (from `/js/**`): the PvPoke battle scripts that `harness.js` loads.

A populated cache is about 30 MB, most of it ranking files.

## Cache location
Resolution order, highest priority first:

1. `--data-dir` on the command line.
2. `$PVP_TEAM_BUILDER_DATA`.
3. `$XDG_CACHE_HOME/pvp-team-builder`, else `~/.cache/pvp-team-builder`.

Nothing is written inside the checkout. The cache is downloaded data and should never reach a commit or `git status`.

## Refresh rules
- Rankings and the gamemaster are refetched after 7 days, or immediately with `--refresh`.
- `--offline` never touches the network. A missing required file fails with the path it expected; an incomplete matrix falls back to estimates for the missing pairs.
- The simulated matrix has no expiry, so a matrix built before a balance patch is stale. Delete `matrix-*.json` or run with `--refresh` after any update that changes stats or moves.

## Rate limits
Requests are plain `urllib` GETs with a descriptive user agent, no concurrency, and at most one fetch per file per week. A cold start is about 12 requests. The matrix is computed locally and never re-uploaded.

PvPoke is a community site. Do not disable the cache to poll it, and do not mirror its data from this project.

## Cups
PvPoke publishes one ranking set per cup and CP cap, and some formats share one set: Great League, Mega Great League, Mega Catch Cup and the Mega Halloween and Color cups all resolve to `mega` at CP 1500. `pvp-team-builder cups` prints every cup and CP pair that exists with the number of ranked Pokemon, which is the authoritative answer for what `--cup` accepts.

Caps that differ from the league default:

- `little`: 500.
- `cauldron`: 2500.
- `premier`: 10000.
- `battlefrontiermaster`: 10000.
