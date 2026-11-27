"""
PvPoke data layer.

Loads the gamemaster and per-league rankings into Mon objects: base stats,
published movesets, role scores, and the matchups PvPoke publishes. Handles
species name resolution (Shadow and regional forms included), evolution
families, cup legality and the on-disk cache.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def default_data_dir() -> Path:
    """
    Cache directory for PvPoke's JSON, about 30 MB once populated.

    Kept outside the working tree so it never lands in a commit or in
    `git status`. $PVP_TEAM_BUILDER_DATA wins, then $XDG_CACHE_HOME,
    then ~/.cache. `--data-dir` overrides all three.
    """
    env = os.environ.get("PVP_TEAM_BUILDER_DATA")
    if env:
        return Path(env).expanduser()
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "pvp-team-builder"


DEFAULT_DATA_DIR = default_data_dir()

MIRRORS = (
    "https://pvpoke.com/data/{rel}",
    "https://raw.githubusercontent.com/pvpoke/pvpoke/master/src/data/{rel}",
)

# PvPoke's ranking scenarios (see gamemaster.json["rankingScenarios"]).
RANKING_SLUGS = ("overall", "leads", "switches", "closers", "chargers", "attackers", "consistency")

LEAGUE_CP = {
    "great": 1500,
    "ultra": 2500,
    "master": 10000,
    "little": 500,
}

# Cups that are published under their own CP cap regardless of the league flag.
CUP_CP = {"little": 500, "littlegeneral": 500}

# Friendly names -> PvPoke cup slug.  PvPoke uses one "mega" ranking set for all
# Mega-enabled Great League formats (Great League: Mega Edition, Mega Catch Cup,
# Mega Halloween/Color Cup), so those all resolve to it.
CUP_ALIASES = {
    "mega catch cup": "mega",
    "mega catch cup great league edition": "mega",
    "catch cup mega": "mega",
    "great league mega edition": "mega",
    "mega great league": "mega",
    "gl mega": "mega",
    "great": "all",
    "great league": "all",
    "open great league": "all",
    "ogl": "all",
    "ultra league": "all",
    "master league": "all",
    "catch cup": "catch",
    "great league catch cup": "catch",
}

# Stat multipliers, level 1 -> 51 in half steps (index = 2*level - 2).
CPM: list[float] = json.loads((HERE / "cpm.json").read_text())

# Gen 6+ effectiveness in GO: super effective 1.6, resisted 0.625, "immune" 0.390625.
SE, NVE, IMMUNE = 1.6, 0.625, 0.390625

# Attacking type -> (super effective on, not very effective on, immune to)
TYPE_CHART: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "normal":   ((), ("rock", "steel"), ("ghost",)),
    "fighting": (("normal", "rock", "steel", "ice", "dark"), ("flying", "poison", "bug", "psychic", "fairy"), ("ghost",)),
    "flying":   (("fighting", "bug", "grass"), ("rock", "steel", "electric"), ()),
    "poison":   (("grass", "fairy"), ("poison", "ground", "rock", "ghost"), ("steel",)),
    "ground":   (("poison", "rock", "steel", "fire", "electric"), ("bug", "grass"), ("flying",)),
    "rock":     (("flying", "bug", "fire", "ice"), ("fighting", "ground", "steel"), ()),
    "bug":      (("grass", "psychic", "dark"), ("fighting", "flying", "poison", "ghost", "steel", "fire", "fairy"), ()),
    "ghost":    (("ghost", "psychic"), ("dark",), ("normal",)),
    "steel":    (("ice", "rock", "fairy"), ("steel", "fire", "water", "electric"), ()),
    "fire":     (("bug", "steel", "grass", "ice"), ("rock", "fire", "water", "dragon"), ()),
    "water":    (("ground", "rock", "fire"), ("water", "grass", "dragon"), ()),
    "grass":    (("ground", "rock", "water"), ("flying", "poison", "bug", "steel", "fire", "grass", "dragon"), ()),
    "electric": (("flying", "water"), ("grass", "electric", "dragon"), ("ground",)),
    "psychic":  (("fighting", "poison"), ("steel", "psychic"), ("dark",)),
    "ice":      (("flying", "ground", "grass", "dragon"), ("steel", "fire", "water", "ice"), ()),
    "dragon":   (("dragon",), ("steel",), ("fairy",)),
    "dark":     (("ghost", "psychic"), ("fighting", "dark", "fairy"), ()),
    "fairy":    (("fighting", "dragon", "dark"), ("poison", "steel", "fire"), ()),
}

_ALL_TYPES = tuple(TYPE_CHART)


def type_multiplier(attack_type: str, defender_types: Sequence[str]) -> float:
    """Damage multiplier of `attack_type` against a defender with `defender_types`."""
    se, nve, imm = TYPE_CHART[attack_type]
    mult = 1.0
    for t in defender_types:
        if t in se:
            mult *= SE
        elif t in nve:
            mult *= NVE
        elif t in imm:
            mult *= IMMUNE
    return round(mult, 6)


def move_multiplier(attack_types: Iterable[str], defender_types: Sequence[str]) -> float:
    """Best multiplier the attacker can reach with the given move types."""
    return max((type_multiplier(t, defender_types) for t in attack_types), default=1.0)


def stats_at(base: dict[str, int], level: float, ivs: Sequence[int] = (15, 15, 15)) -> dict[str, float]:
    """Effective Attack/Def/HP and CP for a species at a level (PvPoke formula)."""
    cpm = CPM[min(max(int(round(level * 2)) - 2, 0), len(CPM) - 1)]
    atk = (base["atk"] + ivs[0]) * cpm
    df = (base["def"] + ivs[1]) * cpm
    hp = int((base["hp"] + ivs[2]) * cpm)
    cp = max(10, int(atk * (df ** 0.5) * (hp ** 0.5) / 10))
    return {"atk": round(atk, 1), "def": round(df, 1), "hp": hp, "cp": cp,
            "product": round(atk * df * hp / 1000)}


class DataError(RuntimeError):
    pass


# Download / cache
class Store:
    """Local cache of PvPoke JSON files."""

    def __init__(self, data_dir: str | Path | None = None, refresh: bool = False,
                 offline: bool = False, max_age_days: float = 7.0, quiet: bool = False):
        self.dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self.refresh = refresh
        self.offline = offline
        self.max_age = max_age_days * 86400
        self.quiet = quiet

    def _log(self, msg: str) -> None:
        if not self.quiet:
            print(f"[data] {msg}", file=sys.stderr)

    def file(self, name: str) -> Path:
        return self.dir / name

    def _stale(self, path: Path) -> bool:
        return self.refresh or not path.exists() or (time.time() - path.stat().st_mtime) > self.max_age

    def get(self, rel: str, local_name: str | None = None, required: bool = True) -> Any | None:
        """Return parsed JSON for a PvPoke `rel` path, downloading if needed."""
        name = local_name or rel.replace("/", "_")
        path = self.file(name)
        if self._stale(path):
            if self.offline:
                if not path.exists() and required:
                    raise DataError(f"offline mode and {name} is not cached in {self.dir}")
            else:
                last_err: Exception | None = None
                for pattern in MIRRORS:
                    url = pattern.format(rel=rel)
                    try:
                        self._log(f"fetching {url}")
                        req = urllib.request.Request(url, headers={"User-Agent": "pvp-team-builder/1.0"})
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            payload = resp.read()
                        json.loads(payload)  # validate before writing
                        path.write_bytes(payload)
                        last_err = None
                        break
                    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                        last_err = exc
                if last_err is not None:
                    if path.exists():
                        self._log(f"could not refresh {name} ({last_err}); using cached copy")
                    elif required:
                        raise DataError(f"could not download {rel}: {last_err}") from last_err
                    else:
                        return None
        if not path.exists():
            if required:
                raise DataError(f"{name} missing from {self.dir}")
            return None
        return json.loads(path.read_text())


# Core model
@dataclass(frozen=True, eq=False)
class Mon:
    """A species as it appears in one league's rankings."""

    species_id: str
    name: str
    types: tuple[str, ...]
    stats: dict[str, float]
    moveset: tuple[str, ...]              # e.g. ("COUNTER", "ROCK_SLIDE", "CLOSE_COMBAT")
    move_types: tuple[str, ...]           # types of the damaging moves in the moveset
    overall: float
    scores: dict[str, float] = field(default_factory=dict, compare=False)
    scorecard: dict[str, float] = field(default_factory=dict)   # opponent -> rating (0-1000)
    rank: int = 0
    notes: str = ""


    # Convenience
    @property
    def role(self) -> str:
        """Dominant PvPoke role, for display only."""
        pairs = [("lead", self.scores.get("leads", 0)),
                 ("switch", self.scores.get("switches", 0)),
                 ("closer", self.scores.get("closers", 0))]
        return max(pairs, key=lambda p: p[1])[0]

    def move_names(self) -> tuple[str, ...]:
        return tuple(_pretty_move(m) for m in self.moveset)

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.name

    def __repr__(self) -> str:  # pragma: no cover
        return f"Mon({self.name})"


def _pretty_move(move_id: str) -> str:
    return " ".join(w.capitalize() for w in move_id.split("_"))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


FORM_ALIASES = {
    "g": "galarian", "a": "alolan", "h": "hisuian", "p": "paldean", "u": "unova",
    "galar": "galarian", "alola": "alolan", "hisui": "hisuian", "paldea": "paldean",
}
# every long form that can appear as a word: "galarian weezing", "weezing galarian"
FORM_WORDS = set(FORM_ALIASES.values()) | {"alolan", "galarian", "hisuian", "paldean", "unovan"}


class Meta:
    """One league and cup view over PvPoke's data: rankings, lookups, matchups."""

    def __init__(self, league: str = "great", cup: str = "all", data_dir: str | Path | None = None,
                 refresh: bool = False, offline: bool = False, quiet: bool = False):
        if league not in LEAGUE_CP:
            raise DataError(f"unknown league {league!r}; pick one of {sorted(LEAGUE_CP)}")
        self.league = league
        self.cup = CUP_ALIASES.get(_norm(cup), cup)
        self.cp = CUP_CP.get(cup, LEAGUE_CP[league])
        self.store = Store(data_dir, refresh=refresh, offline=offline, quiet=quiet)

        gm = self.store.get("gamemaster.json")
        self.gm = gm
        self._pokemon = {p["speciesId"]: p for p in gm["pokemon"]}
        self._moves = {m["moveId"]: m for m in gm["moves"]}
        self._cups = {c["name"]: c for c in gm["cups"]}
        self._alias = self._build_alias_index()

        # rankings: overall decides the order, the rest fill role scores
        self.rankings: dict[str, Mon] = {}
        self.order: list[str] = []
        self.estimated_pairs: set[tuple[str, str]] = set()
        self._matchups = None       # set by engine.MatchupMatrix.attach()
        self._meta_group_name = ""
        for slug in RANKING_SLUGS:
            self._load_ranking_slug(slug)


    # Loading
    def _load_ranking_slug(self, slug: str) -> None:
        rel = f"rankings/{self.cup}/{slug}/rankings-{self.cp}.json"
        rows = self.store.get(rel, local_name=f"rankings-{self.cup}-{self.cp}-{slug}.json", required=False)
        if not rows:
            if slug == "overall":
                raise DataError(
                    f"no rankings for cup={self.cup!r} league={self.league!r} (tried {rel}). "
                    f"Cups are published per CP cap; try --cup all, or another cup. "
                    f"Run `python -m pvp_team_builder cups` to list what exists."
                )
            return  # optional role side-tables
        for rank, row in enumerate(rows, start=1):
            sid = row["speciesId"]
            if slug == "overall":
                mon = self._make_mon(row, rank)
                self.rankings[sid] = mon
                self.order.append(sid)
                for m in row.get("matchups", []):
                    mon.scorecard[m["opponent"]] = float(m["rating"])
            else:
                key = {"leads": "leads", "switches": "switches", "closers": "closers",
                       "chargers": "chargers", "attackers": "attackers", "consistency": "consistency"}[slug]
                mon = self.rankings.get(sid)
                if mon is not None:
                    mon.scores[key] = float(row.get("score", 0))
                    mon.scores.setdefault("leads", 0.0)

    def _make_mon(self, row: dict, rank: int) -> Mon:
        sid = row["speciesId"]
        base = self._pokemon.get(sid, {})
        ivs = (base.get("defaultIVs") or {}).get(f"cp{self.cp}")
        if row.get("stats") and "atk" in row["stats"]:
            stats = dict(row["stats"])
        elif base and ivs:
            lvl, a, d, h = ivs
            stats = stats_at(base["baseStats"], lvl, (a, d, h))
        else:
            stats = {"atk": 0.0, "def": 0.0, "hp": 0.0, "product": 0}
        moveset = tuple(row.get("moveset") or ())
        move_types = tuple(sorted({self._moves[m]["type"] for m in moveset if m in self._moves}))
        scores = {"overall": float(row.get("score", 0))}
        return Mon(
            species_id=sid,
            name=row.get("speciesName", sid),
            types=tuple(t for t in (base.get("types") or row.get("types") or ()) if t and t != "none"),
            stats=stats,
            moveset=moveset,
            move_types=move_types,
            scores=scores,
            scorecard={},
            overall=float(row.get("score", 0)),
            rank=rank,
            notes=(row.get("editorNotes") or "")[:400],
        )

    def _build_alias_index(self) -> dict[str, str]:
        idx: dict[str, str] = {}
        for sid, p in self._pokemon.items():
            idx.setdefault(_norm(sid), sid)
            if p.get("speciesName"):
                idx.setdefault(_norm(p["speciesName"]), sid)
        return idx


    # Lookup
    def get(self, key: str) -> Mon:
        sid = self.resolve(key)
        if sid not in self.rankings:
            raise DataError(
                f"{key!r} resolves to {sid!r}, which is not in the {self.league}/{self.cup} rankings "
                f"(not eligible or not ranked here). Try another league/cup."
            )
        return self.rankings[sid]

    def try_get(self, key: str) -> Mon | None:
        try:
            return self.get(key)
        except DataError:
            return None

    def resolve(self, key: str) -> str:
        """Map a user string ('Shadow Drapion', 'g-weezing', 'azumarill') to a speciesId."""
        raw = key.strip()
        candidates = [raw, raw.replace(" ", "_"), raw.replace(" ", "_").lower(), raw.lower()]
        for c in candidates:
            if c in self._pokemon:
                return c
            if _norm(c) in self._alias:
                return self._alias[_norm(c)]

        low = _norm(raw)
        # shadow handling: "shadow drapion" / "drapion shadow" / "shadow-drapion"
        shadow = False
        if low.startswith("shadow "):
            shadow, low = True, low[len("shadow "):]
        elif low.endswith(" shadow"):
            shadow, low = True, low[: -len(" shadow")]
        # form handling: "g weezing" / "galarian weezing" / "weezing galarian"
        parts = low.split()
        form = None
        if len(parts) > 1 and (parts[0] in FORM_ALIASES or parts[0] in FORM_WORDS):
            form = FORM_ALIASES.get(parts[0], parts[0])
            parts = parts[1:]
        elif len(parts) > 1 and (parts[-1] in FORM_ALIASES or parts[-1] in FORM_WORDS):
            form = FORM_ALIASES.get(parts[-1], parts[-1])
            parts = parts[:-1]
        base = " ".join(parts)
        tries = []
        if form:
            tries += [f"{base}_{form}", f"{base} {form}"]
        tries.append(base)
        if shadow:
            tries = [f"{t}_shadow" for t in tries] + tries
        for t in tries:
            if base and _norm(t) in self._alias:
                return self._alias[_norm(t)]
        for t in tries:
            if t.replace(" ", "_") in self._pokemon:
                return t.replace(" ", "_")

        close = difflib.get_close_matches(base or raw, list(self._alias), n=3, cutoff=0.72)
        hint = ", ".join(self._alias[c] for c in close)
        raise DataError(f"unknown Pokemon {key!r}" + (f"; did you mean: {hint}?" if hint else ""))


    # Families / evolutions
    def family_chain(self, species_id: str, include_shadows: bool = False) -> list[str]:
        """Species in the same evolution family, ancestors first."""
        data = self._pokemon.get(species_id)
        if not data or not data.get("family"):
            return [species_id]
        fam_id = data["family"]["id"]
        members = [sid for sid, p in self._pokemon.items()
                   if (p.get("family") or {}).get("id") == fam_id]
        # order: walk up to the root, then down
        root = species_id
        seen = set()
        while True:
            parent = (self._pokemon.get(root, {}).get("family") or {}).get("parent")
            if not parent or parent in seen or parent not in self._pokemon:
                break
            seen.add(parent)
            root = parent
        order, queue = [], [root]
        while queue:
            sid = queue.pop(0)
            if sid in order:
                continue
            order.append(sid)
            queue.extend((self._pokemon.get(sid, {}).get("family") or {}).get("evolutions") or [])
        out = [m for m in order if m in members]
        for m in members:                      # forms missing from the tree
            if m not in out:
                out.append(m)
        # A Shadow form is a variant of an existing member, not an extra one.
        if not include_shadows:
            out = [m for m in out if not m.endswith("_shadow")]
        return out or [species_id]

    def _is_mega(self, species_id: str) -> bool:
        data = self._pokemon.get(species_id) or {}
        return "mega" in (data.get("tags") or []) or "_mega" in species_id

    def expand_evolutions(self, species_id: str, include_megas: bool = True,
                          keep_base: bool = True, include_shadows: bool = False) -> list[str]:
        """Ranked members of this evolution family, optionally including Megas."""
        ids = []
        for sid in self.family_chain(species_id):
            ids.append(sid)
            if include_shadows and f"{sid}_shadow" in self._pokemon:
                ids.append(f"{sid}_shadow")
            if include_megas:
                ids.extend(sorted(m for m in self._pokemon if m.startswith(sid + "_mega")))
        if not keep_base:
            ids = [i for i in ids if i != species_id]
        out = []
        for sid in ids:
            if not sid or sid not in self.rankings:
                continue
            if not include_megas and self._is_mega(sid):
                continue
            mon = self.rankings[sid]
            if not self.cup_legality(mon):
                continue
            out.append(sid)
        return list(dict.fromkeys(out))

    def find_species(self, name: str) -> list[str]:
        """Resolve a user string to every species it could mean, ranked first."""
        try:
            base = self.resolve(name)
            return [base]
        except DataError:
            pass
        low = _norm(name)
        hits = [sid for sid in self._pokemon if low and low in _norm(sid)]
        hits.sort(key=lambda s: (len(s), s))
        if not hits:
            raise DataError(f"unknown Pokemon {name!r}")
        return hits

    def cup_rules(self) -> dict:
        """Human-readable summary of the current cup's restrictions."""
        cup = self._cups.get(self.cup) or {}
        rules = {"cup": self.cup, "title": cup.get("title", self.cup), "cp": self.cp,
                 "include": [], "exclude": []}
        for side in ("include", "exclude"):
            for f in cup.get(side) or []:
                if f.get("values"):
                    rules[side].append(f"{f['filterType']}: {', '.join(f['values'][:8])}"
                                       + (" ..." if len(f["values"]) > 8 else ""))
        return rules


    # Matchup matrix
    def matchup(self, a: Mon, b: Mon) -> float:
        """
        Rating of `a` against `b`, 0-1000, 500 even.

        PvPoke's published number if the pair appears in `a`'s scorecard, else
        the simulated matrix, else a type and stat estimate. Ratings are
        directional, so `a` vs `b` and `b` vs `a` are separate values.
        """
        if b.species_id in a.scorecard:
            return a.scorecard[b.species_id]

        matrix = self._matchups
        if matrix is not None:
            value = matrix.rating(a.species_id, b.species_id)
            if value is not None:
                return float(value)

        if a.species_id in b.scorecard:
            # only an inverse is known; PvPoke ratings are not symmetric
            return 1000.0 - b.scorecard[a.species_id]

        self.estimated_pairs.add((a.species_id, b.species_id))
        return self._estimate(a, b)

    def _estimate(self, a: Mon, b: Mon) -> float:
        """Cheap surrogate: typing dominance + bulk/power offset around 500."""
        off = move_multiplier(a.move_types, b.types) if a.move_types else 1.0
        dfn = move_multiplier(b.move_types, a.types) if b.move_types else 1.0
        type_edge = (off - dfn)                                   # -2.2 .. +2.2 typical
        # relative bulk and power, log-ish and clamped
        bulk_a = (a.stats["def"] * a.stats["hp"]) ** 0.5
        bulk_b = (b.stats["def"] * b.stats["hp"]) ** 0.5
        atk_a, atk_b = a.stats["atk"], b.stats["atk"]
        bulk_edge = (bulk_a / max(bulk_a + bulk_b, 1e-9)) - 0.5    # -0.5..0.5
        atk_edge = (atk_a / max(atk_a + atk_b, 1e-9)) - 0.5
        raw = 500 + 150 * type_edge + 400 * bulk_edge + 260 * atk_edge
        return float(min(1000, max(0, round(raw))))


    # Views
    def load_group(self, name: str) -> list[str]:
        """Species ids of a PvPoke ranking group (e.g. 'great', 'megagreat')."""
        rows = self.store.get(f"groups/{name}.json", local_name=f"group-{name}.json", required=False)
        return [r["speciesId"] for r in (rows or []) if r.get("speciesId")]

    def tracked_species(self, limit: int = 6, elo: int | None = None) -> list[str]:
        """Top `limit` of the format's meta group, one per evolution family."""
        group = self.meta_group()
        originals = [g.replace("_shadow", "") for g in group]
        ordered = [sid for sid in self.order if sid.replace("_shadow", "") in originals]
        if not ordered:
            ordered = self.order
        out, seen_family = [], set()
        for sid in ordered:
            fam = (self._pokemon.get(sid, {}).get("family") or {}).get("id", sid)
            if fam in seen_family:
                continue
            seen_family.add(fam)
            out.append(sid)
            if len(out) >= limit:
                break
        return out

    def threats_for(self, n: int) -> list[Mon]:
        """
        The `n` threats to grade against: the format's own meta group (for
        example 'megagreat'), ordered by overall ranking, topped up from the
        plain rankings when the group is smaller than `n`.
        """
        group = set(self.meta_group())
        picked = [sid for sid in self.order if sid in group]
        for sid in self.order:                     # top up if the group is tiny
            if len(picked) >= n:
                break
            if sid not in group and "_mega" not in sid:
                picked.append(sid)
        return [self.rankings[s] for s in picked[:n]]

    def meta_group(self) -> list[str]:
        """PvPoke's meta group for the current format ('megagreat', 'great', ...)."""
        fmt = next((f for f in self.gm["formats"]
                    if f.get("cup") == self.cup and (f.get("cp") == self.cp or self.cup != "all")), None)
        group_name = (fmt or {}).get("meta")
        candidates = [group_name] if group_name else []
        if self.cup == "mega":
            candidates += ["megagreat" if self.cp == 1500 else "mega"]
        candidates += ["great" if self.cp == 1500 else "ultra"]
        for name in candidates:
            if not name:
                continue
            ids = self.load_group(name)
            if ids:
                self._meta_group_name = name
                return ids
        return self.order[:50]

    def ranked(self, n: int | None = None) -> list[Mon]:
        ids = self.order if n is None else self.order[:n]
        return [self.rankings[i] for i in ids]

    def scorecard_size_for_elo(self, elo: int | None) -> int:
        """The post's rule of thumb: deeper scorecard the lower your rating."""
        if elo is None:
            return 25
        if elo < 1900:
            return 30
        if elo < 2400:
            return 25
        return 20

    def team_builder_link(self, mons: Sequence[Mon]) -> str:
        """Deep link that pre-loads the team in PvPoke's team builder."""
        ids = ",".join(m.species_id for m in mons)
        return f"https://pvpoke.com/team-builder/{self.cup}/{self.cp}/{ids}/"

    def _matches_filters(self, mon: Mon, filters: Sequence[dict]) -> bool:
        """PvPoke cup filters are OR-ed within a list."""
        data = self._pokemon.get(mon.species_id) or {}
        for f in filters:
            vals = set(f.get("values") or ())
            if not vals:
                continue
            kind = f.get("filterType")
            if kind == "type" and set(mon.types) & vals:
                return True
            if kind == "id" and mon.species_id in vals:
                return True
            if kind == "move" and set(mon.moveset) & vals:
                return True
            if kind == "tag" and set(data.get("tags") or ()) & vals:
                return True
        return False

    def cup_legality(self, mon: Mon) -> bool:
        """Best-effort check of a mon against the cup's include/exclude filters."""
        if self.cup == "all":
            return True
        cup = self._cups.get(self.cup)
        if not cup:
            return True
        include = cup.get("include") or []
        exclude = cup.get("exclude") or []
        allowed = True if not include else self._matches_filters(mon, include)
        return allowed and not self._matches_filters(mon, exclude)
