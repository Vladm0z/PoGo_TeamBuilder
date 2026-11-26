# pvp-team-builder

Team search for Pokemon GO PvP. Give it the Pokemon you actually own; it scores
every legal 3-Pokemon combination against the current meta and returns ranked
teams with a lead / safe-swap / closer assignment and the movesets to run.

Scores are not estimates. The tool executes PvPoke's own battle engine
(`GameMaster.js`, `Pokemon.js`, `Battle.js`, `ActionLogic.js`) headlessly through
Node and reproduces the ratings published on pvpoke.com to the point.

```
$ pvp-team-builder teambuild -l great --cup "mega catch cup" --file my_box.txt --evolutions

--- Best 5 of 10434 legal combinations ---
    ranked by PvPoke's coverage metric, then by scorecard pass rate:

    #   coverage  answers  grade  team  (lead / swap / closer)
    1        385      96%      B  Raichu / Wigglytuff / Vaporeon
    2        383      92%      B  Raichu / Wigglytuff / Flygon
    3        379      88%      B  Umbreon / Raichu / Wigglytuff

#1
  B   coverage 384.6/1000 | best-answer avg 666.5 | scorecard 96% answered
  team : Raichu / Vaporeon / Wigglytuff
  order: Raichu (lead) -> Wigglytuff (safe swap) -> Vaporeon (closer)
  build:
    lead   Raichu — Electric · atk 133.5 / def 110.6 / hp 114 · Volt Switch + Volt Tackle + Trailblaze
    switch Wigglytuff — Normal/Fairy · atk 115.1 / def 75.5 / hp 223 · Charm + Icy Wind + Swift
    closer Vaporeon — Water · atk 118.4 / def 96.9 / hp 165 · Water Gun + Aqua Tail + Last Resort
  corebreakers (nobody wins): Rillaboom (329)
```

## Requirements

| | |
| --- | --- |
| Python | 3.10 or newer |
| Node.js | 18 or newer, for exact simulation |
| Network | first run only (downloads PvPoke data; ~30 MB, cached) |

Without Node the tool still runs with `--engine simple`, using type and stat
estimates. Those are fast and rough; treat them as a sanity check, not a ranking.

## Install

```bash
git clone https://github.com/USER/pvp-team-builder   # replace USER with your account
cd pvp-team-builder
python -m venv .venv && . .venv/bin/activate
pip install -e .
```

To create the remote repository from this checkout, `./scripts/publish.sh`
(needs the GitHub CLI) sets the description, topics and remote, then pushes.

## Usage

Write your Pokemon one per line (comments with `#`), then:

```bash
# open Great League, 1800 rating
pvp-team-builder teambuild -l great --file my_box.txt --elo 1800

# a cup, expanding every Pokemon to its full evolution family
pvp-team-builder teambuild -l great --cup "mega catch cup" --file my_box.txt --evolutions

# ad-hoc list, top 10 instead of 5, plus an HTML report
pvp-team-builder teambuild -l ultra --mons "Talonflame, Swampert, Obstagoon, Cresselia" \
    --top 10 --html teams.html

# one specific team, with the full per-threat scorecard
pvp-team-builder rate -l great --mons "Raichu, Wigglytuff, Vaporeon"

# what is being graded against, and what the cup allows
pvp-team-builder threats -l great --cup mega --scorecard 30
pvp-team-builder info -l great --mons "Raichu, Toxtricity, Kingambit"
```

`--elo` follows the workflow this tool automates: below 1900 the scorecard
covers 30 threats, below 2400 it covers 25, otherwise 20.

### Commands

| Command | Purpose |
| --- | --- |
| `teambuild` | Rank every legal 3-Pokemon team from your box |
| `rate` | Score one team, with the per-threat scorecard |
| `alternatives` | Best next pick for a 1- or 2-Pokemon core |
| `threats` | Show the meta and threat list in use |
| `info` | Stats, moveset, role scores and best/worst matchups |
| `cups` | List cups and CP caps PvPoke publishes |
| `validate` | Re-simulate PvPoke's published ratings and diff them |

Flags common to all commands: `-l/--league`, `-c/--cup`, `--elo`, `--scorecard N`,
`--mons`, `--file`, `--engine {pvpoke,simple}`, `--offline`, `--refresh`,
`--data-dir`.

`teambuild` adds: `--top N`, `--evolutions`, `--shadows`, `--no-megas`,
`--max-megas N`, `--max-exhaustive N`, `--names`, `--detail`, `--diverse`,
`--html FILE`, `--json FILE`.

## How scoring works

PvPoke turns each 1v1 into a 0-1000 rating where 500 is even. Its team builder
then reports two things, and this tool reproduces both:

1. **Meta scorecard** - for the top *N* threats, does each of your three
   Pokemon win, and how many answers do you have.
2. **Coverage** - the average rating of your **six most dangerous distinct
   threats** against your team, graded as `letter(1200 - avg, goal = 680)`:
   A at 90% or better (average 588 or lower), B at 80%, C at 70%, D at 60%,
   otherwise F.

Teams are ranked by coverage, then by scorecard pass rate. Coverage is the
stricter of the two and the one worth reading: a team can answer 96% of the meta
and still grade B because one threat hits it at 745.

Two consequences worth knowing before trusting a number:

- **Coverage counts the threat's side.** PvPoke computes the scorecard from the
  opponent's perspective and inverts it with `1200 - avg`. Applying that
  inversion to your own side inflates every grade by one step. The report prints
  the six threats that set the grade, with both numbers, so it is auditable.
- **Scorecard wins are not game wins.** The simulation is one Pokemon against
  one, with shields. It does not model switching, energy carry-over or
  alignment, so a team that wins the scorecard still needs the reported roles to
  be played correctly. The `corebreakers` and `single answer` lists are the
  practical part: they say what to expect and where to spend a shield.

## Exactness

`pvp-team-builder validate` re-simulates every matchup PvPoke published in its
rankings (each Pokemon's five best and five worst results) and diffs them:

```
 great / all  CP 1500
  re-simulated 200 published matchups
  exact        200/200  (100.0%)
  max error    0
 ultra / all  CP 2500
  re-simulated 196 published matchups
  exact        196/196  (100.0%)
  max error    0
```

Three details make this work, each of which cost a debugging session:

- PvPoke's `selectRecommendedMoveset()` chooses by usage volume and does **not**
  produce the moveset in its own rankings. Movesets are set explicitly from the
  ranking data.
- The published numbers are the **single-shield 1v1** simulation (the team
  builder's default), not an average across shield counts.
- Only each Pokemon's top five wins and losses are published, so any full matrix
  has to be simulated. `engine.py` batches the missing pairs, runs them through
  `harness.js`, and caches the results in `data/matrix-<cup>-<cp>.json`.

If Node is missing, the tool falls back to type/stat estimates
(`Meta._estimate`) instead of failing, and labels the run accordingly.

## Cups, evolutions and Megas

Cups are addressed by slug or by name; the CP cap follows the cup
(`little` maps to 500) rather than the league flag:

```bash
pvp-team-builder cups -l great         # every cup/CP pair that has rankings
```

`--evolutions` expands each name to its whole family, so `eevee` means all eight
Eeveelutions, `magneton` means Magnemite/Magneton/Magnezone, and `hitmonlee`
means all three Hitmons. Mega Evolutions are included where they are ranked in
that cup. The run prints exactly what was expanded, and `--names` prints the
final pool with each Pokemon's rank and moveset.

Other pool controls:

- `--shadows` also considers Shadow forms. Off by default: a Shadow is a
  separate build, so it is never assumed.
- `--no-megas` drops Megas; `--max-megas N` caps them (`1` by default in
  Mega-enabled cups, matching the one-Mega-per-battle rule).
- Mythical Pokemon are always excluded, since cups that allow Megas ban them.

**Catch Cup caveat.** "Only Pokemon caught this season" depends on your account.
The tool assumes every listed Pokemon qualifies and says so in its output. Trim
the list to what you actually caught; with a smaller pool the teams change
substantially.

## Library use

```python
from pvp_team_builder import Meta, TeamEvaluator, search_teams
from pvp_team_builder.engine import MatchupMatrix

meta = Meta("great", cup="mega")                       # cup aliases accepted
box = [meta.get(n) for n in ("raichu", "wigglytuff", "vaporeon", "umbreon")]
threats = meta.threats_for(25)                          # the format's own meta group

MatchupMatrix(meta, [m.species_id for m in box + threats]).attach()   # exact numbers
evaluator = TeamEvaluator(meta, threat_list=threats)

evaluator.evaluate(box[:3]).to_dict(meta)               # one team, full breakdown
result = search_teams(meta, box, top_k=5, threat_list=threats, max_megas=1)
for ranking in result.rankings:
    print(ranking.grade, ranking.score, [m.name for m in ranking.ordered()])
```

## Scale and performance

| Box size | Combinations | Time (exact engine, warm cache) |
| --- | --- | --- |
| 15 | 455 | under 1 s |
| 41 (14 Pokemon with evolutions) | 10,434 | ~2.5 s |
| 60 | 34,220 | ~8 s |

All matchups are simulated once and cached, so repeat runs only pay for scoring.
Above `--max-exhaustive` (default 25,000) the box is pre-filtered by solo score
first; that is visible in the output. Pre-filtering has changed the winner in
practice, so leave the default alone unless the box is genuinely large.

## Data and credits

All simulation and ranking data is PvPoke's, by pvpoke. This project is an
automation layer: `harness.js` loads PvPoke's public battle scripts unmodified
and drives them from Python. Data and scripts are downloaded at runtime and
cached under `data/`, never redistributed here.

PvPoke is not affiliated with this project. If you find it useful, support the
site that does the actual work.

The workflow being automated is the community guide
["How to Build a Decent Team in 5 Minutes"](https://www.reddit.com/r/TheSilphArena/comments/1dmu3xk/how_to_build_a_decent_team_in_5_minutes/)
from r/TheSilphArena.

## License

MIT. See [LICENSE](LICENSE).
