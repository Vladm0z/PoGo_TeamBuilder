# Data

Everything is downloaded from pvpoke.com on first use and cached locally. No
PvPoke data is vendored in this repository.

## What is cached

| Path | Source | Purpose |
| --- | --- | --- |
| `data/gamemaster.json` | `/data/gamemaster.json` | species, base stats, moves, cups, formats, tags |
| `data/rankings-<cup>-<cp>-<slug>.json` | `/data/rankings/<cup>/<slug>/rankings-<cp>.json` | `overall` plus `leads`, `switches`, `closers`, `chargers`, `attackers`, `consistency` |
| `data/group-<name>.json` | `/data/groups/<name>.json` | PvPoke's meta groups (`great`, `megagreat`, cup groups) |
| `data/matrix-<cup>-<cp>.json` | generated | simulated ratings, keyed `attacker|defender` |
| `data/engine/*.js` | `/js/**` | PvPoke battle scripts used by `harness.js` |

Total after a full run is roughly 30 MB. Rankings files are the bulk of it.

## Cache location

Resolution order:

1. `--data-dir` (per command, highest priority)
2. `$PVP_TEAM_BUILDER_DATA`
3. `<project>/data` when running from a checkout (checked by the presence of
   `pyproject.toml`)
4. `$XDG_CACHE_HOME/pvp-team-builder` or `~/.cache/pvp-team-builder`

## Refresh rules

- Rankings and the gamemaster are refetched after 7 days, or immediately with
  `--refresh`.
- `--offline` never touches the network. If a required file is missing it fails
  with the path it expected; if the matrix is incomplete it silently falls back
  to estimates for the missing pairs.
- The simulated matrix has no expiry. A matrix built before a balance patch or a
  cup rotation is stale: delete `data/matrix-*.json` or run with `--refresh`
  after any game update that changes moves or stats.

## Rate limits and etiquette

Requests are plain `urllib` GETs with a descriptive user agent, no concurrency,
and at most one fetch per file per week. A cold start is about 12 requests. The
simulated matrix is computed locally and never re-uploaded.

PvPoke is a community site. Do not disable the cache to poll it, and do not
mirror its data from this project; fetch it from source.

## Cup slugs

PvPoke publishes one ranking set per cup and CP cap. Some GBL formats share one
set: Great League, Mega Great League, Mega Catch Cup and the Mega Halloween and
Color cups all resolve to `mega` at CP 1500. `pvp-team-builder cups` prints every
cup/CP pair that exists, with the number of ranked Pokemon, which is the
authoritative answer for what can be used with `--cup`.

Known caps that are not the league default:

| Cup | CP |
| --- | --- |
| `little` | 500 |
| `cauldron` | 2500 |
| `premier` | 10000 |
| `battlefrontiermaster` | 10000 |
