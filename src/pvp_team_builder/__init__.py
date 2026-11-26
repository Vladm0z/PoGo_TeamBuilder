"""
pvp-team-builder: team search for Pokemon GO PvP.

Scores candidate teams with PvPoke's own battle engine and ranks them the way
PvPoke's team builder reports them (meta scorecard + coverage grade).

Typical use:

    from pvp_team_builder import Meta, TeamEvaluator, search_teams
    from pvp_team_builder.engine import MatchupMatrix

    meta = Meta("great", cup="mega")
    box = [meta.get(name) for name in ("raichu", "wigglytuff", "vaporeon")]
    threats = meta.threats_for(25)
    MatchupMatrix(meta, [m.species_id for m in box + threats]).attach()

    evaluator = TeamEvaluator(meta, threat_list=threats)
    evaluator.evaluate(box).to_dict(meta)
    search_teams(meta, box, top_k=5, threat_list=threats).rankings
"""

from .engine import EngineUnavailable, MatchupMatrix, run_pairs
from .pvp import CUP_ALIASES, LEAGUE_CP, DataError, Meta, Mon, type_multiplier
from .scoring import (
    Ranking,
    TeamEvaluator,
    coverage_grade,
    describe_team,
    grade_for,
    is_mega,
    letter_grade,
    search_teams,
)

__version__ = "1.1.0"

__all__ = [
    "Meta", "Mon", "DataError", "LEAGUE_CP", "CUP_ALIASES", "type_multiplier",
    "MatchupMatrix", "run_pairs", "EngineUnavailable",
    "TeamEvaluator", "Ranking", "search_teams", "grade_for", "coverage_grade",
    "letter_grade", "is_mega", "describe_team",
    "__version__",
]
