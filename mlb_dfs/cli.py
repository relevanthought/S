"""Command-line entry point for the DK Classic MLB lineup optimizer."""

from __future__ import annotations

import argparse
import sys

from . import optimizer
from .optimizer import Lineup
from .slate import load_dk_export, load_projections_csv, load_sample_slate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mlb_dfs",
        description=(
            "Optimize a DraftKings Classic MLB lineup from a DK salary CSV export "
            "(Lineup Builder -> Export to CSV)."
        ),
    )
    parser.add_argument(
        "--salaries",
        metavar="PATH",
        help="path to a DraftKings Classic MLB salary CSV export for the slate you want to optimize",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="use the bundled synthetic sample slate instead of --salaries (demo/testing only, not a real date)",
    )
    parser.add_argument(
        "--projections",
        metavar="PATH",
        help="optional CSV of name,projection to override DK's built-in AvgPointsPerGame",
    )
    parser.add_argument("--salary-cap", type=int, default=optimizer.SALARY_CAP, help="salary cap (default 50000)")
    parser.add_argument(
        "--max-hitters-per-team",
        type=int,
        default=optimizer.MAX_HITTERS_PER_TEAM,
        help="max hitters from one team (default 5, DK's rule)",
    )
    parser.add_argument(
        "--min-games", type=int, default=optimizer.MIN_GAMES, help="min distinct games represented (default 2)"
    )
    parser.add_argument("--lock", action="append", default=[], metavar="DK_ID", help="force a player id into the lineup (repeatable)")
    parser.add_argument("--exclude", action="append", default=[], metavar="DK_ID", help="exclude a player id (repeatable)")
    parser.add_argument("--lineups", type=int, default=1, help="number of distinct lineups to generate (default 1)")
    parser.add_argument(
        "--max-overlap",
        type=int,
        default=8,
        help="max shared players between generated lineups when --lineups > 1 (default 8)",
    )
    return parser


def _print_lineup(lineup: Lineup, index: int | None = None) -> None:
    header = "=== Optimized Lineup ===" if index is None else f"=== Lineup {index} ==="
    print(header)
    print(f"{'Slot':<5} {'Player':<24} {'Team':<5} {'Opp':<5} {'Salary':>8} {'Proj':>7}")
    for label, p in lineup.slots:
        print(f"{label:<5} {p.name:<24} {p.team:<5} {p.opponent:<5} {p.salary:>8,} {p.projection:>7.2f}")
    print("-" * 60)
    print(
        f"Total salary: ${lineup.total_salary:,} / ${optimizer.SALARY_CAP:,} "
        f"(${lineup.remaining_salary:,} unused)  |  Projected points: {lineup.total_projection}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.salaries and not args.sample:
        parser.error(
            "no slate provided. DraftKings' live salary pool isn't reachable from this environment "
            "(see README) -- pass --salaries with a CSV exported from the DK Lineup Builder "
            "('Export to CSV'), or use --sample for a synthetic demo slate."
        )

    projections = load_projections_csv(args.projections) if args.projections else None

    if args.sample:
        if projections is not None:
            print("warning: --projections has no effect combined with --sample's fixed data", file=sys.stderr)
        players = load_sample_slate()
    else:
        players = load_dk_export(args.salaries, projections=projections)

    if not players:
        print("no players loaded from slate", file=sys.stderr)
        return 1

    kwargs = dict(
        salary_cap=args.salary_cap,
        max_hitters_per_team=args.max_hitters_per_team,
        min_games=args.min_games,
        locked=args.lock,
        excluded=args.exclude,
    )

    if args.lineups <= 1:
        lineup = optimizer.optimize(players, **kwargs)
        if lineup is None:
            print("no feasible lineup found under the given constraints", file=sys.stderr)
            return 1
        _print_lineup(lineup)
        return 0

    lineups = optimizer.optimize_multiple(players, args.lineups, max_overlap=args.max_overlap, **kwargs)
    if not lineups:
        print("no feasible lineup found under the given constraints", file=sys.stderr)
        return 1
    for i, lineup in enumerate(lineups, start=1):
        _print_lineup(lineup, index=i)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
