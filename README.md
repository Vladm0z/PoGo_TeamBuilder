Team search for Pokemon GO PvP (based on [How to Build a *Decent* Team in 5 Minutes reddit post](https://www.reddit.com/r/TheSilphArena/comments/1dmu3xk/how_to_build_a_decent_team_in_5_minutes/)). Point it at the Pokemon you own and it scores every legal three-Pokemon team against the current meta, then reports the best ones with a lead, safe swap, closer and full movesets.

Scores are not estimates. The tool runs PvPoke's own battle scripts headlessly through Node and reproduces the ratings published on pvpoke.com exactly; `validate` checks that it still does.

```
$ pvp-team-builder teambuild -l great --cup "mega catch cup" --file my_box.txt --evolutions

--- Best 5 of 10434 legal combinations ---
    #   coverage  answers  grade  team  (lead / swap / closer)
    1        385      96%      B  Raichu / Wigglytuff / Vaporeon
    2        383      92%      B  Raichu / Wigglytuff / Flygon
    3        379      88%      B  Umbreon / Raichu / Wigglytuff

#1
  B   coverage 384.6/1000 | best-answer avg 666.5 | scorecard 96% answered
  order: Raichu (lead) -> Wigglytuff (safe swap) -> Vaporeon (closer)
  build:
    lead   Raichu - Electric - atk 133.5 / def 110.6 / hp 114 - Volt Switch + Volt Tackle + Trailblaze
    switch Wigglytuff - Normal/Fairy - atk 115.1 / def 75.5 / hp 223 - Charm + Icy Wind + Swift
    closer Vaporeon - Water - atk 118.4 / def 96.9 / hp 165 - Water Gun + Aqua Tail + Last Resort
  corebreakers (nobody wins): Rillaboom (329)
```

## Requirements
- Python 3.10 or newer.
- Node.js 18 or newer, for exact simulation.
- Network on the first run only. PvPoke's data is about 30 MB and is cached outside the checkout.

Without Node the tool still runs with `--engine simple`, which uses type and stat estimates. Treat those as a sanity check, not a ranking.

## Install

```bash
git clone https://github.com/Vladm0z/PoGo_TeamBuilder
cd pvp-team-builder
python -m venv .venv && . .venv/bin/activate
pip install -e .
```

## Usage

Write your Pokemon one per line, with `#` for comments, then run one of the following.

```bash
# open Great League, 1800 rating
pvp-team-builder teambuild -l great --file my_box.txt --elo 1800

# a cup, expanding each Pokemon to its full evolution family
pvp-team-builder teambuild -l great --cup "mega catch cup" --file my_box.txt --evolutions

# ad-hoc list, top 10 instead of 5, plus an HTML report
pvp-team-builder teambuild -l ultra --mons "Talonflame, Swampert, Obstagoon, Cresselia" --top 10 --html teams.html

# one specific team, with the full per-threat scorecard
pvp-team-builder rate -l great --mons "Raichu, Wigglytuff, Vaporeon"
```

### Commands

- `teambuild`: rank every legal three-Pokemon team from your box.
- `rate`: score one team, with the per-threat scorecard.
- `alternatives`: best next pick for a one- or two-Pokemon core.
- `threats`: show the meta and the threat list in use.
- `info`: stats, moveset, role scores and best and worst matchups for one Pokemon.
- `cups`: list the cups and CP caps PvPoke publishes.
- `validate`: re-simulate PvPoke's published ratings and diff them.

### Options

- `-l`, `--league` (League): `great`, `ultra`, `master` or `little`.
- `-c`, `--cup` (Cup): slug or name, for example `mega` or `"mega catch cup"`.
- `--elo` (Rating): sets the scorecard length, 30 below 1900, 25 below 2400, otherwise 20.
- `--mons` (List): comma-separated Pokemon, as an alternative to `--file`.
- `--file` (File): one Pokemon per line.
- `--engine` (Engine): `pvpoke` for exact simulation, `simple` for estimates.
- `--offline` (Offline): fail rather than download.
- `--refresh` (Refresh): re-download the cached data.
- `--data-dir` (Directory): override the cache location.

`teambuild` adds:

- `--top` (Count): number of teams to report, 5 by default.
- `--evolutions` (Expand): treat each name as its whole evolution family.
- `--shadows` (Shadows): also consider Shadow forms.
- `--no-megas` (No Megas): exclude Mega Evolutions.
- `--max-megas` (Limit): cap Megas per team, 1 by default, which is the game's own rule.
- `--max-exhaustive` (Threshold): combination count above which the box is pre-filtered, 25000 by default.
- `--names` (Names): print the resolved pool with ranks and movesets.
- `--detail` (Detail): print the full scorecard for every team.
- `--diverse` (Diverse): drop teams that share a core with a better one.
- `--html` (File): write a self-contained HTML report.
- `--json` (File): write machine-readable results.

## Scoring

PvPoke turns each 1v1 into a 0-1000 rating where 500 is even. Its team builder reports two numbers per team, and this tool reproduces both.

The meta scorecard checks, for the top N threats, whether each of your three Pokemon wins and how many answers the team has. Coverage grades the average rating of your six most dangerous distinct threats against the team as `letter(1200 - avg, goal = 680)`: A at 90 percent or better (average 588 or lower), B at 80, C at 70, D at 60, otherwise F.

Teams are ranked by coverage, then by scorecard pass rate. Coverage is the stricter number and the more useful one. A team can answer 96 percent of the meta and still grade B because a single threat hits it at 745.

Two properties of the metric are worth knowing. Coverage counts the threat's side of the matchup; applying the `1200 - avg` inversion to your own ratings inflates every grade by one step, so the report prints the six threats that set the grade with both numbers and can be audited. And scorecard wins are not game wins: the simulation is one Pokemon against one with shields, so switching, energy carry-over and alignment are not modelled. The `corebreakers` and single-answer lists are the practical part of the output, because they say what to expect and where to spend a shield.

## Exactness

`pvp-team-builder validate` re-simulates every matchup PvPoke published in its rankings, meaning each Pokemon's five best and five worst results, and diffs them.

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

Three details make that work, each of which cost a debugging session.

- PvPoke's `selectRecommendedMoveset()` picks by usage volume and does not produce the moveset in its own rankings, so movesets are set explicitly from the ranking data.
- The published numbers are the single-shield 1v1 simulation, the team builder's default, not an average across shield counts.
- Only each Pokemon's five best and five worst results are published, so a full matrix has to be simulated. `engine.py` batches the missing pairs, runs them through `harness.js` and caches the result.

## Cups and evolutions

Cups are addressed by slug or by name, and the CP cap follows the cup rather than the league flag, so `little` maps to 500.

```bash
pvp-team-builder cups -l great
```

`--evolutions` expands each name to its whole family: `eevee` means all eight Eeveelutions, `magneton` means Magnemite, Magneton and Magnezone, and `trapinch` brings Flygon and Vibrava. Mega Evolutions are included where they are ranked in that cup. The run prints what was expanded, and `--names` prints the final pool with each Pokemon's rank and moveset.

- `--shadows` also considers Shadow forms. It is off by default because a Shadow is a separate build.
- `--no-megas` drops Megas, and `--max-megas` caps them.
- Mythical Pokemon are excluded, since the cups that allow Megas ban them.

In a Catch Cup the "only Pokemon caught this season" rule depends on your account. The tool assumes every listed Pokemon qualifies and says so in its output, so trim the list to what you actually caught; a smaller pool changes the teams substantially.

## Library use

```python
from pvp_team_builder import Meta, TeamEvaluator, search_teams
from pvp_team_builder.engine import MatchupMatrix

meta = Meta("great", cup="mega")                       # cup aliases accepted
box = [meta.get(n) for n in ("raichu", "wigglytuff", "vaporeon", "umbreon")]
threats = meta.threats_for(25)                          # the format's own meta group

MatchupMatrix(meta, [m.species_id for m in box + threats]).attach()   # exact numbers
evaluator = TeamEvaluator(meta, threat_list=threats)
result = search_teams(meta, box, top_k=5, threat_list=threats, max_megas=1)

for ranking in result.rankings:
    print(ranking.grade, ranking.score, [m.name for m in ranking.ordered()])
```

## Performance

Every matchup is simulated once and cached, so repeat runs only pay for scoring. Times below are on a warm cache.

- 15 Pokemon, 455 combinations: under 1 s.
- 41 forms, 10434 combinations: about 2.5 s.
- 60 Pokemon, 34220 combinations: about 8 s.

Above `--max-exhaustive` the box is pre-filtered by solo score, which the output reports. Pre-filtering has changed the winning team in testing, so leave the default alone unless the box is genuinely large.

## Limitations and Artifacts
- Coverage, and therefore the ranking, comes from 1v1 simulations. Team-level effects such as switch advantage, alignment and energy carry-over are not simulated at all.
- The threat list is PvPoke's meta group for the format. A cup with a thin or unusual meta will grade teams against threats you rarely meet.
- Catch Cup legality is taken as given. The tool has no way to know what your account caught in the current season.
- Without Node the fallback estimator is fast and rough. Its rankings are not comparable with the exact engine's.
- All simulation, moveset and ranking data is PvPoke's. This repository redistributes none of it; data and scripts are downloaded at runtime.

## Credits
All simulation and ranking data is PvPoke's, by pvpoke, and the project is not affiliated with it. The workflow being automated is the community guide ["How to Build a Decent Team in 5 Minutes"](https://www.reddit.com/r/TheSilphArena/comments/1dmu3xk/how_to_build_a_decent_team_in_5_minutes/) from r/TheSilphArena.

## Versions
The tool tracks PvPoke's data rather than the game's patches, so dates here are release dates of this repository.

Date | Version | Notes
:--- | :-----: | :------
2026-11-27 | 1.1.0 | Cache moved out of the checkout. Documentation and comment restyle.
2026-11-26 | 1.0.0 | First release: exact engine bridge, team search, validation, HTML report.

## License

MIT. See [LICENSE](LICENSE).
