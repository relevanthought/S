"""Build a season's draftable player pool with weekly actual scores and an
ADP (Average Draft Position).

DraftKings Best Ball drafts happen *before* the season, using ADP that
reflects the market's pre-season expectations -- not the season's actual
results. Where a real DK Best Ball ADP snapshot is available (see
``live_adp.py`` -- currently a snapshot for the upcoming 2026 season
sourced from occupyfantasy.com, since that site itself is blocked from live
fetches in this environment) we use it directly, matched by normalized
player name + position. For anyone not in that snapshot (players scored
against an older season, or players the snapshot doesn't cover), we fall
back to a proxy: rank by *prior* season real DK fantasy points converted to
points-above-replacement, plus a small deterministic tiebreak for
rookies/unknowns with no prior-season data. Both paths only use information
that would genuinely have been available before Week 1, so the draft never
"sees the future."

Note the ADP snapshot's vintage (2026) and the `season` argument here
(real box scores, currently available through 2024 -- nflverse hasn't
published 2025 results yet and 2026 hasn't been played) are independent:
using 2026 ADP with `season=2024` runs a "2026 market, 2024 results"
backtest, not a literal replay of the 2026 season.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field

from . import data, live_adp
from .live_adp import normalize_name
from .scoring import dk_points

DRAFTABLE_POSITIONS = {"QB", "RB", "WR", "TE"}

# Approximate replacement-level depth per position for a 12-team Best Ball
# league (starters + realistic bench draft depth). Used to convert raw
# prior-season points into points-above-replacement, which is what actually
# drives real-world ADP ordering (e.g. why RB/WR go earlier than QB despite
# QBs scoring the most raw points -- teams only start one QB).
REPLACEMENT_RANK = {"QB": 16, "RB": 40, "WR": 48, "TE": 15}


@dataclass
class Player:
    player_id: str
    name: str
    position: str
    team: str
    adp: int  # 1 = drafted first on average
    weekly_points: dict = field(default_factory=dict)  # week -> DK points
    adp_source: str = "proxy"  # "live" (real DK ADP snapshot) or "proxy" (points-above-replacement)

    def points_in_week(self, week: int) -> float:
        return self.weekly_points.get(week, 0.0)

    def season_total(self) -> float:
        return round(sum(self.weekly_points.values()), 2)

    def games_played(self) -> int:
        return len(self.weekly_points)


def _primary_position_and_team(rows: list[dict]) -> tuple[str, str]:
    pos_counts: dict[str, int] = defaultdict(int)
    team_counts: dict[str, int] = defaultdict(int)
    for r in rows:
        pos_counts[r["position"]] += 1
        team_counts[r["recent_team"]] += 1
    position = max(pos_counts, key=pos_counts.get)
    team = max(team_counts, key=team_counts.get)
    return position, team


def _rookie_tiebreak(player_id: str) -> float:
    """Small, deterministic pseudo-random value in [0, 1) so undrafted-history
    players don't all tie at the same ADP value, without leaking any
    knowledge of how the upcoming season actually goes."""
    digest = hashlib.sha256(player_id.encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def build_player_pool(season: int, use_live_adp: bool = True) -> list[Player]:
    """Return the draftable player pool for ``season``: real DK weekly
    scores for that season, ADP from the real DK snapshot in ``live_adp.py``
    where a player matches it, falling back to a ``season - 1`` results-based
    proxy for anyone it doesn't cover. Pass ``use_live_adp=False`` to use the
    proxy for every player (e.g. for older seasons predating the snapshot)."""
    csv_path = data.fetch_player_stats_csv()
    live_adp_table = live_adp.load_live_adp() if use_live_adp else {}
    current_rows = data.load_weekly_rows(season, csv_path)
    prior_rows = data.load_weekly_rows(season - 1, csv_path)

    prior_totals: dict[str, float] = defaultdict(float)
    prior_position: dict[str, str] = {}
    for r in prior_rows:
        if r["position"] not in DRAFTABLE_POSITIONS:
            continue
        prior_totals[r["player_id"]] += dk_points(r)
        prior_position[r["player_id"]] = r["position"]

    by_position: dict[str, list[float]] = defaultdict(list)
    for player_id, total in prior_totals.items():
        by_position[prior_position[player_id]].append(total)
    replacement_value: dict[str, float] = {}
    for pos, rank in REPLACEMENT_RANK.items():
        totals = sorted(by_position.get(pos, []), reverse=True)
        idx = min(rank, len(totals)) - 1
        replacement_value[pos] = totals[idx] if idx >= 0 else 0.0

    rows_by_player: dict[str, list[dict]] = defaultdict(list)
    for r in current_rows:
        if r["position"] not in DRAFTABLE_POSITIONS:
            continue
        rows_by_player[r["player_id"]].append(r)

    candidates = []
    for player_id, rows in rows_by_player.items():
        position, team = _primary_position_and_team(rows)
        name = rows[-1]["player_display_name"] or rows[-1]["player_name"]
        weekly_points = {r["week"]: dk_points(r) for r in rows}
        vbd = prior_totals.get(player_id, 0.0) - replacement_value.get(position, 0.0)
        proxy_value = vbd + _rookie_tiebreak(player_id)
        live_value = live_adp_table.get((normalize_name(name), position))
        candidates.append(
            {
                "player_id": player_id,
                "name": name,
                "position": position,
                "team": team,
                "proxy_value": proxy_value,
                "live_value": live_value,
                "weekly_points": weekly_points,
            }
        )

    # Real ADP first (lower = drafted earlier), then the proxy fallback for
    # anyone the live snapshot doesn't cover (higher points-above-replacement
    # = drafted earlier).
    matched = sorted((c for c in candidates if c["live_value"] is not None), key=lambda c: c["live_value"])
    unmatched = sorted(
        (c for c in candidates if c["live_value"] is None), key=lambda c: c["proxy_value"], reverse=True
    )

    players = []
    for rank, c in enumerate(matched + unmatched, start=1):
        players.append(
            Player(
                player_id=c["player_id"],
                name=c["name"],
                position=c["position"],
                team=c["team"],
                adp=rank,
                weekly_points=c["weekly_points"],
                adp_source="live" if c["live_value"] is not None else "proxy",
            )
        )
    return players
