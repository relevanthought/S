import itertools
import random
import unittest

from bestball.lineup import best_lineup
from bestball.players import Player


def make_player(pid, position, points_by_week):
    return Player(player_id=pid, name=pid, position=position, team="XX", adp=0, weekly_points=points_by_week)


def brute_force_best(roster, week):
    """Independent reference implementation: try every valid combination of
    2 RB/3 WR/1 TE + 1 FLEX and take the max, to check best_lineup's exact
    case-based solver against brute force."""
    qbs = [p for p in roster if p.position == "QB"]
    rbs = [p for p in roster if p.position == "RB"]
    wrs = [p for p in roster if p.position == "WR"]
    tes = [p for p in roster if p.position == "TE"]

    best_qb_pts = max((p.points_in_week(week) for p in qbs), default=0.0)

    best_total = float("-inf")
    for rb_combo in itertools.combinations(rbs, min(2, len(rbs))):
        for wr_combo in itertools.combinations(wrs, min(3, len(wrs))):
            for te_combo in itertools.combinations(tes, min(1, len(tes))):
                used = set(p.player_id for p in rb_combo + wr_combo + te_combo)
                flex_pool = [p for p in rbs + wrs + tes if p.player_id not in used]
                flex_pts = max((p.points_in_week(week) for p in flex_pool), default=0.0)
                total = (
                    sum(p.points_in_week(week) for p in rb_combo)
                    + sum(p.points_in_week(week) for p in wr_combo)
                    + sum(p.points_in_week(week) for p in te_combo)
                    + flex_pts
                )
                best_total = max(best_total, total)
    return best_qb_pts + best_total


class TestLineupOptimizer(unittest.TestCase):
    def _random_roster(self, rng):
        roster = []
        for i in range(rng.randint(1, 3)):
            roster.append(make_player(f"qb{i}", "QB", {1: rng.uniform(0, 35)}))
        for i in range(rng.randint(3, 7)):
            roster.append(make_player(f"rb{i}", "RB", {1: rng.uniform(0, 30)}))
        for i in range(rng.randint(4, 8)):
            roster.append(make_player(f"wr{i}", "WR", {1: rng.uniform(0, 30)}))
        for i in range(rng.randint(1, 4)):
            roster.append(make_player(f"te{i}", "TE", {1: rng.uniform(0, 25)}))
        return roster

    def test_matches_brute_force_on_random_rosters(self):
        rng = random.Random(1234)
        for _ in range(50):
            roster = self._random_roster(rng)
            expected = brute_force_best(roster, week=1)
            got = best_lineup(roster, week=1).total_points
            self.assertAlmostEqual(got, round(expected, 2), places=1)

    def test_flex_picks_best_remaining_player(self):
        roster = [
            make_player("qb1", "QB", {1: 20}),
            make_player("rb1", "RB", {1: 10}),
            make_player("rb2", "RB", {1: 8}),
            make_player("rb3", "RB", {1: 25}),  # should win FLEX over wr3
            make_player("wr1", "WR", {1: 12}),
            make_player("wr2", "WR", {1: 11}),
            make_player("wr3", "WR", {1: 5}),
            make_player("te1", "TE", {1: 7}),
        ]
        lu = best_lineup(roster, week=1)
        # rb3 (25) and rb1 (10) are the two best RBs and take the core RB
        # slots; rb2 (8), the third-best RB, fills FLEX ahead of wr3 (5).
        self.assertEqual({p.player_id for p in lu.rbs}, {"rb3", "rb1"})
        self.assertEqual(lu.flex.player_id, "rb2")
        self.assertAlmostEqual(lu.total_points, 20 + 10 + 8 + 12 + 11 + 5 + 7 + 25)

    def test_bench_excludes_starters(self):
        # 4 RB / 3 WR / 1 TE: with only 3 WR and 1 TE, the (2,4,1) and
        # (2,3,2) FLEX cases are infeasible, so only (3,3,1) applies and the
        # weakest RB is necessarily the odd one out.
        roster = [
            make_player("qb1", "QB", {1: 20}),
            make_player("rb1", "RB", {1: 10}),
            make_player("rb2", "RB", {1: 8}),
            make_player("rb3", "RB", {1: 6}),
            make_player("rb4", "RB", {1: 1}),
            make_player("wr1", "WR", {1: 12}),
            make_player("wr2", "WR", {1: 11}),
            make_player("wr3", "WR", {1: 5}),
            make_player("te1", "TE", {1: 7}),
        ]
        lu = best_lineup(roster, week=1)
        starter_ids = {p.player_id for p in lu.starters}
        bench_ids = {p.player_id for p in lu.bench}
        self.assertEqual(starter_ids & bench_ids, set())
        self.assertEqual(starter_ids | bench_ids, {p.player_id for p in roster})
        self.assertEqual(bench_ids, {"rb4"})  # lowest scorer sits


if __name__ == "__main__":
    unittest.main()
