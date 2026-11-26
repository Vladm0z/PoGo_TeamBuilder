# Methodology

What this tool computes, how it maps onto PvPoke, and where the numbers stop
being trustworthy. Written to be checked, not believed.

## The workflow it automates

r/TheSilphArena's ["How to Build a Decent Team in 5
Minutes"](https://www.reddit.com/r/TheSilphArena/comments/1dmu3xk/how_to_build_a_decent_team_in_5_minutes/)
describes a five-step manual loop in GO Battle Log and PvPoke:

| Step | Manual action | Automation |
| --- | --- | --- |
| 1 | Take the highest ranked meta Pokemon you own as pick one | `TeamEvaluator.greedy_build` starts from the best-ranked owned mon |
| 2 | Import the meta into PvPoke's team builder, scorecard length 30 | Threat list = the format's own meta group, truncated to the scorecard length |
| 3 | Rate, add the best available alternative, rate, add again | `greedy_build` reproduces that loop; `search_teams` replaces it with an exhaustive search |
| 4 | Read the Leads ranking to choose the lead | `assign_roles` reads PvPoke's `leads` score |
| 5 | Read Switches / Closers to know how to play a bad lead | `assign_roles` reads `switches` and `closers` |

Two additions from the post's comments are implemented as first-class output:
**corebreakers** (threats nobody on the team beats) and **single-answer
threats** (matchups that depend on one Pokemon, so the team is prone to
rock-paper-scissors).

## Matchup ratings

A 1v1 is one simulation with a fixed shields setting. The rating is PvPoke's own:

```
rating = floor( (my remaining HP fraction + damage dealt fraction) * 500 )
```

500 is even, 1000 is a flawless win, 0 is a loss without dealing damage. These
are the numbers printed in PvPoke's team builder.

Sources, in priority order:

1. **Published value.** Each Pokemon's rankings entry carries the ratings of its
   five best and five worst matchups. When the pair is there, it is used as-is.
2. **Simulated value.** Everything else comes from running PvPoke's engine
   (`src/pvp_team_builder/harness.js`) with both movesets taken from the
   rankings. Cached per league and cup in `data/matrix-<cup>-<cp>.json`.
3. **Estimate.** Only if the engine is unavailable (`--engine simple`, or no
   Node): a function of type effectiveness, bulk and attack. Flagged in the
   report and excluded from any claim of accuracy.

Ratings are directional. `a vs b` and `b vs a` are separate simulations because
turn order and shield order break symmetry, and both directions are computed.

## Team metrics

Given a team of three and a threat list of *N*:

```
per threat:  our ratings   = [team[i] vs threat for i in 1..3]
             threat rating = mean(threat vs team[i])          # threat's perspective
             best          = max(our ratings)
             answers       = count(our rating > 500)

best_mean    = mean(best over all threats)
coverage_pct = 100 * count(threats with >= 1 answer) / N
coverage set = the 6 most dangerous distinct threats, ordered by threat rating
threat_avg   = mean(threat rating over the coverage set)
coverage     = 1000 - threat_avg
grade        = letter_grade(1200 - threat_avg, goal = 680)
```

`letter_grade` mirrors `TeamInterface.js`:

| Grade | Requirement | Equivalent threat average |
| --- | --- | --- |
| A | value / goal >= 0.90 | 588 or lower |
| B | >= 0.80 | 656 or lower |
| C | >= 0.70 | 724 or lower |
| D | >= 0.60 | 792 or lower |
| F | below 0.60 | above 792 |

**Direction matters.** PvPoke builds the scorecard from the threat's side and
then subtracts from 1200. Reading that as a team-side average and subtracting
from 1200 anyway (an easy mistake, and one this project made and fixed) shifts
every grade up by roughly one step. `tests/test_builder.py` pins the mapping.

**Distinctness.** The six threats that set the grade are chosen with a
similarity filter, as PvPoke does: a Shadow form or a regional form of an
already counted species does not occupy a second slot, and neither does a
different species with an identical type combination. Without this, a team can
be graded on the same Pokemon three times.

## Ranking

Teams are ordered by `coverage` (descending), then `coverage_pct`, then
`best_mean`. Coverage first because it is the metric a player should act on: it
is the one that drops when a single popular threat beats the whole team. A team
that answers 96% of the meta and grades B is a normal, expected outcome.

`--diverse` changes this to limit how often any two-Pokemon core may appear in
the results, which spreads the list across different shapes. It is off by
default because it reorders past numerically better teams.

## Roles

`lead` is the Pokemon with the best PvPoke **Leads** score among the three.
Of the remaining two, the better **Switches** score takes the safe-swap slot and
the other closes. This is procedural, matching steps 4 and 5, and it ignores
matchup context: it will not knowingly lead a Pokemon that loses to the most
common leads. When the two remaining Pokemon are both poor switch-ins, the
honest advice from the post applies - sacrifice the lead and keep the closer in
back - which the tool reports by showing the low switch score rather than
pretending otherwise.

## Simulation scope and known gaps

The simulator is one Pokemon versus one Pokemon:

- no switching, no energy carry-over between matchups, no alignment;
- shields are a fixed count for both sides, not a strategic choice;
- a team is never played out as a 3v3 game.

Therefore a coverage grade is a statement about the scorecard, not about win
rate. Three teams within 10 points of each other are effectively tied, and the
`corebreakers` list is a better tiebreaker than the number.

Other deliberate limits:

- **Teams of three only.** GO Battle League's format.
- **ABC lineups.** The post is explicit that ABB and BAB require switch-timing
  judgement that does not fit a five-minute process; they are out of scope.
- **One Mega per team** in Mega-enabled cups, matching the battle rule.
- **Catch Cup recency is not verifiable** from PvPoke data, so it is assumed and
  stated in the output.
- **Cup filters are advisory.** Include/exclude rules from PvPoke's gamemaster
  produce warnings, never silent removals; the rankings file for a cup is the
  source of truth for what is ranked there.

## Validation

`pvp-team-builder validate` deletes the cached matrix, re-simulates every
published matchup for the top *N* Pokemon of a league, and diffs. Expected
result: every pair exact, maximum error 0. This runs against Great and Ultra
League in CI on every push (`docs/development.md`).

Validation covers the simulation layer and the data plumbing. It does not prove
the team-level aggregates are sensible; those are pinned by unit tests for the
grade function, the distinct-threat filter, role assignment and the Mega limit.
