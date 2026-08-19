"""Fetch and cache real NFL weekly player stats from nflverse.

nflverse (https://github.com/nflverse/nflverse-data) publishes weekly-updated
player stat tables as public CSV release assets, scraped from official NFL
play-by-play data. We pull the ``player_stats`` release directly over HTTPS
(no API key required) and cache it locally so repeated runs don't re-download
~30MB every time.
"""

from __future__ import annotations

import csv
import io
import time
import urllib.error
import urllib.request
from pathlib import Path

PLAYER_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "player_stats/player_stats.csv"
)

CACHE_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_PATH = CACHE_DIR / "player_stats.csv"
CACHE_MAX_AGE_SECONDS = 12 * 3600  # re-download at most twice a day

NUMERIC_FIELDS = [
    "completions", "attempts", "passing_yards", "passing_tds", "interceptions",
    "sacks", "sack_yards", "sack_fumbles", "sack_fumbles_lost",
    "passing_2pt_conversions", "carries", "rushing_yards", "rushing_tds",
    "rushing_fumbles", "rushing_fumbles_lost", "rushing_2pt_conversions",
    "receptions", "targets", "receiving_yards", "receiving_tds",
    "receiving_fumbles", "receiving_fumbles_lost", "receiving_2pt_conversions",
    "special_teams_tds",
]


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    req = urllib.request.Request(url, headers={"User-Agent": "bestball-sim/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    tmp.replace(dest)


def fetch_player_stats_csv(force_refresh: bool = False) -> Path:
    """Return a local path to the nflverse player_stats.csv, downloading/
    refreshing the cache as needed. Falls back to a stale cache if the
    network is unavailable."""
    fresh_enough = (
        CACHE_PATH.exists()
        and (time.time() - CACHE_PATH.stat().st_mtime) < CACHE_MAX_AGE_SECONDS
    )
    if not force_refresh and fresh_enough:
        return CACHE_PATH

    try:
        _download(PLAYER_STATS_URL, CACHE_PATH)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if CACHE_PATH.exists():
            return CACHE_PATH
        raise RuntimeError(
            f"Could not download nflverse player stats from {PLAYER_STATS_URL} "
            f"and no local cache exists: {exc}"
        ) from exc
    return CACHE_PATH


def load_weekly_rows(season: int, csv_path: Path | None = None) -> list[dict]:
    """Load raw weekly stat rows for a given season (regular season only),
    with numeric fields coerced to float/int."""
    path = csv_path or fetch_player_stats_csv()
    season_str = str(season)
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["season"] != season_str:
                continue
            if row["season_type"] != "REG":
                continue
            for field in NUMERIC_FIELDS:
                raw = row.get(field, "")
                row[field] = float(raw) if raw not in ("", None) else 0.0
            row["week"] = int(float(row["week"]))
            rows.append(row)
    return rows


def available_seasons(csv_path: Path | None = None) -> list[int]:
    path = csv_path or fetch_player_stats_csv()
    seasons: set[int] = set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["season_type"] == "REG":
                seasons.add(int(row["season"]))
    return sorted(seasons)


def latest_complete_season(csv_path: Path | None = None) -> int:
    """Heuristic: the most recent season that has an 18-week regular season
    footprint in the data (i.e. it actually finished)."""
    path = csv_path or fetch_player_stats_csv()
    weeks_by_season: dict[int, int] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["season_type"] != "REG":
                continue
            s = int(row["season"])
            w = int(float(row["week"]))
            weeks_by_season[s] = max(weeks_by_season.get(s, 0), w)
    complete = [s for s, w in weeks_by_season.items() if w >= 17]
    if not complete:
        raise RuntimeError("No complete NFL regular season found in nflverse data")
    return max(complete)
