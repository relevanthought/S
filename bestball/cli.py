"""Command-line entry point for the Best Ball contest simulation."""

from __future__ import annotations

import argparse

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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.refresh_data:
        data.fetch_player_stats_csv(force_refresh=True)

    sim_season = args.season or data.latest_complete_season()

    payout_spec = payouts.PayoutSpec(entry_fee=args.entry_fee, rake=args.rake)
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
