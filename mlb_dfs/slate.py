"""Loading a player pool from DraftKings' own CSV export format.

DraftKings doesn't expose a public, unauthenticated API for today's slate --
and even if it did, this environment's network egress policy blocks
draftkings.com and every sports-data/DFS site tried (see the "Live data"
section of the README), the same way it blocked occupyfantasy.com for the
NFL Best Ball ADP snapshot in ``bestball/live_adp.py``. So this module reads
the CSV a user downloads themselves from the DK contest lobby ("Export to
CSV" in the lineup builder for the classic MLB slate they want to optimize),
which is also how virtually every real MLB DFS optimizer tool sources salary
data -- DK's live pool is the one part of this that has no publicly
fetchable substitute at all.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .player import Player, parse_positions

# DK's Classic MLB export uses these headers (case varies slightly by sport/
# contest type over the years, so matching is case-insensitive).
_ID_COLS = ("id", "playerid", "player id")
_NAME_COLS = ("name", "playername", "player name")
_POSITION_COLS = ("roster position", "position")
_SALARY_COLS = ("salary",)
_GAME_INFO_COLS = ("game info", "gameinfo")
_TEAM_COLS = ("teamabbrev", "team")
_PROJECTION_COLS = ("avgpointspergame", "projection", "fpts", "proj")


def _find_column(fieldnames: list[str], candidates: tuple[str, ...]) -> str | None:
    lookup = {f.strip().lower(): f for f in fieldnames}
    for candidate in candidates:
        if candidate in lookup:
            return lookup[candidate]
    return None


def _parse_opponent(game_info: str, team: str) -> str:
    """Game Info looks like "NYY@BOS 07:05PM ET" -- pull out the other team."""
    matchup = game_info.split(" ")[0] if game_info else ""
    teams = matchup.replace("@", " ").split()
    others = [t for t in teams if t.upper() != team.upper()]
    return others[0] if others else ""


def load_dk_export(path: str | Path, projections: dict[str, float] | None = None) -> list[Player]:
    """Parse a DraftKings Classic MLB salary CSV export into ``Player`` rows.

    ``projections`` optionally overrides DK's built-in ``AvgPointsPerGame``
    column with a custom projection, keyed by player name (case-insensitive).
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError(f"{path}: no header row found")
        fieldnames = list(reader.fieldnames)

        id_col = _find_column(fieldnames, _ID_COLS)
        name_col = _find_column(fieldnames, _NAME_COLS)
        position_col = _find_column(fieldnames, _POSITION_COLS)
        salary_col = _find_column(fieldnames, _SALARY_COLS)
        game_info_col = _find_column(fieldnames, _GAME_INFO_COLS)
        team_col = _find_column(fieldnames, _TEAM_COLS)
        projection_col = _find_column(fieldnames, _PROJECTION_COLS)

        missing = [
            label
            for label, col in (
                ("Name", name_col),
                ("Position/Roster Position", position_col),
                ("Salary", salary_col),
                ("TeamAbbrev", team_col),
            )
            if col is None
        ]
        if missing:
            raise ValueError(
                f"{path}: missing expected DK export column(s): {', '.join(missing)}. "
                f"Found columns: {fieldnames}"
            )

        players: list[Player] = []
        for row in reader:
            name = row[name_col].strip()
            if not name:
                continue
            team = row[team_col].strip()
            game_info = row[game_info_col].strip() if game_info_col else ""
            dk_projection = float(row[projection_col]) if projection_col and row.get(projection_col) else 0.0
            projection = dk_projection
            if projections is not None:
                override = projections.get(name.lower())
                if override is not None:
                    projection = override
            players.append(
                Player(
                    dk_id=row[id_col].strip() if id_col else name,
                    name=name,
                    positions=parse_positions(row[position_col]),
                    salary=int(float(row[salary_col])),
                    team=team,
                    opponent=_parse_opponent(game_info, team),
                    game_info=game_info,
                    projection=projection,
                )
            )
        return players


def load_projections_csv(path: str | Path) -> dict[str, float]:
    """Load a simple ``name,projection`` CSV as a custom projections override."""
    path = Path(path)
    projections: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError(f"{path}: no header row found")
        name_col = _find_column(list(reader.fieldnames), _NAME_COLS)
        proj_col = _find_column(list(reader.fieldnames), _PROJECTION_COLS)
        if name_col is None or proj_col is None:
            raise ValueError(f"{path}: expected columns like 'name,projection'. Found: {reader.fieldnames}")
        for row in reader:
            name = row[name_col].strip()
            if not name:
                continue
            projections[name.lower()] = float(row[proj_col])
    return projections


def load_sample_slate() -> list[Player]:
    """Load the bundled synthetic sample slate, for demos and tests only.

    This is NOT a real slate for any actual date -- see data/README.md.
    """
    sample_path = Path(__file__).resolve().parent.parent / "data" / "sample_dk_mlb_slate.csv"
    return load_dk_export(sample_path)
