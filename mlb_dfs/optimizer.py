"""Exact (ILP) optimal lineup solver for DraftKings Classic MLB.

DK's Classic MLB roster and rules (published in-app, not something with a
fetchable API, so encoded here as documented constants):

- 10 roster slots: P, P, C, 1B, 2B, 3B, SS, OF, OF, OF.
- $50,000 salary cap.
- No more than 5 hitters (non-pitchers) from the same real MLB team.
- Players must be drawn from at least 2 different games on the slate.

This is a small assignment problem (10 slots, a few hundred candidate
players at most), solved exactly with an integer program rather than a
greedy/heuristic approach, so the result is provably the highest-projection
lineup satisfying every constraint -- not just a good one.
"""

from __future__ import annotations

from dataclasses import dataclass

import pulp

from .player import Player

ROSTER_SLOTS: tuple[str, ...] = ("P", "P", "C", "1B", "2B", "3B", "SS", "OF", "OF", "OF")
SALARY_CAP = 50_000
MAX_HITTERS_PER_TEAM = 5
MIN_GAMES = 2


@dataclass
class Lineup:
    slots: list[tuple[str, Player]]  # (slot label incl. index e.g. "OF2", Player)

    @property
    def players(self) -> list[Player]:
        return [p for _, p in self.slots]

    @property
    def total_salary(self) -> int:
        return sum(p.salary for p in self.players)

    @property
    def total_projection(self) -> float:
        return round(sum(p.projection for p in self.players), 2)

    @property
    def remaining_salary(self) -> int:
        return SALARY_CAP - self.total_salary


def _slot_labels(roster_slots: tuple[str, ...]) -> list[tuple[str, str]]:
    """Return [(display_label, base_position), ...], numbering duplicates."""
    counts: dict[str, int] = {}
    seen_total: dict[str, int] = {}
    for s in roster_slots:
        seen_total[s] = seen_total.get(s, 0) + 1

    labels = []
    for s in roster_slots:
        counts[s] = counts.get(s, 0) + 1
        label = s if seen_total[s] == 1 else f"{s}{counts[s]}"
        labels.append((label, s))
    return labels


def optimize(
    players: list[Player],
    *,
    salary_cap: int = SALARY_CAP,
    roster_slots: tuple[str, ...] = ROSTER_SLOTS,
    max_hitters_per_team: int = MAX_HITTERS_PER_TEAM,
    min_games: int = MIN_GAMES,
    locked: list[str] | None = None,
    excluded: list[str] | None = None,
    forbidden_player_sets: list[set[str]] | None = None,
    max_overlap: int | None = None,
) -> Lineup | None:
    """Solve for the highest-projection valid lineup. Returns None if infeasible.

    ``locked``/``excluded`` take DK player ids. ``forbidden_player_sets`` +
    ``max_overlap`` are used by ``optimize_multiple`` to force diversity
    across a batch of lineups (at most ``max_overlap`` shared players with
    any previously returned lineup).
    """
    excluded_ids = set(excluded or [])
    pool = [p for p in players if p.dk_id not in excluded_ids]
    slot_labels = _slot_labels(roster_slots)

    prob = pulp.LpProblem("dk_mlb_lineup", pulp.LpMaximize)

    x: dict[tuple[str, str], pulp.LpVariable] = {}
    for p in pool:
        for label, base in slot_labels:
            if p.eligible_for(base):
                x[(p.dk_id, label)] = pulp.LpVariable(f"x_{p.dk_id}_{label}", cat="Binary")

    if not x:
        return None

    def var(player_id: str, label: str) -> pulp.LpVariable | int:
        return x.get((player_id, label), 0)

    # Objective: maximize total projection.
    by_id = {p.dk_id: p for p in pool}
    prob += pulp.lpSum(var(p.dk_id, label) * p.projection for p in pool for label, _ in slot_labels)

    # Exactly one player per slot.
    for label, base in slot_labels:
        eligible = [p for p in pool if p.eligible_for(base)]
        prob += pulp.lpSum(var(p.dk_id, label) for p in eligible) == 1, f"fill_{label}"

    # Each player used at most once across all slots.
    for p in pool:
        p_vars = [var(p.dk_id, label) for label, _ in slot_labels if (p.dk_id, label) in x]
        if p_vars:
            prob += pulp.lpSum(p_vars) <= 1, f"once_{p.dk_id}"

    # Salary cap.
    prob += (
        pulp.lpSum(var(p.dk_id, label) * p.salary for p in pool for label, _ in slot_labels) <= salary_cap,
        "salary_cap",
    )

    # No more than N hitters from the same team.
    teams = {p.team for p in pool if not p.is_pitcher}
    for team in teams:
        hitter_vars = [
            var(p.dk_id, label)
            for p in pool
            if p.team == team and not p.is_pitcher
            for label, base in slot_labels
            if base != "P" and (p.dk_id, label) in x
        ]
        if hitter_vars:
            prob += pulp.lpSum(hitter_vars) <= max_hitters_per_team, f"team_cap_{team}"

    # At least `min_games` distinct games represented (equivalently: no single
    # game supplies every roster slot).
    games = {p.game_info for p in pool if p.game_info}
    if min_games >= 2 and len(games) >= min_games:
        n_slots = len(roster_slots)
        for game in games:
            game_vars = [
                var(p.dk_id, label)
                for p in pool
                if p.game_info == game
                for label, _ in slot_labels
                if (p.dk_id, label) in x
            ]
            if game_vars:
                prob += pulp.lpSum(game_vars) <= n_slots - 1, f"game_cap_{game!r}"

    # Locked players: must appear somewhere in the lineup.
    for player_id in locked or []:
        if player_id not in by_id:
            raise ValueError(f"locked player id {player_id!r} not found in pool")
        p_vars = [var(player_id, label) for label, _ in slot_labels if (player_id, label) in x]
        if not p_vars:
            return None  # locked player has no eligible slot
        prob += pulp.lpSum(p_vars) == 1, f"lock_{player_id}"

    # Diversity constraints against previously generated lineups.
    if forbidden_player_sets and max_overlap is not None:
        for i, prev_ids in enumerate(forbidden_player_sets):
            overlap_vars = [
                var(pid, label) for pid in prev_ids for label, _ in slot_labels if (pid, label) in x
            ]
            if overlap_vars:
                prob += pulp.lpSum(overlap_vars) <= max_overlap, f"diversity_{i}"

    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    if pulp.LpStatus[prob.status] != "Optimal":
        return None

    slots: list[tuple[str, Player]] = []
    for label, base in slot_labels:
        chosen = None
        for p in pool:
            v = var(p.dk_id, label)
            if not isinstance(v, int) and v.value() == 1:
                chosen = p
                break
        if chosen is None:
            return None
        slots.append((label, chosen))
    return Lineup(slots=slots)


def optimize_multiple(
    players: list[Player],
    n: int,
    *,
    max_overlap: int = 8,
    **kwargs,
) -> list[Lineup]:
    """Generate up to ``n`` distinct high-projection lineups.

    Each successive lineup may share at most ``max_overlap`` players with any
    earlier one in the batch, so results aren't just trivial swaps.
    """
    results: list[Lineup] = []
    forbidden: list[set[str]] = []
    for _ in range(n):
        lineup = optimize(players, forbidden_player_sets=forbidden, max_overlap=max_overlap, **kwargs)
        if lineup is None:
            break
        results.append(lineup)
        forbidden.append({p.dk_id for p in lineup.players})
    return results
