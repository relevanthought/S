"""Optimal weekly Best Ball lineup selection.

In Best Ball there's no in-season lineup management: for a given week, the
platform automatically starts whichever eligible players scored the most,
subject to the roster's starting slots (QB, 2x RB, 3x WR, TE, 1x FLEX). This
module computes that optimal lineup exactly (not greedily).

The RB/WR/TE + FLEX assignment is a small combinatorial problem: choose 6
players from the RB/WR/TE pool to fill 2 RB + 3 WR + 1 TE + 1 FLEX(RB/WR/TE)
maximizing total points. Since FLEX can only be one extra RB, WR, or TE, there
are exactly three feasible slot distributions to compare:
    3 RB + 3 WR + 1 TE
    2 RB + 4 WR + 1 TE
    2 RB + 3 WR + 2 TE
Taking the top-N by points within each position for each case and keeping the
best of the three cases is exactly optimal (a standard result for single-FLEX
assignment problems).
"""

from __future__ import annotations

from dataclasses import dataclass

from .players import Player

FLEX_CASES = [  # (rb_count, wr_count, te_count)
    (3, 3, 1),
    (2, 4, 1),
    (2, 3, 2),
]


@dataclass
class WeeklyLineup:
    week: int
    qb: Player | None
    rbs: list[Player]
    wrs: list[Player]
    tes: list[Player]
    flex: Player | None
    bench: list[Player]

    @property
    def starters(self) -> list[Player]:
        starters = list(self.rbs) + list(self.wrs) + list(self.tes)
        if self.qb:
            starters.append(self.qb)
        if self.flex:
            starters.append(self.flex)
        return starters

    @property
    def total_points(self) -> float:
        return round(sum(p.points_in_week(self.week) for p in self.starters), 2)


def _top(players: list[Player], week: int, n: int) -> list[Player]:
    ranked = sorted(players, key=lambda p: p.points_in_week(week), reverse=True)
    return ranked[:n]


def best_lineup(roster: list[Player], week: int) -> WeeklyLineup:
    qbs = [p for p in roster if p.position == "QB"]
    rbs = [p for p in roster if p.position == "RB"]
    wrs = [p for p in roster if p.position == "WR"]
    tes = [p for p in roster if p.position == "TE"]

    best_qb = max(qbs, key=lambda p: p.points_in_week(week), default=None)

    best_combo = None
    best_total = float("-inf")
    for rb_n, wr_n, te_n in FLEX_CASES:
        if len(rbs) < rb_n or len(wrs) < wr_n or len(tes) < te_n:
            continue
        rb_sel = _top(rbs, week, rb_n)
        wr_sel = _top(wrs, week, wr_n)
        te_sel = _top(tes, week, te_n)
        total = sum(p.points_in_week(week) for p in rb_sel + wr_sel + te_sel)
        if total > best_total:
            best_total = total
            best_combo = (rb_sel, wr_sel, te_sel)

    if best_combo is None:
        # Roster doesn't meet the usual minimums (e.g. ad-hoc/partial roster);
        # fall back to simply starting the best 2/3/1 available at each spot.
        rb_sel = _top(rbs, week, 2)
        wr_sel = _top(wrs, week, 3)
        te_sel = _top(tes, week, 1)
        best_combo = (rb_sel, wr_sel, te_sel)

    rb_sel, wr_sel, te_sel = best_combo
    # The FLEX slot is whichever "extra" player pushed one case above the
    # standard 2 RB/3 WR/1 TE -- identify it for display purposes.
    core_rb, core_wr, core_te = _top(rbs, week, 2), _top(wrs, week, 3), _top(tes, week, 1)
    flex = None
    for group_sel, core in ((rb_sel, core_rb), (wr_sel, core_wr), (te_sel, core_te)):
        extra = [p for p in group_sel if p not in core]
        if extra:
            flex = extra[0]
            break

    starters_ids = {p.player_id for p in rb_sel + wr_sel + te_sel}
    if best_qb:
        starters_ids.add(best_qb.player_id)
    bench = [p for p in roster if p.player_id not in starters_ids]

    # Present RB/WR/TE lists as the "core" slots (excluding flex) + flex separately.
    rbs_out = [p for p in rb_sel if p is not flex] if flex in rb_sel else rb_sel[:2]
    wrs_out = [p for p in wr_sel if p is not flex] if flex in wr_sel else wr_sel[:3]
    tes_out = [p for p in te_sel if p is not flex] if flex in te_sel else te_sel[:1]

    return WeeklyLineup(
        week=week,
        qb=best_qb,
        rbs=rbs_out,
        wrs=wrs_out,
        tes=tes_out,
        flex=flex,
        bench=bench,
    )


def season_points(roster: list[Player], weeks: list[int]) -> float:
    return round(sum(best_lineup(roster, w).total_points for w in weeks), 2)
