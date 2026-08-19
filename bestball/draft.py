"""Snake-draft simulation with AI opponents.

Mirrors DraftKings Best Ball Mania-style roster construction: 8 starting
slots (QB, 2x RB, 3x WR, TE, 1x FLEX) plus a 10-man bench for 18 total
rounds, no kicker or defense. Exact DK roster-construction position limits
aren't published in a scrapeable feed, so ``POSITION_MIN``/``POSITION_MAX``/
``POSITION_SOFT_TARGET`` below are a reasonable, documented approximation
you can tune.

Each AI team drafts "best player available" off of ADP, perturbed by
per-pick random noise (so repeated drafts don't all look identical) and a
positional-need bonus that steers teams toward a balanced roster instead of
hoarding one position.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .players import Player

STARTER_SLOTS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1}
BENCH_SIZE = 10
ROSTER_SIZE = sum(STARTER_SLOTS.values()) + BENCH_SIZE  # 18

POSITION_MIN = {"QB": 1, "RB": 3, "WR": 4, "TE": 1}
POSITION_MAX = {"QB": 4, "RB": 9, "WR": 10, "TE": 4}
POSITION_SOFT_TARGET = {"QB": 2, "RB": 6, "WR": 7, "TE": 2}

NEED_BONUS_WEIGHT = 12.0
ADP_DECAY = 0.985  # controls how steeply perceived value falls off with ADP


@dataclass
class Team:
    team_id: int
    name: str
    roster: list[Player] = field(default_factory=list)

    def position_count(self, position: str) -> int:
        return sum(1 for p in self.roster if p.position == position)


@dataclass
class DraftPick:
    pick_no: int
    round: int
    team_id: int
    player: Player


class Draft:
    def __init__(
        self,
        player_pool: list[Player],
        num_teams: int = 12,
        team_names: list[str] | None = None,
        seed: int | None = None,
        noise_sigma: float = 0.25,
    ):
        if num_teams < 2:
            raise ValueError("num_teams must be >= 2")
        self.num_teams = num_teams
        self.rng = random.Random(seed)
        self.noise_sigma = noise_sigma
        names = team_names or [f"Team {i + 1}" for i in range(num_teams)]
        if len(names) != num_teams:
            raise ValueError("team_names must have exactly num_teams entries")
        self.teams = [Team(i, names[i]) for i in range(num_teams)]
        self.available: dict[str, Player] = {p.player_id: p for p in player_pool}
        self.picks: list[DraftPick] = []

    def run(self) -> list[Team]:
        pick_no = 0
        for rnd in range(1, ROSTER_SIZE + 1):
            order = range(self.num_teams) if rnd % 2 == 1 else range(self.num_teams - 1, -1, -1)
            for team_idx in order:
                pick_no += 1
                team = self.teams[team_idx]
                player = self._select_pick(team)
                team.roster.append(player)
                del self.available[player.player_id]
                self.picks.append(DraftPick(pick_no, rnd, team.team_id, player))
        return self.teams

    def _eligible_positions(self, team: Team) -> set[str]:
        remaining_picks = ROSTER_SIZE - len(team.roster)
        deficits = {
            pos: max(0, POSITION_MIN[pos] - team.position_count(pos)) for pos in POSITION_MIN
        }
        required = sum(deficits.values())
        if required >= remaining_picks:
            forced = {pos for pos, d in deficits.items() if d > 0}
            if forced:
                return forced
        return {pos for pos in POSITION_MAX if team.position_count(pos) < POSITION_MAX[pos]}

    def _select_pick(self, team: Team) -> Player:
        eligible = self._eligible_positions(team)
        candidates = [p for p in self.available.values() if p.position in eligible]
        if not candidates:
            candidates = list(self.available.values())

        best_player = None
        best_score = float("-inf")
        for p in candidates:
            base_value = 1000.0 * (ADP_DECAY**p.adp)
            noise = self.rng.lognormvariate(0.0, self.noise_sigma)
            perceived = base_value * noise
            soft = POSITION_SOFT_TARGET.get(p.position, 0)
            count = team.position_count(p.position)
            need_bonus = max(0, soft - count) * NEED_BONUS_WEIGHT
            score = perceived + need_bonus
            if score > best_score:
                best_score = score
                best_player = p
        return best_player
