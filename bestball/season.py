"""Orchestrates a full Best Ball contest simulation: draft -> weekly Best Ball
scoring against real historical NFL results -> standings -> a simplified
"advance the top teams to a championship week" cut, mirroring the shape of
DraftKings' multi-stage Best Ball tournaments without claiming to reproduce
their exact (unpublished/live-only) bracket rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import data, payouts, players
from .draft import Draft, Team
from .lineup import best_lineup

REGULAR_SEASON_WEEKS = list(range(1, 15))  # weeks 1-14
PLAYOFF_WEEKS = [15, 16, 17]  # weeks 15-17


@dataclass
class TeamResult:
    team: Team
    weekly_points: dict[int, float]
    regular_season_total: float
    playoff_total: float
    advanced: bool
    final_rank: int
    payout: float = 0.0


@dataclass
class LeagueResult:
    season: int
    draft: Draft
    weeks_available: list[int]
    results: list[TeamResult]  # sorted by final rank

    def standings(self) -> list[TeamResult]:
        return self.results


def _weeks_with_data(season: int) -> list[int]:
    all_weeks = REGULAR_SEASON_WEEKS + PLAYOFF_WEEKS
    rows = data.load_weekly_rows(season)
    available = {r["week"] for r in rows}
    return [w for w in all_weeks if w in available]


@dataclass
class SweepResult:
    season: int
    num_teams: int
    league_results: list[LeagueResult]


def simulate_many(
    season: int,
    num_teams: int = 12,
    num_sims: int = 100,
    base_seed: int = 0,
    advance_count: int = 4,
    payout_spec: payouts.PayoutSpec | None = None,
) -> SweepResult:
    """Run `num_sims` independently-seeded league simulations against the
    same real season (same player pool, different random drafts) so you can
    see how much of a "champion" is draft-randomness noise vs. a repeatable
    edge -- e.g. whether a particular draft slot (pick position) wins more
    than its fair share.
    """
    pool = players.build_player_pool(season)
    league_results = [
        simulate_league(
            season=season,
            num_teams=num_teams,
            seed=base_seed + i,
            advance_count=advance_count,
            payout_spec=payout_spec,
            player_pool=pool,
        )
        for i in range(num_sims)
    ]
    return SweepResult(season=season, num_teams=num_teams, league_results=league_results)


def simulate_league(
    season: int,
    num_teams: int = 12,
    team_names: list[str] | None = None,
    seed: int | None = None,
    advance_count: int = 4,
    payout_spec: payouts.PayoutSpec | None = None,
    player_pool: list[players.Player] | None = None,
) -> LeagueResult:
    """Simulate one Best Ball league: draft `num_teams` rosters, score every
    week of the given `season` with real NFL results, cut to the top
    `advance_count` teams after the regular-season weeks, and rank the field
    by (regular season + playoff) points.
    """
    pool = player_pool if player_pool is not None else players.build_player_pool(season)
    draft = Draft(pool, num_teams=num_teams, team_names=team_names, seed=seed)
    teams = draft.run()

    weeks = _weeks_with_data(season)
    reg_weeks = [w for w in REGULAR_SEASON_WEEKS if w in weeks]
    playoff_weeks = [w for w in PLAYOFF_WEEKS if w in weeks]

    weekly_points: dict[int, dict[int, float]] = {}
    reg_totals: dict[int, float] = {}
    for team in teams:
        wp = {w: best_lineup(team.roster, w).total_points for w in reg_weeks + playoff_weeks}
        weekly_points[team.team_id] = wp
        reg_totals[team.team_id] = round(sum(wp[w] for w in reg_weeks), 2)

    advance_count = min(advance_count, num_teams)
    ranked_by_regular_season = sorted(teams, key=lambda t: reg_totals[t.team_id], reverse=True)
    advancing_ids = {t.team_id for t in ranked_by_regular_season[:advance_count]}

    playoff_totals: dict[int, float] = {}
    for team in teams:
        if team.team_id in advancing_ids and playoff_weeks:
            playoff_totals[team.team_id] = round(
                sum(weekly_points[team.team_id][w] for w in playoff_weeks), 2
            )
        else:
            playoff_totals[team.team_id] = 0.0

    def sort_key(t: Team):
        advanced = t.team_id in advancing_ids
        # Advancing teams are ranked by playoff total among themselves;
        # everyone else is ranked below them by regular-season total.
        return (advanced, playoff_totals[t.team_id] if advanced else 0, reg_totals[t.team_id])

    final_order = sorted(teams, key=sort_key, reverse=True)

    payout_map = payouts.payout_table(num_teams, payout_spec)

    results = []
    for rank, team in enumerate(final_order, start=1):
        results.append(
            TeamResult(
                team=team,
                weekly_points=weekly_points[team.team_id],
                regular_season_total=reg_totals[team.team_id],
                playoff_total=playoff_totals[team.team_id],
                advanced=team.team_id in advancing_ids,
                final_rank=rank,
                payout=payout_map.get(rank, 0.0),
            )
        )

    return LeagueResult(
        season=season,
        draft=draft,
        weeks_available=reg_weeks + playoff_weeks,
        results=results,
    )
