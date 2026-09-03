import itertools
import unittest

from mlb_dfs.optimizer import ROSTER_SLOTS, SALARY_CAP, optimize, optimize_multiple
from mlb_dfs.player import Player, parse_positions
from mlb_dfs.slate import load_dk_export, load_sample_slate


def make_player(dk_id, name, positions, salary, team, opponent="OPP", projection=10.0, game_info=None):
    return Player(
        dk_id=dk_id,
        name=name,
        positions=positions if isinstance(positions, tuple) else tuple(positions.split("/")),
        salary=salary,
        team=team,
        opponent=opponent,
        game_info=game_info or f"{team}@{opponent}",
        projection=projection,
    )


class TestPlayer(unittest.TestCase):
    def test_parse_positions_splits_and_normalizes(self):
        self.assertEqual(parse_positions("1B/OF"), ("1B", "OF"))
        self.assertEqual(parse_positions("SP"), ("P",))
        self.assertEqual(parse_positions("SP/RP"), ("P",))

    def test_eligible_for_pitcher_slot(self):
        p = make_player("1", "Ace", ("P",), 8000, "AAA")
        self.assertTrue(p.eligible_for("P"))
        self.assertFalse(p.eligible_for("OF"))

    def test_eligible_for_multi_position_hitter(self):
        p = make_player("1", "Multi", ("1B", "OF"), 4000, "AAA")
        self.assertTrue(p.eligible_for("1B"))
        self.assertTrue(p.eligible_for("OF"))
        self.assertFalse(p.eligible_for("2B"))

    def test_value_is_points_per_1000_salary(self):
        p = make_player("1", "X", ("C",), 4000, "AAA", projection=8.0)
        self.assertAlmostEqual(p.value(), 2.0)


class TestSampleSlateLoader(unittest.TestCase):
    def setUp(self):
        self.players = load_sample_slate()

    def test_loads_a_reasonable_number_of_players(self):
        self.assertGreater(len(self.players), 40)

    def test_every_player_has_positive_salary_and_team(self):
        for p in self.players:
            self.assertGreater(p.salary, 0)
            self.assertTrue(p.team)

    def test_multi_position_player_parsed(self):
        multi = [p for p in self.players if len(p.positions) > 1]
        self.assertTrue(multi, "expected at least one multi-position player in the sample slate")
        for p in multi:
            self.assertGreaterEqual(len(p.positions), 2)

    def test_opponent_derived_from_game_info(self):
        for p in self.players:
            self.assertNotEqual(p.opponent, p.team)
            self.assertTrue(p.opponent)


def _feasible(players, salary_cap=SALARY_CAP, max_hitters_per_team=5, min_games=2):
    """Reference check: does this exact 10-player set satisfy every DK
    Classic MLB rule? Used to brute-force-verify the ILP optimizer."""
    if sum(p.salary for p in players) > salary_cap:
        return False
    teams = set(p.team for p in players)
    for team in teams:
        hitters = [p for p in players if p.team == team and not p.is_pitcher]
        if len(hitters) > max_hitters_per_team:
            return False
    games = set(p.game_info for p in players)
    if len(games) < min_games:
        return False
    return True


def _brute_force_best(players, roster_slots=ROSTER_SLOTS):
    """Independent reference optimizer: assumes every player in ``players``
    is single-position (true of the small test pool), so the roster slots
    partition cleanly into disjoint groups. Try every combination of players
    per position group and keep the best feasible, valid total. Only for
    small pools -- this is intentionally not the fast path the real
    optimizer uses."""
    needed: dict[str, int] = {}
    for slot in roster_slots:
        needed[slot] = needed.get(slot, 0) + 1

    by_position: dict[str, list] = {slot: [] for slot in needed}
    for p in players:
        (pos,) = p.positions
        if pos in by_position:
            by_position[pos].append(p)

    group_choices = []
    for pos, count in needed.items():
        group_choices.append(list(itertools.combinations(by_position[pos], count)))

    best_total = None
    for choice_combo in itertools.product(*group_choices):
        chosen = [p for group in choice_combo for p in group]
        if not _feasible(chosen):
            continue
        total = sum(p.projection for p in chosen)
        if best_total is None or total > best_total:
            best_total = total
    return best_total


class TestOptimizer(unittest.TestCase):
    def _small_pool(self):
        # Two games, two teams each -- small enough to brute force exactly.
        pool = []
        pool.append(make_player("p1", "Ace A", ("P",), 9000, "AAA", "BBB", 18.0, "AAA@BBB"))
        pool.append(make_player("p2", "Ace B", ("P",), 7000, "BBB", "AAA", 12.0, "AAA@BBB"))
        pool.append(make_player("p3", "Ace C", ("P",), 6000, "CCC", "DDD", 10.0, "CCC@DDD"))
        pool.append(make_player("p4", "Ace D", ("P",), 5000, "DDD", "CCC", 9.0, "CCC@DDD"))

        specs = [
            ("c1", "C", "AAA", "BBB", "AAA@BBB", 3000, 8.0),
            ("c2", "C", "BBB", "AAA", "AAA@BBB", 3500, 9.0),
            ("b1", "1B", "AAA", "BBB", "AAA@BBB", 4000, 10.0),
            ("b2", "1B", "CCC", "DDD", "CCC@DDD", 4200, 11.0),
            ("s2", "2B", "AAA", "BBB", "AAA@BBB", 3800, 9.5),
            ("s2b", "2B", "CCC", "DDD", "CCC@DDD", 3600, 8.5),
            ("t3", "3B", "BBB", "AAA", "AAA@BBB", 4100, 10.5),
            ("t3b", "3B", "DDD", "CCC", "CCC@DDD", 3900, 9.0),
            ("ss1", "SS", "AAA", "BBB", "AAA@BBB", 4300, 11.5),
            ("ss2", "SS", "CCC", "DDD", "CCC@DDD", 4000, 10.0),
            ("of1", "OF", "AAA", "BBB", "AAA@BBB", 3200, 8.5),
            ("of2", "OF", "BBB", "AAA", "AAA@BBB", 3400, 9.0),
            ("of3", "OF", "CCC", "DDD", "CCC@DDD", 3300, 8.8),
            ("of4", "OF", "DDD", "CCC", "CCC@DDD", 3100, 8.2),
        ]
        for dk_id, pos, team, opp, gi, salary, proj in specs:
            pool.append(make_player(dk_id, dk_id, (pos,), salary, team, opp, proj, gi))
        return pool

    def test_matches_brute_force_on_small_pool(self):
        pool = self._small_pool()
        lineup = optimize(pool)
        self.assertIsNotNone(lineup)
        expected = _brute_force_best(pool)
        self.assertAlmostEqual(lineup.total_projection, round(expected, 2))

    def test_lineup_respects_salary_cap_and_slots(self):
        players = load_sample_slate()
        lineup = optimize(players)
        self.assertIsNotNone(lineup)
        self.assertLessEqual(lineup.total_salary, SALARY_CAP)
        self.assertEqual(len(lineup.slots), len(ROSTER_SLOTS))
        for (label, p), base in zip(lineup.slots, ROSTER_SLOTS):
            self.assertTrue(p.eligible_for(base))
        # no player used twice
        ids = [p.dk_id for _, p in lineup.slots]
        self.assertEqual(len(ids), len(set(ids)))

    def test_max_hitters_per_team_enforced(self):
        players = load_sample_slate()
        lineup = optimize(players, max_hitters_per_team=2)
        self.assertIsNotNone(lineup)
        from collections import Counter

        hitters_by_team = Counter(p.team for p in lineup.players if not p.is_pitcher)
        self.assertTrue(all(count <= 2 for count in hitters_by_team.values()))

    def test_infeasible_constraint_returns_none(self):
        players = load_sample_slate()
        # Only 4 teams in the sample slate; capping at 1 hitter/team can't
        # fill 8 hitter slots.
        lineup = optimize(players, max_hitters_per_team=1)
        self.assertIsNone(lineup)

    def test_locked_player_is_included(self):
        players = load_sample_slate()
        target = next(p for p in players if not p.is_pitcher)
        lineup = optimize(players, locked=[target.dk_id])
        self.assertIn(target.dk_id, [p.dk_id for p in lineup.players])

    def test_excluded_player_is_not_included(self):
        players = load_sample_slate()
        target = max((p for p in players if not p.is_pitcher), key=lambda p: p.projection)
        lineup = optimize(players, excluded=[target.dk_id])
        self.assertNotIn(target.dk_id, [p.dk_id for p in lineup.players])

    def test_optimize_multiple_returns_diverse_lineups(self):
        players = load_sample_slate()
        lineups = optimize_multiple(players, 3, max_overlap=8)
        self.assertEqual(len(lineups), 3)
        id_sets = [set(p.dk_id for p in lu.players) for lu in lineups]
        for a, b in itertools.combinations(id_sets, 2):
            self.assertLessEqual(len(a & b), 8)
            self.assertNotEqual(a, b)


class TestDkExportLoader(unittest.TestCase):
    def test_missing_required_column_raises(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.csv"
            path.write_text("Name,Salary\nFoo,5000\n")
            with self.assertRaises(ValueError):
                load_dk_export(path)

    def test_projection_override_by_name(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "slate.csv"
            path.write_text(
                "Position,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\n"
                "C,Foo Bar,1,C,4000,AAA@BBB 7:05PM ET,AAA,5.0\n"
            )
            players = load_dk_export(path, projections={"foo bar": 12.5})
            self.assertEqual(players[0].projection, 12.5)


if __name__ == "__main__":
    unittest.main()
