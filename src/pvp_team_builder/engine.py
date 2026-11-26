"""
Exact matchup matrix, computed by PvPoke's own battle engine via Node.

PvPoke's rankings only publish each Pokemon's top 5 wins and top 5 losses, so
any team search over an arbitrary box needs the full matrix.  Rather than
approximating it, this module runs PvPoke's real code (GameMaster.js,
Pokemon.js, Battle.js, ActionLogic.js, ...) headlessly in a Node vm sandbox —
see `pvpoke_engine/harness.js` — with each Pokemon's *published* moveset.

Validation (`validate.py`): against the ratings PvPoke actually published
(their single-shield 1v1 simulations) this reproduces **100% exactly**
(0 error over 495 pairs in Great and Ultra League).  It is not an
approximation of PvPoke — it is PvPoke.

The matrix is cached in `data/matrix-<cup>-<cp>.json`, so runs after the first
are instant and work offline.  Without Node (or with `--engine simple`) the
tool falls back to fast typing/stat estimates from `pvp.Meta._estimate`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE / "harness.js"          # shipped with the package

ENGINE_FILES = {
    "GameMaster.js": "js/GameMaster.js",
    "Pokemon.js": "js/pokemon/Pokemon.js",
    "Battle.js": "js/battle/Battle.js",
    "DamageCalculator.js": "js/battle/DamageCalculator.js",
    "ActionLogic.js": "js/battle/actions/ActionLogic.js",
    "TimelineEvent.js": "js/battle/timeline/TimelineEvent.js",
    "TimelineAction.js": "js/battle/timeline/TimelineAction.js",
    "DecisionOption.js": "js/training/DecisionOption.js",
}

PVPOKE = "https://pvpoke.com/{rel}?v={version}"
VERSION = "1.40.7.1"

# PvPoke's team builder defaults (js/interface/PokeMultiSelect.js):
#   shields: 1, bait: 1, levelCap: 50, single-shield scoring mode.
MAP_MODE, MAP_SHIELDS = "single", 1


class EngineUnavailable(RuntimeError):
    pass


def node_path() -> str | None:
    return shutil.which("node") or shutil.which("nodejs")


def engine_dir(meta=None) -> Path:
    """Where PvPoke's battle scripts are cached (inside the data dir)."""
    base = Path(meta.store.dir) if meta is not None else HERE.parent.parent / "data"
    return base / "engine"


def engine_ready(directory: Path | None = None) -> bool:
    d = directory or engine_dir()
    return HARNESS.exists() and all((d / n).exists() for n in ENGINE_FILES)


def ensure_engine(directory: Path | None = None, quiet: bool = True) -> Path:
    """Download PvPoke's public battle scripts once, into `directory`."""
    import urllib.request

    d = directory or engine_dir()
    if engine_ready(d):
        return d
    d.mkdir(parents=True, exist_ok=True)
    for local, rel in ENGINE_FILES.items():
        dest = d / local
        if dest.exists():
            continue
        if not quiet:
            print(f"[engine] downloading {rel}", file=sys.stderr)
        req = urllib.request.Request(PVPOKE.format(rel=rel, version=VERSION),
                                     headers={"User-Agent": "pvp-team-builder/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.write_bytes(resp.read())
    return d


def run_pairs(gamemaster: Path, pairs: Sequence[tuple[str, str]], cp: int, cup: str = "all",
              movesets: dict[str, Sequence[str]] | None = None, mode: str = MAP_MODE,
              shields: int = MAP_SHIELDS, timeout: int | None = None,
              directory: Path | None = None) -> dict[tuple[str, str], dict]:
    """Rate pairs with PvPoke's engine. Returns {(a, b): {...}}."""
    node = node_path()
    if node is None:
        raise EngineUnavailable("node not found — install Node.js, or use --engine simple")
    scripts = ensure_engine(directory)
    payload = {
        "gamemaster": str(Path(gamemaster).resolve()),
        "cp": cp,
        "cup": cup,
        "mode": mode,
        "shields": shields,
        "pairs": [list(p) for p in pairs],
        "movesets": {k: list(v) for k, v in (movesets or {}).items()},
        "engine": str(scripts),
    }
    proc = subprocess.run(
        [node, str(HARNESS)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=timeout or max(120, len(pairs) // 100),
    )
    out = proc.stdout.decode().strip()
    if not out:
        raise EngineUnavailable(f"pvpoke engine produced no output: {proc.stderr.decode()[:400]}")
    try:
        rows = json.loads(out)
    except json.JSONDecodeError as exc:
        raise EngineUnavailable(f"bad engine output: {exc}: {out[:300]}") from exc
    return {(r["a"], r["b"]): r for r in rows if "rating" in r}


class MatchupMatrix:
    """
    Lazily-built, disk-cached full matrix for a set of species.

    `rating(a, b)` returns PvPoke's 0-1000 rating (500 = even).  Both
    directions are simulated because turn order means a vs b != 1 - b vs a.
    """

    def __init__(self, meta, species_ids: Iterable[str], refresh: bool = False,
                 quiet: bool = True, allow_download: bool = True):
        self.meta = meta
        self.ids = list(dict.fromkeys(species_ids))
        self.quiet = quiet
        self.cache_file = meta.store.file(f"matrix-{meta.cup}-{meta.cp}.json")
        self.data: dict[tuple[str, str], int] = {}
        self.simulated = 0
        self._load_cache(refresh)
        self._ensure(allow_download)

    # -- cache ------------------------------------------------------------- #
    def _load_cache(self, refresh: bool) -> None:
        if refresh or not self.cache_file.exists():
            return
        try:
            raw = json.loads(self.cache_file.read_text())
            self.data = {tuple(k.split("|")): int(v) for k, v in raw.items()}  # type: ignore[misc]
        except (json.JSONDecodeError, ValueError, TypeError):
            self.data = {}

    def _save_cache(self) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(json.dumps({f"{a}|{b}": v for (a, b), v in self.data.items()}))

    # -- building ---------------------------------------------------------- #
    def _ensure(self, allow_download: bool) -> None:
        wanted = [(a, b) for a in self.ids for b in self.ids if a != b]
        missing = [p for p in wanted if p not in self.data]
        if not missing:
            return
        if not allow_download:
            return
        meta = self.meta
        movesets = {}
        for sid in self.ids:
            mon = meta.rankings.get(sid)
            if mon and mon.moveset:
                movesets[sid] = mon.moveset
        if not self.quiet:
            print(f"[engine] simulating {len(missing)} matchups with PvPoke's engine", file=sys.stderr)
        rows = run_pairs(meta.store.file("gamemaster.json"), missing, meta.cp, cup=meta.cup,
                         movesets=movesets, directory=engine_dir(meta))
        for pair, row in rows.items():
            self.data[pair] = int(row["rating"])
        self.simulated = len(rows)
        self._save_cache()

    # -- access ------------------------------------------------------------ #
    def rating(self, a: str, b: str) -> int | None:
        return self.data.get((a, b))

    def attach(self) -> None:
        """Install this matrix on the Meta object (so Mon.matchup uses it)."""
        self.meta._matchups = self  # noqa: SLF001 - internal wiring

    def coverage(self, ids: Iterable[str] | None = None) -> str:
        ids = list(ids or self.ids)
        total = max(1, len(ids) * (len(ids) - 1))
        have = sum(1 for a in ids for b in ids if a != b and (a, b) in self.data)
        return f"{have}/{total} pairs"
