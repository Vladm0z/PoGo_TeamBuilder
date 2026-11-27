"""Tests. Run with `pytest` (the package is installed via `pip install -e .`)."""

from __future__ import annotations

import pytest

from pvp_team_builder.engine import MatchupMatrix, node_path
from pvp_team_builder.pvp import IMMUNE, NVE, SE, DataError, Meta, stats_at, type_multiplier
from pvp_team_builder.scoring import (
    TeamEvaluator,
    coverage_grade,
    letter_grade,
    search_teams,
    worst_threats,
)


@pytest.fixture(scope="module")
def meta():
    return Meta("great", quiet=True)

 
# Data layer 
def test_type_chart():
    assert type_multiplier("fairy", ["dragon", "flying"]) == pytest.approx(SE * 1.0)
    assert type_multiplier("dragon", ["fairy"]) == pytest.approx(IMMUNE)
    assert type_multiplier("ghost", ["normal"]) == pytest.approx(IMMUNE)
    assert type_multiplier("water", ["ground", "rock"]) == pytest.approx(SE * SE)
    assert type_multiplier("fire", ["water", "rock"]) == pytest.approx(NVE * NVE)


def test_stats_match_pvpoke():
    # Azumarill
    stats = stats_at({"atk": 112, "def": 152, "hp": 225}, 43, (4, 15, 13))
    assert stats["atk"] == pytest.approx(93.4, abs=0.2)
    assert stats["hp"] == 191
    assert stats["cp"] <= 1500


def test_resolver(meta):
    assert meta.resolve("Azumarill") == "azumarill"
    assert meta.resolve("shadow drapion") == "drapion_shadow"
    assert meta.resolve("drapion shadow") == "drapion_shadow"
    assert meta.resolve("G-Weezing") == "weezing_galarian"
    assert meta.resolve("galarian weezing") == "weezing_galarian"
    with pytest.raises(DataError):
        meta.resolve("notapokemonxyz")


def test_rankings_loaded(meta):
    assert len(meta.rankings) > 500
    azu = meta.get("azumarill")
    assert azu.types == ("water", "fairy")
    assert azu.moveset[0] == "BUBBLE"
    assert azu.scores["overall"] > 80
    assert meta.get("mimikyu").scores["leads"] >= 90


def test_cup_cp_switch():
    little = Meta("great", cup="little", quiet=True)
    assert little.cp == 500
    assert len(little.rankings) > 100

 
# Scoring 
def test_letter_grade_matches_pvpoke():
    # PvPoke: calculateLetterGrade(value, goal) -> A >= 90%, B >= 80%, ...
    assert letter_grade(680, 680) == "A"
    assert letter_grade(612, 680) == "A"      # 90%
    assert letter_grade(544, 680) == "B"      # 80%
    assert letter_grade(476, 680) == "C"
    assert letter_grade(408, 680) == "D"
    assert letter_grade(400, 680) == "F"


def test_worst_threats_dedupes_forms(meta):
    threats = meta.ranked(10)
    per = {}
    for t in threats:
        per[t.species_id] = {"best": 500 - threats.index(t) * 10, "answers": 0, "ratings": {}}
    chosen = worst_threats(per, meta.rankings, 6)
    bases = [c.replace("_shadow", "") for c in chosen]
    assert len(bases) == len(set(bases))


def test_evaluate_team(meta):
    ev = TeamEvaluator(meta, threat_list=meta.ranked(20))
    team = [meta.get(x) for x in ("azumarill", "skarmory", "clodsire")]
    r = ev.evaluate(team)
    assert 0 <= r.worst6_mean <= 1000
    assert 0 <= r.coverage_pct <= 100
    assert r.grade in {"A", "B", "C", "D", "F"}
    assert len(r.per_threat) == 20
    assert set(r.roles) == {"lead", "switch", "closer"}
    lead = max(team, key=lambda m: m.scores["leads"])
    assert r.roles["lead"] == lead.species_id


def test_greedy_build(meta):
    ev = TeamEvaluator(meta, threat_list=meta.ranked(15))
    pool = [meta.get(x) for x in ("azumarill", "skarmory", "clodsire", "talonflame", "umbreon")]
    team = ev.greedy_build(pool)
    assert len(team) == 3
    assert len(set(team)) == 3


def test_search_teams(meta):
    pool = [meta.get(x) for x in ("azumarill", "skarmory", "clodsire", "talonflame", "umbreon",
                                  "lanturn", "gastrodon", "dunsparce")]
    res = search_teams(meta, pool, top_k=3, threat_list=meta.ranked(15), max_exhaustive=10000)
    assert len(res.rankings) == 3
    scores = [r.score for r in res.rankings]
    assert scores == sorted(scores, reverse=True)
    assert res.evaluated == 56  # C(8,3)


def test_team_builder_link(meta):
    mons = [meta.get(x) for x in ("azumarill", "skarmory")]
    assert meta.team_builder_link(mons) == "https://pvpoke.com/team-builder/all/1500/azumarill,skarmory/"

 
# Engine (skipped when Node isn't available) 
needs_node = pytest.mark.skipif(not node_path() or not node_path(), reason="node not installed")


@needs_node
def test_engine_reproduces_published_ratings(meta):
    ranked = meta.ranked(12)
    ids = [m.species_id for m in ranked]
    published = {(m.species_id, o): r for m in ranked for o, r in m.scorecard.items() if o in ids}
    matrix = MatchupMatrix(meta, ids, quiet=True)
    for (a, b), expected in published.items():
        assert matrix.rating(a, b) == expected, f"{a} vs {b}"

 
# Cup rules, evolution expansion, mega limit (Mega Catch Cup) 
@pytest.fixture(scope="module")
def mega_meta():
    return Meta("great", cup="mega catch cup", quiet=True)


def test_cup_alias_and_cp(mega_meta):
    assert mega_meta.cup == "mega"
    assert mega_meta.cp == 1500
    mega_meta.threats_for(5)          # resolves and caches the format's meta group
    assert mega_meta._meta_group_name == "megagreat"


def test_evolution_expansion(mega_meta):
    assert set(mega_meta.expand_evolutions("eevee")) == {
        "eevee", "vaporeon", "jolteon", "flareon", "espeon", "umbreon",
        "leafeon", "glaceon", "sylveon"}
    assert mega_meta.expand_evolutions("magneton") == ["magnemite", "magneton", "magnezone"]
    assert mega_meta.expand_evolutions("rattata") == ["raticate", "raticate_alolan"]
    # shadows are opt-in
    assert "machamp_shadow" in mega_meta.expand_evolutions("machamp", include_shadows=True)
    assert "machamp_shadow" not in mega_meta.expand_evolutions("machamp")
    # megas are included by default, excludable
    assert "lucario_mega" in mega_meta.expand_evolutions("lucario")
    assert mega_meta.expand_evolutions("lucario", include_megas=False) == ["lucario"]
    # toxtricity's alternate forms aren't ranked in this cup
    assert mega_meta.expand_evolutions("toxtricity") == ["toxtricity"]


def test_threats_come_from_meta_group(mega_meta):
    threats = mega_meta.threats_for(10)
    assert len(threats) == 10
    group = set(mega_meta.meta_group())
    assert all(t.species_id in group for t in threats)


def test_one_mega_per_team(mega_meta):
    pool = [mega_meta.get(x) for x in ("lucario_mega", "raichu_mega_x", "wigglytuff",
                                       "umbreon", "vaporeon", "raichu")]
    res = search_teams(mega_meta, pool, top_k=50, threat_list=mega_meta.threats_for(10),
                       max_exhaustive=10000, max_megas=1)
    from pvp_team_builder.scoring import is_mega
    for r in res.rankings:
        assert sum(1 for m in r.mons if is_mega(m)) <= 1


def test_coverage_grade_is_threat_side():
    assert coverage_grade(520) == "A"
    assert coverage_grade(600) == "B"      # 600/680 = 88%
    assert coverage_grade(700) == "C"      # 500/680 = 74%
    assert coverage_grade(760) == "D"      # 440/680 = 65%
    assert coverage_grade(830) == "F"      # 370/680 = 54%
