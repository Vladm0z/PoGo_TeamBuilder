"""
Checks the simulator against PvPoke.

Re-simulates every matchup PvPoke published in its rankings -- each Pokemon's
five best and five worst results -- and diffs them. A correctly wired bridge
gives zero error.

    pvp-team-builder validate -l great -l ultra --n 40

Exit code 0 means every matchup matched.
"""

from __future__ import annotations

import argparse
import sys

from .engine import EngineUnavailable, MatchupMatrix
from .pvp import Meta


def check(league: str, n: int, cup: str = "all", verbose: bool = True) -> tuple[int, int, int]:
    meta = Meta(league, cup, quiet=True)
    ranked = meta.ranked(n)
    ids = [m.species_id for m in ranked]
    published: dict[tuple[str, str], float] = {}
    for m in ranked:
        for opp, rating in m.scorecard.items():
            if opp in ids:
                published[(m.species_id, opp)] = rating
    if not published:
        return 0, 0, 0

    matrix = MatchupMatrix(meta, ids, refresh=True, quiet=True)   # force fresh sims
    exact = maxerr = 0
    mismatches = []
    for (a, b), expected in published.items():
        got = matrix.rating(a, b)
        if got is None:
            mismatches.append((a, b, expected, None))
            continue
        diff = abs(got - expected)
        maxerr = max(maxerr, diff)
        if diff == 0:
            exact += 1
        elif verbose:
            mismatches.append((a, b, expected, got))

    total = len(published)
    if verbose:
        print(f"\n{league:>6} / {cup}  CP {meta.cp}")
        print(f"  re-simulated {total} published matchups")
        print(f"  exact        {exact}/{total}  ({100 * exact / total:.1f}%)")
        print(f"  max error    {maxerr}")
        if mismatches:
            print("  mismatches:")
            for a, b, exp, got in mismatches[:10]:
                print(f"    {a:22} vs {b:22} published {exp:4.0f}  ours {got}")
    return exact, total, maxerr


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate the engine against PvPoke's published ratings.")
    ap.add_argument("-l", "--league", action="append", choices=["great", "ultra", "master", "little"])
    ap.add_argument("-c", "--cup", default="all")
    ap.add_argument("--n", type=int, default=40, help="how many top-ranked Pokemon to include")
    args = ap.parse_args(argv)

    leagues = args.league or ["great", "ultra"]
    ok = True
    for league in leagues:
        try:
            exact, total, maxerr = check(league, args.n, args.cup)
        except EngineUnavailable as exc:
            print(f"engine unavailable: {exc}", file=sys.stderr)
            return 1
        ok = ok and exact == total and total > 0
    print("\nOK - the simulator reproduces PvPoke exactly." if ok else "\nMISMATCH - see above.")
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
