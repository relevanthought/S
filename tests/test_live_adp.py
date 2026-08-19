import unittest

from bestball.live_adp import load_live_adp, normalize_name


class TestLiveAdp(unittest.TestCase):
    def test_normalize_strips_punctuation_and_suffixes(self):
        self.assertEqual(normalize_name("Ja'Marr Chase"), "jamarr chase")
        self.assertEqual(normalize_name("A.J. Brown"), "aj brown")
        self.assertEqual(normalize_name("Kenneth Walker III"), "kenneth walker")
        self.assertEqual(normalize_name("Marvin Harrison Jr."), "marvin harrison")
        self.assertEqual(normalize_name("Jaxon Smith-Njigba"), "jaxon smith njigba")

    def test_known_aliases_resolve_to_same_key(self):
        self.assertEqual(normalize_name("Kenny Gainwell"), normalize_name("Kenneth Gainwell"))
        self.assertEqual(normalize_name("Chig Okonkwo"), normalize_name("Chigoziem Okonkwo"))

    def test_load_live_adp_returns_lower_is_earlier(self):
        table = load_live_adp()
        self.assertGreater(len(table), 400)
        gibbs = table[(normalize_name("Jahmyr Gibbs"), "RB")]
        chase = table[(normalize_name("Ja'Marr Chase"), "WR")]
        self.assertLess(gibbs, chase)  # Gibbs (ADP 1.1) went before Chase (ADP 3.0)


if __name__ == "__main__":
    unittest.main()
