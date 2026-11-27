# Methodology
What the tool computes, how it maps onto PvPoke, and where the numbers stop being trustworthy.

## Workflow
The tool automates the five-step manual loop from r/TheSilphArena's ["How to Build a Decent Team in 5 Minutes"](https://www.reddit.com/r/TheSilphArena/comments/1dmu3xk/how_to_build_a_decent_team_in_5_minutes/).

- Take the highest ranked meta Pokemon you own as pick one: `greedy_build` starts from the best-ranked owned mon.
- Import the meta into PvPoke's team builder at scorecard length 30: the threat list is the format's own meta group, cut to the scorecard length.
- Rate, add the best available alternative, rate, add again: `greedy_build` reproduces the loop, and `search_teams` replaces it with an exhaustive search.
- Read the Leads ranking to choose the lead: `assign_roles` reads PvPoke's `leads` score.
- Read Switches and Closers to play a bad lead: `assign_roles` reads `switches` and `closers`.

Two points from the post's comments are first-class output: corebreakers, meaning threats nobody on the team beats, and single-answer threats, meaning matchups that depend on one Pokemon and make the team prone to rock-paper-scissors.

## Matchup ratings
A 1v1 is one simulation at a fixed shield count, and the rating is PvPoke's own:

```
rating = floor( (my remaining HP fraction + damage dealt fraction) * 500 )
```

500 is even, 1000 a flawless win, 0 a loss without dealing damage. The values come from one of three sources, in priority order.

- The published value. Each rankings entry carries the ratings of its five best and five worst matchups, used as-is when the pair is present.
- The simulated value. Everything else comes from PvPoke's engine driven by `harness.js`, with both movesets taken from the rankings.
- An estimate. Only when the engine is unavailable, meaning `--engine simple` or no Node. It is a function of type effectiveness, bulk and attack, and the report flags it.

Ratings are directional. `a vs b` and `b vs a` are separate simulations because turn order and shield order break symmetry, so both directions are computed.

## Team metrics
Given a team of three and a threat list of N:

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

- A: value over goal at least 0.90, meaning a threat average of 588 or lower.
- B: at least 0.80, meaning 656 or lower.
- C: at least 0.70, meaning 724 or lower.
- D: at least 0.60, meaning 792 or lower.
- F: below 0.60, meaning above 792.

Two details decide whether the number is right.

- Direction. PvPoke builds the scorecard from the threat's side and subtracts from 1200. Reading that as a team-side average and subtracting from 1200 anyway shifts every grade up by about one step; this project made that mistake and fixed it, and `tests/test_builder.py` pins the mapping.
- Distinctness. The six threats that set the grade pass a similarity filter, as on PvPoke: a Shadow or regional form of a counted species does not take a second slot, and neither does another species with an identical type combination. Without it a team can be graded on the same Pokemon three times.

## Ranking
Teams are ordered by coverage, then `coverage_pct`, then `best_mean`. Coverage comes first because it is the number a player should act on: it drops when one popular threat beats the whole team. A team that answers 96 percent of the meta and still grades B is a normal outcome.

`--diverse` instead limits how often any two-Pokemon core may appear in the results, which spreads the list across different shapes. It is off by default because it reorders past numerically better teams.

## Roles
`lead` is whichever of the three has the best PvPoke Leads score. Of the other two, the better Switches score takes the safe swap and the remaining one closes. That is procedural, matching steps four and five, and it ignores matchup context: it will not knowingly lead a Pokemon that loses to the most common leads. When both remaining Pokemon are poor switch-ins, the post's own advice applies, which is to sacrifice the lead and keep the closer in back; the tool reports the low switch score instead of pretending otherwise.

## Simulation scope
The simulator is one Pokemon against one Pokemon. There is no switching, no energy carry-over between matchups and no alignment, shields are a fixed count for both sides rather than a strategic choice, and a team is never played out as a 3v3 game.

A coverage grade is therefore a statement about the scorecard, not about win rate. Three teams within 10 points of each other are effectively tied, and the corebreaker list is a better tiebreaker than the score.

## Limitations
- Teams of three only, which is the GO Battle League format.
- ABC lineups only. The post is explicit that ABB and BAB need switch-timing judgement that does not fit a five-minute process.
- One Mega per team in Mega-enabled cups, matching the battle rule.
- Catch Cup recency cannot be verified from PvPoke data, so it is assumed and stated in the output.
- Cup filters are advisory. Include and exclude rules from the gamemaster produce warnings, never silent removals, and the cup's rankings file decides what is ranked there.

## Validation
`pvp-team-builder validate` deletes the cached matrix, re-simulates every published matchup for the top N Pokemon of a league and diffs the results. The expected result is every pair exact with a maximum error of 0. CI runs it against Great and Ultra League on every push.

Validation covers the simulation layer and the data plumbing. It does not show that the team-level aggregates are sensible; unit tests pin the grade function, the distinct-threat filter, role assignment and the Mega limit.
