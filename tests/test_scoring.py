import unittest

from bestball.scoring import dk_points


class TestDkScoring(unittest.TestCase):
    def test_qb_stat_line(self):
        row = {
            "passing_yards": 320,
            "passing_tds": 3,
            "interceptions": 1,
            "passing_2pt_conversions": 0,
            "rushing_yards": 10,
            "rushing_tds": 0,
            "rushing_2pt_conversions": 0,
            "receptions": 0,
            "receiving_yards": 0,
            "receiving_tds": 0,
            "receiving_2pt_conversions": 0,
            "sack_fumbles_lost": 0,
            "rushing_fumbles_lost": 1,
            "receiving_fumbles_lost": 0,
            "special_teams_tds": 0,
        }
        # 320*0.04=12.8 + 3*4=12 + 1*-1=-1 + 300yd bonus 3 + 10*0.1=1 + fumble -1
        expected = 12.8 + 12 - 1 + 3 + 1.0 - 1
        self.assertAlmostEqual(dk_points(row), round(expected, 2))

    def test_wr_stat_line_with_bonus(self):
        row = {
            "receptions": 10,
            "receiving_yards": 145,
            "receiving_tds": 2,
            "receiving_2pt_conversions": 1,
        }
        # 10 rec = 10, 145*0.1=14.5, 2 TD=12, 100yd bonus=3, 2pt=2
        expected = 10 + 14.5 + 12 + 3 + 2
        self.assertAlmostEqual(dk_points(row), round(expected, 2))

    def test_empty_stat_line_scores_zero(self):
        self.assertEqual(dk_points({}), 0.0)

    def test_no_bonus_under_threshold(self):
        row = {"rushing_yards": 99, "rushing_tds": 1}
        expected = 99 * 0.1 + 6  # no 100-yard bonus
        self.assertAlmostEqual(dk_points(row), round(expected, 2))


if __name__ == "__main__":
    unittest.main()
