"""Build a season's draftable player pool with weekly actual scores and an
ADP (Average Draft Position) proxy.

DraftKings Best Ball drafts happen *before* the season, using ADP that
reflects the market's pre-season expectations -- not the season's actual
results. Since a live ADP feed isn't reachable from here, we derive a
realistic stand-in: rank players by their *prior* season's real DK fantasy
points (plus a small deterministic tiebreak for rookies/unknowns who have no
prior-season data). This uses only information that would genuinely have
been available before Week 1, so the draft never "sees the future."
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field

from . import data
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


def build_player_pool(season: int) -> list[Player]:
    """Return the draftable player pool for ``season``: real DK weekly
    scores for that season, ADP derived from the ``season - 1`` results."""
    csv_path = data.fetch_player_stats_csv()
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
        adp_value = vbd + _rookie_tiebreak(player_id)
        candidates.append(
            {
                "player_id": player_id,
                "name": name,
                "position": position,
                "team": team,
                "adp_value": adp_value,
                "weekly_points": weekly_points,
            }
        )

    candidates.sort(key=lambda c: c["adp_value"], reverse=True)

    players = []
    for rank, c in enumerate(candidates, start=1):
        players.append(
            Player(
                player_id=c["player_id"],
                name=c["name"],
                position=c["position"],
                team=c["team"],
                adp=rank,
                weekly_points=c["weekly_points"],
            )
        )
    return players
