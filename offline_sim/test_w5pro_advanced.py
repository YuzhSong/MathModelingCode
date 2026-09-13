from __future__ import annotations

import unittest

from q3.models import Point
from q4.w5pro_hypothesis import HypothesisGrid
from q4.w5pro_nbv import NBVCandidate
from q4.w5pro_outcomes import outcome_probabilities
from q4.w5pro_tspn import sample_neighborhood


class W5ProAdvancedTests(unittest.TestCase):
    def test_outcomes_are_probability_distribution_and_not_certificate(self):
        result = outcome_probabilities(HypothesisGrid(), 1, Point(0, 0))
        self.assertAlmostEqual(result.no_signal + result.bearing + result.near, 1.0)
        self.assertGreaterEqual(result.no_signal, 0)

    def test_tspn_neighborhood_selects_only_qualified_points(self):
        good = NBVCandidate(Point(1, 1), "perpendicular", visible_fraction=.8, information_gain=.5, meta={"crossing_quality": .8})
        bad = NBVCandidate(Point(2, 2), "ring", visible_fraction=.01, information_gain=.01)
        neighborhood = sample_neighborhood(1, [good, bad])
        self.assertEqual(neighborhood.candidates, (good,))


if __name__ == "__main__":
    unittest.main()
