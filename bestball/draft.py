"""Snake-draft simulation with AI opponents.

Mirrors DraftKings Best Ball Mania-style roster construction: 8 starting
slots (QB, 2x RB, 3x WR, TE, 1x FLEX) plus a 12-man bench for 20 total
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
BENCH_SIZE = 12
ROSTER_SIZE = sum(STARTER_SLOTS.values()) + BENCH_SIZE  # 20

POSITION_MIN = {"QB": 1, "RB": 3, "WR": 4, "TE": 1}
POSITION_MAX = {"QB": 4, "RB": 10, "WR": 11, "TE": 5}
POSITION_SOFT_TARGET = {"QB": 2, "RB": 7, "WR": 8, "TE": 2}

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
        team_targets: dict[int, dict[str, int]] | None = None,
        team_embargoes: dict[int, dict[str, int]] | None = None,
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

        # Optional per-team exact roster-construction override, e.g.
        # {0: {"QB": 3, "RB": 7, "WR": 7, "TE": 3}} to force team 0 to draft
        # exactly that position mix instead of following the default
        # min/max/soft-target heuristic. Each target dict must sum to
        # ROSTER_SIZE. Teams not present in team_targets use the default
        # heuristic.
        self.team_targets = team_targets or {}
        for team_id, target in self.team_targets.items():
            if sum(target.values()) != ROSTER_SIZE:
                raise ValueError(
                    f"roster target for team {team_id} must sum to {ROSTER_SIZE}, "
                    f"got {sum(target.values())}: {target}"
                )

        # Optional per-team draft-order embargo, e.g. {0: {"RB": 5}} bars
        # team 0 from drafting any RB before round 5 -- this is the actual
        # mechanism behind strategies like "Zero RB" (avoid the position
        # early, then take opportunistic value once it's cheaper), which a
        # final-count target alone can't express: two teams can finish with
        # the same RB count while one drafted them all in rounds 1-3 and the
        # other waited until round 6+. Combines with team_targets or the
        # default heuristic -- it only ever narrows the eligible set further.
        self.team_embargoes = team_embargoes or {}

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
        target = self.team_targets.get(team.team_id)
        if target is not None:
            eligible = {pos for pos, count in target.items() if team.position_count(pos) < count}
            eligible = eligible or set(target.keys())  # safety net; shouldn't trigger if target sums to ROSTER_SIZE
        else:
            remaining_picks = ROSTER_SIZE - len(team.roster)
            deficits = {
                pos: max(0, POSITION_MIN[pos] - team.position_count(pos)) for pos in POSITION_MIN
            }
            required = sum(deficits.values())
            if required >= remaining_picks:
                forced = {pos for pos, d in deficits.items() if d > 0}
                if forced:
                    eligible = forced
                else:
                    eligible = {pos for pos in POSITION_MAX if team.position_count(pos) < POSITION_MAX[pos]}
            else:
                eligible = {pos for pos in POSITION_MAX if team.position_count(pos) < POSITION_MAX[pos]}

        embargo = self.team_embargoes.get(team.team_id)
        if embargo:
            current_round = len(team.roster) + 1
            embargoed_out = {pos for pos, pos_eligible in embargo.items() if current_round < pos_eligible}
            narrowed = eligible - embargoed_out
            # If the embargo would leave nothing draftable this pick (e.g. a
            # forced deficit-fill collides with an embargoed position),
            # honor the deficit fill rather than stalling the draft.
            eligible = narrowed or eligible

        return eligible

    def _select_pick(self, team: Team) -> Player:
        eligible = self._eligible_positions(team)
        candidates = [p for p in self.available.values() if p.position in eligible]
        if not candidates:
            candidates = list(self.available.values())

        soft_targets = self.team_targets.get(team.team_id, POSITION_SOFT_TARGET)

        best_player = None
        best_score = float("-inf")
        for p in candidates:
            base_value = 1000.0 * (ADP_DECAY**p.adp)
            noise = self.rng.lognormvariate(0.0, self.noise_sigma)
            perceived = base_value * noise
            soft = soft_targets.get(p.position, 0)
            count = team.position_count(p.position)
            need_bonus = max(0, soft - count) * NEED_BONUS_WEIGHT
            score = perceived + need_bonus
            if score > best_score:
                best_score = score
                best_player = p
        return best_player
