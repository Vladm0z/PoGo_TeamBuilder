"""
Team scoring for the r/TheSilphArena "decent team in 5 minutes" workflow.

PvPoke turns each 1v1 into a 0-1000 rating (500 = even) and reports two things
per team (js/interface/TeamInterface.js):

- a meta scorecard: for the top N threats, whether each team member wins and
  how many answers the team has;
- a coverage grade from the average rating against the six most dangerous
  threats, graded as letter(1200 - avg, goal = 680).

Coverage is the closest thing PvPoke has to a single team quality number, so it
drives the ranking, with scorecard pass rate as a tie-break.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from .pvp import Mon

ROLE_NAMES = ("lead", "switch", "closer")


def is_mega(mon: Mon) -> bool:
    """Mega Evolutions are separate ranked forms and are capped per team."""
    return "_mega" in mon.species_id or "mega" in (mon.species_id.split("_") or [])
GRADE_SCALE = (("A", 0.9), ("B", 0.8), ("C", 0.7), ("D", 0.6))
COVERAGE_GOAL = 680


# PvPoke-style grades
def letter_grade(value: float, goal: float) -> str:
    """PvPoke's calculateLetterGrade()."""
    pct = value / goal if goal else 0
    for name, threshold in GRADE_SCALE:      # highest threshold first
        if pct >= threshold:
            return name
    return "F"


def coverage_grade(threat_avg_rating: float) -> str:
    """
    PvPoke's coverage grade: letter(1200 - avg, goal 680), with `avg` measured
    from the threat's side. Mirrors TeamInterface.js.
    """
    return letter_grade(1200 - threat_avg_rating, COVERAGE_GOAL)


def coverage_from_our_perspective(our_avg_rating: float) -> str:
    """Same grade from our-side ratings. Approximation: ratings are directional."""
    return coverage_grade(1000 - our_avg_rating)


def grade_for(score: float) -> str:
    """Back-compat helper: grade a 0-1000 'best answer' average."""
    return coverage_grade(score)


# Result object
@dataclass
class Ranking:
    """One scored team plus everything needed to explain it."""

    mons: tuple[Mon, ...]
    best_mean: float                     # mean of best-member rating across the scorecard (our side)
    worst6_mean: float                   # mean BEST-member rating vs the 6 most dangerous threats
    coverage_pct: float                  # share of threats where at least one member wins
    corebreaker_pct: float               # share of threats nobody answers
    grade: str                           # PvPoke coverage grade
    per_threat: dict[str, dict]          # threat -> {ratings, best, answers}
    corebreakers: list[tuple[str, float]]  # (threat, best rating) with no answer
    single_answer: list[tuple[str, float]]
    threat_worst6: float = 0.0           # mean THREAT rating vs our 3 members, 6 worst (PvPoke's number)
    roles: dict[str, str] = field(default_factory=dict)
    role_scores: dict[str, float] = field(default_factory=dict)
    threat_list: tuple[str, ...] = ()
    coverage_set: tuple[str, ...] = ()   # the 6 threats that set the coverage grade
    estimated: int = 0


    # Presentation
    @property
    def score(self) -> float:
        """Ranking value: PvPoke's threat-side coverage number, flipped to our side."""
        return round(1000 - self.threat_worst6, 1)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(m.name for m in self.mons)

    def ordered(self) -> tuple[Mon, ...]:
        """(lead, safe switch, closer)."""
        by_id = {m.species_id: m for m in self.mons}
        out = [by_id[self.roles[r]] for r in ROLE_NAMES if r in self.roles]
        out += [m for m in self.mons if m not in out]
        return tuple(out[:3])

    def role_label(self, role: str) -> str | None:
        sid = self.roles.get(role)
        if sid is None:
            return None
        for m in self.mons:
            if m.species_id == sid:
                return m.name
        return sid

    def wins_for(self, mon: Mon) -> int:
        return sum(1 for t, d in self.per_threat.items() if d["ratings"].get(mon.species_id, 0) > 500)

    def to_dict(self, meta=None) -> dict:
        d = {
            "team": [m.name for m in self.mons],
            "order": {"lead": self.role_label("lead"), "switch": self.role_label("switch"),
                      "closer": self.role_label("closer")},
            "grade": self.grade,
            "score": self.score,
            "best_mean_rating": round(self.best_mean, 1),
            "worst6_best_answer": round(self.worst6_mean, 1),
            "worst6_threat_side": round(self.threat_worst6, 1),
            "coverage_pct": round(self.coverage_pct, 1),
            "corebreaker_pct": round(self.corebreaker_pct, 1),
            "corebreakers": [{"threat": t, "rating": round(r)} for t, r in self.corebreakers],
            "single_answer": [{"threat": t, "rating": round(r)} for t, r in self.single_answer],
            "wins_per_member": {m.name: self.wins_for(m) for m in self.mons},
            "movesets": {m.name: list(m.move_names()) for m in self.mons},
            "coverage_set": [{"threat": meta.rankings[t].name if meta else t,
                              "threat_side": round(self.per_threat[t]["threat_avg"])} for t in self.coverage_set],
            "estimated_cells": self.estimated,
        }
        if meta is not None:
            d["pvpoke_url"] = meta.team_builder_link(self.mons)
        return d


# Threat diversity (PvPoke only counts one representative per "kind" of threat)
def _base_species(species_id: str) -> str:
    for suffix in ("_shadow", "_mega", "_mega_x", "_mega_y", "_xs", "_xl", "_busted",
                   "_meteor", "_core", "_blade", "_shield", "_gorging", "_gulping"):
        species_id = species_id.replace(suffix, "")
    return species_id


def _similar(a: Mon, b: Mon) -> bool:
    if _base_species(a.species_id) == _base_species(b.species_id):
        return True
    return bool(set(a.types) & set(b.types)) and set(a.types) == set(b.types)


def worst_threats(per_threat: dict[str, dict], rankings: dict[str, Mon], n: int = 6) -> list[str]:
    """The `n` most dangerous distinct threats; one per species and type combo."""
    ordered = sorted(per_threat, key=lambda t: -per_threat[t].get("threat_avg", -per_threat[t]["best"]))
    chosen: list[Mon] = []
    out: list[str] = []
    for tid in ordered:
        mon = rankings.get(tid)
        if mon is None:
            continue
        if any(_similar(mon, c) for c in chosen):
            continue
        chosen.append(mon)
        out.append(tid)
        if len(out) >= n:
            break
    return out


# Evaluator
class TeamEvaluator:
    """Scores candidate teams against a threat list."""

    def __init__(self, meta, scorecard_size: int = 30, threat_list: Sequence[Mon] | None = None,
                 penalty: float = 0.0):
        self.meta = meta
        self.scorecard_size = scorecard_size
        self.threats: list[Mon] = list(threat_list) if threat_list else list(meta.ranked(scorecard_size))
        self.penalty = penalty


    # One team
    def evaluate(self, team: Sequence[Mon]) -> Ranking:
        team = tuple(team)
        per_threat: dict[str, dict] = {}
        estimated = 0
        for t in self.threats:
            ratings, threat_side = {}, []
            for mine in team:
                ours = self.meta.matchup(mine, t)
                ratings[mine.species_id] = ours
                            # PvPoke builds its scorecard from the threat's side.
                threat_side.append(self.meta.matchup(t, mine))
                if t.species_id not in mine.scorecard:
                    estimated += 1
            best = max(ratings.values()) if ratings else 0.0
            per_threat[t.species_id] = {
                "ratings": ratings,
                "threat_avg": sum(threat_side) / len(threat_side),
                "best": best,
                "answers": sum(1 for r in ratings.values() if r > 500),
            }

        best_mean = sum(d["best"] for d in per_threat.values()) / max(len(per_threat), 1)
        wins = sum(1 for d in per_threat.values() if d["answers"] > 0)
        core = sum(1 for d in per_threat.values() if d["answers"] == 0)
        worst = worst_threats(per_threat, self.meta.rankings, 6)
        worst6_mean = (sum(per_threat[t]["best"] for t in worst) / len(worst)) if worst else best_mean
        threat_worst6 = (sum(per_threat[t]["threat_avg"] for t in worst) / len(worst)) if worst else 1000 - best_mean

        corebreakers = sorted(((self.meta.rankings[t].name, d["best"])
                               for t, d in per_threat.items() if d["answers"] == 0),
                              key=lambda x: x[1])[:8]
        single = sorted(((self.meta.rankings[t].name, d["best"])
                         for t, d in per_threat.items() if d["answers"] == 1),
                        key=lambda x: x[1])[:8]

        ranking = Ranking(
            mons=team,
            best_mean=best_mean,
            worst6_mean=worst6_mean,
            coverage_pct=100.0 * wins / max(len(per_threat), 1),
            corebreaker_pct=100.0 * core / max(len(per_threat), 1),
            threat_worst6=threat_worst6,
            grade=coverage_grade(threat_worst6),
            per_threat=per_threat,
            corebreakers=corebreakers,
            single_answer=single,
            threat_list=tuple(t.species_id for t in self.threats),
            coverage_set=tuple(worst),
            estimated=estimated,
        )
        ranking.roles, ranking.role_scores = self.assign_roles(team)
        return ranking


    # Steps 4 and 5 of the post
    def assign_roles(self, team: Sequence[Mon]) -> tuple[dict[str, str], dict[str, float]]:
        """
        Lead = highest rated in PvPoke's *Leads* ranking (step 4).
        Of the rest, the better *Switches* score takes the safe-swap slot and
        the other closes (step 5).
        """
        three = list(team)
        if len(three) == 1:
            m = three[0]
            return {"lead": m.species_id}, {"lead": m.scores.get("leads", 0)}
        lead = max(three, key=lambda m: (m.scores.get("leads", 0), m.overall))
        rest = [m for m in three if m is not lead]
        if len(rest) == 1:
            sw = cl = rest[0]
        else:
            sw = max(rest, key=lambda m: (m.scores.get("switches", 0), m.overall))
            cl = [m for m in rest if m is not sw][0]
        return (
            {"lead": lead.species_id, "switch": sw.species_id, "closer": cl.species_id},
            {"lead": lead.scores.get("leads", 0), "switch": sw.scores.get("switches", 0),
             "closer": cl.scores.get("closers", 0)},
        )


    # Step 3 of the post: greedy "add the best alternative"
    def greedy_build(self, pool: Sequence[Mon], max_megas: int | None = None) -> list[Mon]:
        """Start from the best-ranked mon you own, then add the best next pick twice."""
        if not pool:
            return []
        ceiling = 3 if max_megas is None else max_megas

        def mega_count(team):
            return sum(1 for m in team if is_mega(m))

        start = min(pool, key=lambda m: m.rank)
        if max_megas is not None and is_mega(start) and max_megas == 0:
            start = min((m for m in pool if not is_mega(m)), key=lambda m: m.rank)
        team = [start]
        while len(team) < 3:
            best, best_score = None, -1.0
            for cand in pool:
                if cand in team:
                    continue
                if max_megas is not None and is_mega(cand) and mega_count(team) >= ceiling:
                    continue
                score = self.evaluate(team + [cand]).score
                if score > best_score:
                    best, best_score = cand, score
            if best is None:
                break
            team.append(best)
        return team


# Search
@dataclass
class SearchResult:
    rankings: list[Ranking]
    pool: list[Mon]
    threats: list[Mon]
    evaluated: int
    pruned: bool


def search_teams(meta, pool: Sequence[Mon], top_k: int = 10, scorecard_size: int = 30,
                 team_size: int = 3, max_exhaustive: int = 4000, prefilter: int | None = None,
                 threat_list: Sequence[Mon] | None = None, dedupe_core: bool = False,
                 max_megas: int | None = 1) -> SearchResult:
    """
    Enumerate combinations of `pool`, return the best `top_k`.

    Above `max_exhaustive` combinations the box is pre-filtered by solo score.
    Pre-filtering has changed the winning team in practice, so the default
    threshold is generous.
    """
    pool = list(pool)
    if len(pool) < team_size:
        raise ValueError(f"need at least {team_size} Pokemon, got {len(pool)}")

    evaluator = TeamEvaluator(meta, scorecard_size=scorecard_size, threat_list=threat_list)

    pruned = False
    candidates = pool
    if math.comb(len(pool), team_size) > max_exhaustive:
        pruned = True
        n = prefilter or max(team_size + 2, min(len(pool), int(max_exhaustive ** (1 / team_size)) + 6))
        candidates = sorted(pool, key=lambda m: -evaluator.evaluate([m]).score)[:n]

    combos = itertools.combinations(candidates, team_size)
    if max_megas is not None:
        combos = (c for c in combos if sum(1 for m in c if is_mega(m)) <= max_megas)
    results: list[Ranking] = [evaluator.evaluate(c) for c in combos]
    # Worst threat first: it is the number that decides a losing team.
    results.sort(key=lambda r: (r.threat_worst6, -r.coverage_pct, -r.best_mean))
    if dedupe_core:
        results = dedupe_by_core(results)

    return SearchResult(rankings=results[:top_k], pool=list(candidates), threats=evaluator.threats,
                        evaluated=len(results), pruned=pruned)


def dedupe_by_core(results: list[Ranking], max_repeat: int = 2) -> list[Ranking]:
    """Keep the top list diverse so one good pair doesn't fill it."""
    seen: dict[frozenset[str], int] = {}
    out = []
    for r in results:
        cores = [frozenset(p) for p in itertools.combinations((m.species_id for m in r.mons), 2)]
        if any(seen.get(c, 0) >= max_repeat for c in cores):
            continue
        for c in cores:
            seen[c] = seen.get(c, 0) + 1
        out.append(r)
    return out or results


# Text report
def mon_line(mon: Mon) -> str:
    """One-line stat and moveset summary for reports."""
    types = "/".join(t.title() for t in mon.types)
    moves = " + ".join(mon.move_names())
    return (f"{mon.name} - {types} - atk {mon.stats['atk']:.1f} / def {mon.stats['def']:.1f} / "
            f"hp {mon.stats['hp']:.0f} - {moves}")


def describe_team(r: Ranking, meta, evaluator: TeamEvaluator, show_threats: int = 6,
                  detail: bool = False, moveset_table: bool = True) -> str:
    lead, switch, closer = r.ordered()
    lines = [
        f"  {r.grade}   coverage {r.score:5.1f}/1000 (PvPoke-style: 1000 - threat avg vs your 6 worst) | "
        f"best-answer avg {r.best_mean:5.1f} | scorecard {r.coverage_pct:4.0f}% answered"
        f" | unanswerable {r.corebreaker_pct:.0f}%",
        f"  team : {' / '.join(m.name for m in r.mons)}",
        f"  order: {lead.name} (lead) -> {switch.name} (safe swap) -> {closer.name} (closer)",
        f"  roles: lead {r.role_scores.get('lead', 0):.0f} | switch {r.role_scores.get('switch', 0):.0f}"
        f" | closer {r.role_scores.get('closer', 0):.0f}   (PvPoke Lead/Switch/Closer scores)",
    ]
    if moveset_table:
        lines.append("  build:")
        for label, mon in (("lead  ", lead), ("switch", switch), ("closer", closer)):
            lines.append(f"    {label} {mon_line(mon)}")
        for mon in r.mons:
            if mon not in (lead, switch, closer):
                lines.append(f"           {mon_line(mon)}")
    if r.corebreakers:
        lines.append("  corebreakers (nobody wins): " +
                     ", ".join(f"{n} ({v:.0f})" for n, v in r.corebreakers[:show_threats]))
    if r.single_answer:
        lines.append("  only one answer          : " +
                     ", ".join(f"{n} ({v:.0f})" for n, v in r.single_answer[:show_threats]))
    if r.coverage_set:
        lines.append("  coverage set (threat's average rating against your team):")
        for tid in r.coverage_set:
            d = r.per_threat[tid]
            lines.append(f"    {meta.rankings[tid].name:<26} threat-side {d['threat_avg']:5.0f}"
                         f"   your best answer {d['best']:4.0f}   answers {d['answers']}/3")
    worst = sorted(evaluator.threats, key=lambda t: r.per_threat[t.species_id]["best"])[:4]
    lines.append("  hardest meta threats     : " + ", ".join(
        f"{t.name} ({r.per_threat[t.species_id]['best']:.0f})" for t in worst))
    lines.append("  answers per member       : " + ", ".join(
        f"{m.name} {r.wins_for(m)}/{len(evaluator.threats)}" for m in r.mons))
    if detail:
        lines.append("  full scorecard (best rating of your team vs each threat; >500 = you win):")
        for t in sorted(evaluator.threats, key=lambda t: r.per_threat[t.species_id]["best"]):
            d = r.per_threat[t.species_id]
            per = " ".join(f"{m.name[:12]}={d['ratings'][m.species_id]:.0f}" for m in r.mons)
            lines.append(f"    {t.name:<26} best {d['best']:5.0f}  answers {d['answers']}/3  "
                         f"threat-side {d['threat_avg']:4.0f}  [{per}]")
    return "\n".join(lines)
