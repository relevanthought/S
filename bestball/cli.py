"""Command-line entry point for the Best Ball contest simulation."""

from __future__ import annotations

import argparse
import statistics
from collections import Counter

from . import data, payouts, season


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bestball",
        description="Simulate a DraftKings-style NFL Best Ball contest using real historical results.",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=None,
        help="NFL season to simulate (defaults to the most recent complete season in the data)",
    )
    parser.add_argument("--teams", type=int, default=12, help="number of teams in the league (default 12)")
    parser.add_argument("--seed", type=int, default=None, help="random seed for reproducible drafts")
    parser.add_argument(
        "--advance", type=int, default=4, help="number of teams that advance to the playoff weeks (default 4)"
    )
    parser.add_argument("--entry-fee", type=float, default=25.0, help="contest entry fee in $ (default 25)")
    parser.add_argument("--rake", type=float, default=0.15, help="platform rake fraction (default 0.15)")
    parser.add_argument(
        "--show-rosters", action="store_true", help="print each team's full drafted roster"
    )
    parser.add_argument(
        "--refresh-data", action="store_true", help="force re-download of the nflverse stats cache"
    )
    parser.add_argument(
        "--sweep",
        type=int,
        default=None,
        metavar="N",
        help="run N independently-seeded simulations and report champion consistency instead of a single result",
    )
    parser.add_argument(
        "--sweep-base-seed", type=int, default=0, help="first seed used in a --sweep run (default 0)"
    )
    return parser


def _print_draft_board(result: season.LeagueResult) -> None:
    print(f"\n=== Draft ({result.draft.num_teams} teams, {len(result.draft.picks)} picks) ===")
    for team in result.draft.teams:
        by_round = sorted(team.roster, key=lambda p: p.adp)
        line = ", ".join(f"{p.name} ({p.position})" for p in by_round)
        print(f"{team.name}: {line}")


def _print_standings(result: season.LeagueResult) -> None:
    print(f"\n=== Standings (season {result.season}) ===")
    header = f"{'Rk':>3} {'Team':<10} {'Reg Season':>11} {'Playoff':>9} {'Advanced':>9} {'Payout':>10}"
    print(header)
    print("-" * len(header))
    for r in result.results:
        print(
            f"{r.final_rank:>3} {r.team.name:<10} {r.regular_season_total:>11.1f} "
            f"{r.playoff_total:>9.1f} {str(r.advanced):>9} ${r.payout:>9.2f}"
        )


def _run_sweep(args: argparse.Namespace, sim_season: int, payout_spec: payouts.PayoutSpec) -> None:
    sweep = season.simulate_many(
        season=sim_season,
        num_teams=args.teams,
        num_sims=args.sweep,
        base_seed=args.sweep_base_seed,
        advance_count=args.advance,
        payout_spec=payout_spec,
    )

    champion_slot_counts: Counter[int] = Counter()
    champion_totals = []
    runnerup_gaps = []
    field_totals = []

    for lr in sweep.league_results:
        champ = lr.results[0]
        champ_total = champ.regular_season_total + champ.playoff_total
        champion_slot_counts[champ.team.team_id] += 1
        champion_totals.append(champ_total)
        if len(lr.results) > 1:
            runner_up = lr.results[1]
            runner_up_total = runner_up.regular_season_total + runner_up.playoff_total
            runnerup_gaps.append(champ_total - runner_up_total)
        for r in lr.results:
            field_totals.append(r.regular_season_total + r.playoff_total)

    n = len(sweep.league_results)
    fair_rate = 100.0 / args.teams

    print(f"\n=== Seed sweep: {n} simulations, season {sim_season}, {args.teams} teams ===")
    print(
        f"Champion total points: mean={statistics.mean(champion_totals):.1f} "
        f"stdev={statistics.pstdev(champion_totals):.1f} "
        f"min={min(champion_totals):.1f} max={max(champion_totals):.1f}"
    )
    if runnerup_gaps:
        print(
            f"Margin over runner-up: mean={statistics.mean(runnerup_gaps):.1f} "
            f"stdev={statistics.pstdev(runnerup_gaps):.1f}"
        )
    print(
        f"Whole-field total points: mean={statistics.mean(field_totals):.1f} "
        f"stdev={statistics.pstdev(field_totals):.1f}"
    )

    print(f"\nChampion by draft slot (fair share would be {fair_rate:.1f}% each):")
    header = f"{'Slot':>4} {'Wins':>5} {'Win %':>7}"
    print(header)
    print("-" * len(header))
    for slot in range(args.teams):
        wins = champion_slot_counts.get(slot, 0)
        print(f"{slot + 1:>4} {wins:>5} {100.0 * wins / n:>6.1f}%")

    unique_champs = len(champion_slot_counts)
    print(f"\n{unique_champs}/{args.teams} distinct draft slots won at least once across {n} sims.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.refresh_data:
        data.fetch_player_stats_csv(force_refresh=True)

    sim_season = args.season or data.latest_complete_season()
    payout_spec = payouts.PayoutSpec(entry_fee=args.entry_fee, rake=args.rake)

    if args.sweep:
        _run_sweep(args, sim_season, payout_spec)
        return 0

    result = season.simulate_league(
        season=sim_season,
        num_teams=args.teams,
        seed=args.seed,
        advance_count=args.advance,
        payout_spec=payout_spec,
    )

    if args.show_rosters:
        _print_draft_board(result)
    _print_standings(result)

    winner = result.results[0]
    print(
        f"\nChampion: {winner.team.name} "
        f"({winner.regular_season_total + winner.playoff_total:.1f} total pts, ${winner.payout:.2f})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
