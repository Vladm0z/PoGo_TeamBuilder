"""
Command line interface.

    # rank every combination of the Pokemon you own
    pvp-team-builder teambuild -l great --mons "Azumarill, Skarmory, Clodsire" --elo 1800

    # from a file, with evolutions expanded, for a specific cup
    pvp-team-builder teambuild -l great --cup "mega catch cup" --file my_box.txt --evolutions

    # score one team in detail
    pvp-team-builder rate -l ultra --mons "Talonflame, Swampert, Obstagoon"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import EngineUnavailable, MatchupMatrix
from .pvp import LEAGUE_CP, DataError, Meta, Mon
from .scoring import (
    TeamEvaluator,
    describe_team,
    search_teams,
)


def build_meta(args) -> Meta:
    return Meta(args.league, args.cup, data_dir=args.data_dir, refresh=args.refresh, offline=args.offline)


def wire_engine(meta: Meta, args, species: list[str]) -> str:
    """Attach the exact PvPoke matrix; fall back to estimates if unavailable."""
    if getattr(args, "engine", "pvpoke") == "simple":
        return "simple (typing/stats estimates, no simulation)"
    try:
        matrix = MatchupMatrix(meta, species, refresh=args.refresh, quiet=False,
                               allow_download=not args.offline)
        matrix.attach()
        return f"pvpoke ({matrix.coverage(species)} pairs cached/simulated)"
    except EngineUnavailable as exc:
        print(f"[!] exact engine unavailable ({exc}); falling back to typing estimates", file=sys.stderr)
        return "simple (fallback: typing/stats estimates)"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def parse_list(items: list[str] | None, file: str | None) -> list[str]:
    raw: list[str] = []
    if file:
        text = Path(file).read_text()
        for line in text.splitlines():
            line = line.split("#")[0].strip()
            if line:
                raw.extend(p for p in line.split(",") if p.strip())
    for chunk in items or []:
        raw.extend(p for p in chunk.split(",") if p.strip())
    seen, out = set(), []
    for r in raw:
        key = r.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(r.strip())
    return out


def resolve_pool(meta: Meta, names: list[str], evolutions: bool = False,
                 include_megas: bool = True, explain: bool = True,
                 shadows: bool = False) -> tuple[list[Mon], list[str]]:
    """
    Resolve names to Mon objects.

    With `evolutions`, each name also contributes its whole family (and its
    Mega Evolutions), so "eevee" means all eight Eeveelutions and "magneton"
    means Magnemite/Magneton/Magnezone.
    """
    pool, missing, notes = [], [], {}
    for n in names:
        try:
            species = meta.find_species(n)
        except DataError:
            missing.append(n)
            continue
        found = []
        for sid in species:
            if evolutions:
                found.extend(meta.expand_evolutions(sid, include_megas=include_megas,
                                                    include_shadows=shadows))
            elif sid in meta.rankings:
                found.append(sid)
        found = [f for f in dict.fromkeys(found) if f in meta.rankings]
        if not found:
            missing.append(f"{n} (no ranked form in {meta.cup}/{meta.cp})")
            continue
        for sid in found:
            mon = meta.rankings[sid]
            if mon not in pool:
                pool.append(mon)
        if len(found) > 1 or found[0] != species[0]:
            notes[n] = [meta.rankings[sid].name for sid in found]
    if explain and notes:
        print("evolutions considered:", file=sys.stderr)
        for n, forms in notes.items():
            print(f"  {n} -> {', '.join(forms)}", file=sys.stderr)
    return pool, missing


def apply_cup_rules(meta: Meta, pool: list[Mon], allow_megas: bool) -> tuple[list[Mon], list[str]]:
    """Apply mythical ban + optional mega ban (Mega Catch Cup allows megas)."""
    kept, dropped = [], []
    for mon in pool:
        data = meta._pokemon.get(mon.species_id) or {}
        tags = set(data.get("tags") or ())
        if "mythical" in tags:
            dropped.append(f"{mon.name} (mythical)")
            continue
        if not allow_megas and ("mega" in tags or "_mega" in mon.species_id):
            dropped.append(f"{mon.name} (mega evolution)")
            continue
        kept.append(mon)
    return kept, dropped


def legality_warnings(meta: Meta, pool: list[Mon]) -> list[str]:
    """Cup filters are advisory here: PvPoke's JSON is the source of truth."""
    if meta.cup == "all":
        return []
    return [f"{m.name} may not be legal in {meta.cup}" for m in pool if not meta.cup_legality(m)]


def fmt_team(r, meta) -> str:
    lead, switch, closer = r.ordered()
    return f"{lead.name} / {switch.name} / {closer.name}"


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_teambuild(args) -> int:
    meta = build_meta(args)
    names = parse_list(args.mons, args.file)
    if not names:
        print("Give me some Pokemon: --mons \"Azumarill, Skarmory\" or --file mons.txt", file=sys.stderr)
        return 2

    pool, missing = resolve_pool(meta, names, evolutions=args.evolutions,
                                 include_megas=not args.no_megas, shadows=args.shadows)
    pool, illegal = apply_cup_rules(meta, pool, allow_megas=not args.no_megas)
    if missing:
        print(f"[!] not found in {args.league}/{meta.cup} rankings: {', '.join(missing)}", file=sys.stderr)
    if illegal:
        print(f"[!] excluded by cup rules: {', '.join(illegal)}", file=sys.stderr)
    if len(pool) < 3:
        print("Need at least 3 usable Pokemon.", file=sys.stderr)
        return 2

    if args.max_megas is None:
        args.max_megas = 1 if meta.cup == "mega" else None
    size = meta.scorecard_size_for_elo(args.elo)
    scorecard = args.scorecard or size
    threats_top = meta.threats_for(scorecard)
    engine_info = wire_engine(meta, args, [m.species_id for m in pool] + [t.species_id for t in threats_top])
    evaluator = TeamEvaluator(meta, scorecard_size=scorecard, threat_list=threats_top)

    print(f"\n=== {args.league.title()} League / {meta.cup} (CP {meta.cp}) ===")
    print(f"pool: {len(pool)} Pokemon | scorecard: {len(threats_top)} meta threats "
          f"| elo {args.elo or 'unset'} -> scorecard {size}")
    print(f"matchups: {engine_info}")
    if meta.cup in ("mega", "catch"):
        print("[i] Catch Cup legality depends on when you caught each Pokemon "
              "(this season only) — that is assumed, not checked.")

    result = search_teams(
        meta, pool,
        top_k=args.top,
        scorecard_size=scorecard,
        threat_list=threats_top,
        max_exhaustive=args.max_exhaustive,
        dedupe_core=args.diverse,
        max_megas=args.max_megas,
    )

    if result.pruned:
        print(f"[i] too many combinations -- pre-filtered to the {len(result.pool)} best of your mons "
              f"({result.evaluated} teams simulated). Use --max-exhaustive to widen.")

    greedy = evaluator.greedy_build(pool, max_megas=args.max_megas)
    greedy_ranking = evaluator.evaluate(greedy)

    print("\n--- Step 1-3: greedy build (the post's manual loop) ---")
    print(describe_team(greedy_ranking, meta, evaluator, detail=args.detail))

    print(f"\n--- Best {len(result.rankings)} of {result.evaluated} legal combinations ---")
    print("    ranked by PvPoke's coverage metric, then by scorecard pass rate:")
    print(f"\n    {'#':<3}{'coverage':>9}{'answers':>9}{'grade':>7}  team  (lead / swap / closer)")
    for i, r in enumerate(result.rankings, 1):
        print(f"    {i:<3}{r.score:>9.0f}{r.coverage_pct:>8.0f}%{r.grade:>7}  "
              f"{' / '.join(m.name for m in r.ordered())}")
    for i, r in enumerate(result.rankings, 1):
        print(f"\n#{i}")
        print(describe_team(r, meta, evaluator, detail=args.detail))

    if args.names:
        print("\n--- evolution pool used ---")
        for mon in sorted(pool, key=lambda x: (x.rank)):
            print(f"  #{mon.rank:<4} {mon.name:<26} {'/'.join(mon.types):<16} "
                  f"{', '.join(mon.move_names())}")

    if args.html:
        from .report import render
        out = Path(args.html)
        out.write_text(render(meta, result.rankings, evaluator, args.league,
                              [m.name for m in pool], args.elo, engine_info, greedy_ranking))
        print(f"\n[wrote {out}]  open it in a browser for the full scorecards")

    if args.json:
        payload = {
            "league": args.league,
            "cup": meta.cup,
            "cp": meta.cp,
            "elo": args.elo,
            "scorecard": scorecard,
            "threats": [t.name for t in threats_top],
            "greedy": greedy_ranking.to_dict(meta),
            "teams": [r.to_dict(meta) for r in result.rankings],
        }
        out = Path(args.json)
        out.write_text(json.dumps(payload, indent=2))
        print(f"\n[wrote {out}]")

    print("\nOpen in PvPoke:", meta.team_builder_link(result.rankings[0].mons) if result.rankings else "-")
    return 0


def cmd_threats(args) -> int:
    meta = build_meta(args)
    n = args.scorecard or meta.scorecard_size_for_elo(args.elo)
    meta.threats_for(n)  # ensures the meta group is resolved
    print(f"top {n} {args.league}/{meta.cup} threats (PvPoke '{meta._meta_group_name}' meta group):\n")
    for i, m in enumerate(meta.threats_for(n), 1):
        print(f"{i:3d}. {m.name:<28} {m.overall:5.1f}  {'/'.join(m.types):<14} {m.role}")
    return 0


def cmd_rate(args) -> int:
    meta = build_meta(args)
    names = parse_list(args.mons, args.file)
    pool, missing = resolve_pool(meta, names, evolutions=False)
    if missing:
        print(f"[!] skipped: {', '.join(missing)}", file=sys.stderr)
    if len(pool) != 3:
        print(f"Rating expects exactly 3 Pokemon, got {len(pool)}.", file=sys.stderr)
        return 2
    scorecard = args.scorecard or meta.scorecard_size_for_elo(args.elo)
    wire_engine(meta, args, [m.species_id for m in pool] + [t.species_id for t in meta.threats_for(scorecard)])
    ev = TeamEvaluator(meta, threat_list=meta.threats_for(scorecard))
    r = ev.evaluate(pool)
    print(describe_team(r, meta, ev, show_threats=10, detail=True))
    print("\nper-threat, best rating from your team (500 = even, >500 you win):")
    ranked_threats = sorted(ev.threats, key=lambda t: r.per_threat[t.species_id]["best"])
    for t in ranked_threats:
        d = r.per_threat[t.species_id]
        per = " ".join(f"{m.name[:14]}={d['ratings'][m.species_id]:.0f}" for m in pool)
        print(f"  {t.name:<26} best {d['best']:5.0f}  answers {d['answers']}/3  [{per}]")
    return 0


def cmd_alternatives(args) -> int:
    """Step 3 of the post: best next pick for a partial team, from your pool."""
    meta = build_meta(args)
    names = parse_list(args.mons, args.file)
    pool, missing = resolve_pool(meta, names, evolutions=args.evolutions,
                                 include_megas=not args.no_megas, explain=False)
    pool, illegal = apply_cup_rules(meta, pool, allow_megas=not args.no_megas)
    if missing:
        print(f"[!] skipped: {', '.join(missing)}", file=sys.stderr)
    if illegal:
        print(f"[!] excluded by cup rules: {', '.join(illegal)}", file=sys.stderr)
    scorecard = args.scorecard or meta.scorecard_size_for_elo(args.elo)
    wire_engine(meta, args, [m.species_id for m in pool] + [t.species_id for t in meta.threats_for(scorecard)])
    ev = TeamEvaluator(meta, threat_list=meta.threats_for(scorecard))

    base = pool[: args.have]
    if len(base) < args.have:
        print(f"I need {args.have} starting Pokemon.", file=sys.stderr)
        return 2
    rest = [m for m in pool if m not in base]
    print(f"current: {' / '.join(m.name for m in base)}  -> score {ev.evaluate(base).score:.1f}\n")
    scored = sorted(((ev.evaluate(base + [c]).score, c) for c in rest), reverse=True)
    for score, c in scored[: args.top]:
        team = ev.evaluate(base + [c])
        print(f"+ {c.name:<26} {score:6.1f}  {team.grade}   ({c.role}, overall {c.overall:.0f})")
    return 0


def _cmd_validate(args) -> int:
    from .validate import check
    ok = True
    for league in (args.league or ["great", "ultra"]):
        exact, total, _ = check(league, args.n, args.cup)
        ok = ok and total > 0 and exact == total
    print("\nOK - the simulator reproduces PvPoke exactly." if ok else "\nMISMATCH - see above.")
    return 0 if ok else 1


def cmd_cups(args) -> int:
    """List cup/CP combinations PvPoke publishes rankings for."""
    import urllib.error
    import urllib.request

    meta = build_meta(args)
    seen = set()
    print(f"{'cup':<20} {'cp':>6}  {'ranked mons':>11}")
    for fmt in meta.gm["formats"]:
        cup, cp = fmt.get("cup"), fmt.get("cp")
        if not cup or not cp or (cup, cp) in seen:
            continue
        seen.add((cup, cp))
        url = f"https://pvpoke.com/data/rankings/{cup}/overall/rankings-{cp}.json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "pvp-team-builder/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                n = len(json.loads(resp.read()))
            print(f"{cup:<20} {cp:>6}  {n:>11}")
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
            print(f"{cup:<20} {cp:>6}  {'not published':>11}")
    return 0


def cmd_info(args) -> int:
    meta = build_meta(args)
    for n in parse_list(args.mons, args.file):
        m = meta.try_get(n)
        if m is None:
            print(f"{n}: not found / not ranked")
            continue
        print(f"\n{m.name} (#{m.rank} overall, score {m.overall:.1f}, {m.role})")
        print(f"  types  : {'/'.join(m.types)}")
        print(f"  stats  : atk {m.stats['atk']} def {m.stats['def']} hp {m.stats['hp']} "
              f"(product {m.stats['product']})")
        print(f"  moveset: {', '.join(m.move_names())}")
        print("  scores : " + ", ".join(f"{k} {v:.0f}" for k, v in m.scores.items()))
        if m.scorecard:
            best = sorted(m.scorecard.items(), key=lambda kv: -kv[1])[:4]
            worst = sorted(m.scorecard.items(), key=lambda kv: kv[1])[:4]
            def name(species_id: str) -> str:
                return meta.rankings[species_id].name if species_id in meta.rankings else species_id

            def tag(rating: float) -> str:
                return "W" if rating > 500 else "L"
            print("  best   : " + ", ".join(f"{name(s)} {v:.0f}{tag(v)}" for s, v in best))
            print("  worst  : " + ", ".join(f"{name(s)} {v:.0f}{tag(v)}" for s, v in worst))
        if m.notes:
            print(f"  notes  : {m.notes[:200]}")
    return 0


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pvp-team-builder",
        description="Automate r/TheSilphArena's 'How to build a decent team in 5 minutes'.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--data-dir", default=None, help="where to cache PvPoke JSON (default: package data/)")
    p.add_argument("--refresh", action="store_true", help="re-download PvPoke data")
    p.add_argument("--offline", action="store_true", help="never hit the network")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("-l", "--league", default="great", choices=sorted(LEAGUE_CP))
        sp.add_argument("-c", "--cup", default="all",
                        help="cup slug or friendly name, e.g. 'all', 'mega' / 'mega catch cup', 'little', 'willpower'")
        sp.add_argument("--evolutions", action="store_true",
                        help="expand every Pokemon to its whole evolution family (eevee -> all Eeveelutions)")
        sp.add_argument("--no-megas", action="store_true", help="exclude Mega Evolutions from the pool")
        sp.add_argument("--shadows", action="store_true",
                        help="also consider Shadow forms of every evolution (off by default)")
        sp.add_argument("--elo", type=int, default=None, help="your rating; sets scorecard length like the post")
        sp.add_argument("--scorecard", type=int, default=None, help="override scorecard length (post: 30)")
        sp.add_argument("--meta-size", type=int, default=30, help="how many mons count as 'meta' for weighting")
        sp.add_argument("--engine", default="pvpoke", choices=["pvpoke", "simple"],
                        help="pvpoke = exact numbers via PvPoke's own simulator (needs Node); "
                             "simple = fast typing/stat estimates")
        sp.add_argument("--mons", action="append", help="comma separated Pokemon list, repeatable")
        sp.add_argument("--file", help="text file with one Pokemon per line (or comma separated)")
        return sp

    sp = common(sub.add_parser("teambuild", help="rank teams from your collection"))
    sp.add_argument("--top", type=int, default=5)
    sp.add_argument("--max-exhaustive", type=int, default=25000,
                    help="evaluate every combination up to this many, else pre-filter the box")
    sp.add_argument("--names", action="store_true",
                    help="print the resolved evolution pool (every mon considered) at the end")
    sp.add_argument("--diverse", action="store_true",
                    help="spread results across different cores instead of pure score order")
    sp.add_argument("--max-megas", type=int, default=None,
                    help="max Mega Evolutions per team (default: 1 in a Mega-enabled cup, else no limit)")
    sp.add_argument("--json", help="also write results to this JSON file")
    sp.add_argument("--html", help="write a self-contained HTML report to this file")
    sp.add_argument("--detail", action="store_true", help="print the full per-threat scorecard")
    sp.set_defaults(func=cmd_teambuild)

    sp = common(sub.add_parser("rate", help="score one specific team of 3"))
    sp.set_defaults(func=cmd_rate)

    sp = common(sub.add_parser("alternatives", help="best next pick for a 1-2 mon core (post step 3)"))
    sp.add_argument("--have", type=int, default=1, help="how many of the listed mons are the current core")
    sp.add_argument("--top", type=int, default=8)
    sp.set_defaults(func=cmd_alternatives)

    sp = common(sub.add_parser("threats", help="see the meta/threat list used"))
    sp.set_defaults(func=cmd_threats)

    sp = sub.add_parser("validate", help="prove the simulator matches PvPoke's published ratings")
    sp.add_argument("-l", "--league", action="append", choices=["great", "ultra", "master", "little"])
    sp.add_argument("-c", "--cup", default="all")
    sp.add_argument("--n", type=int, default=40)
    sp.add_argument("--data-dir", default=None)
    sp.add_argument("--refresh", action="store_true")
    sp.add_argument("--offline", action="store_true")
    sp.set_defaults(func=_cmd_validate)

    sp = common(sub.add_parser("cups", help="list cups/CP caps with published rankings"))
    sp.set_defaults(func=cmd_cups)

    sp = common(sub.add_parser("info", help="show a Pokemon's data"))
    sp.set_defaults(func=cmd_info)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except DataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
