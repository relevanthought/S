import unittest

from bestball.draft import Draft, POSITION_MAX, POSITION_MIN, ROSTER_SIZE
from bestball.players import Player


def make_pool(n_qb=48, n_rb=110, n_wr=140, n_te=48):
    pool = []
    adp = 1
    # Interleave so ADP roughly reflects a realistic mixed draft order.
    counts = {"QB": n_qb, "RB": n_rb, "WR": n_wr, "TE": n_te}
    idx = {"QB": 0, "RB": 0, "WR": 0, "TE": 0}
    total = sum(counts.values())
    positions_cycle = (["RB", "WR"] * 3 + ["QB"] + ["TE"]) * (total // 7 + 1)
    for pos in positions_cycle:
        if idx[pos] >= counts[pos]:
            continue
        pid = f"{pos}{idx[pos]}"
        pool.append(Player(pid, pid, pos, "XX", adp, {1: max(0.0, 30 - adp * 0.1)}))
        idx[pos] += 1
        adp += 1
        if all(idx[p] >= counts[p] for p in counts):
            break
    return pool


class TestDraft(unittest.TestCase):
    def test_every_team_gets_full_roster_within_position_limits(self):
        pool = make_pool()
        draft = Draft(pool, num_teams=12, seed=99)
        teams = draft.run()
        self.assertEqual(len(teams), 12)
        for team in teams:
            self.assertEqual(len(team.roster), ROSTER_SIZE)
            player_ids = [p.player_id for p in team.roster]
            self.assertEqual(len(player_ids), len(set(player_ids)))  # no duplicates
            for pos, min_n in POSITION_MIN.items():
                count = team.position_count(pos)
                self.assertGreaterEqual(count, min_n, f"{team.name} under min {pos}")
                self.assertLessEqual(count, POSITION_MAX[pos], f"{team.name} over max {pos}")

    def test_no_player_drafted_twice_across_league(self):
        pool = make_pool()
        draft = Draft(pool, num_teams=10, seed=5)
        teams = draft.run()
        all_ids = [p.player_id for t in teams for p in t.roster]
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_deterministic_with_same_seed(self):
        pool = make_pool()
        teams_a = Draft(pool, num_teams=8, seed=123).run()
        teams_b = Draft(make_pool(), num_teams=8, seed=123).run()
        for ta, tb in zip(teams_a, teams_b):
            ids_a = [p.player_id for p in ta.roster]
            ids_b = [p.player_id for p in tb.roster]
            self.assertEqual(ids_a, ids_b)


if __name__ == "__main__":
    unittest.main()
