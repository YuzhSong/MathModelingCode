from __future__ import annotations

import unittest

from q3.models import Point
from q4.w5pro_nbv import NBVCandidate
from q4.w5pro_tspn import sample_neighborhood


class W5ProTSPNTests(unittest.TestCase):
    def test_discrete_neighborhood_samples_only_qualified_candidates(self):
        good = NBVCandidate(Point(10, 0), "intersection", visible_fraction=.8,
                            information_gain=.4, meta={"crossing_quality": .9})
        bad = NBVCandidate(Point(20, 0), "intersection", visible_fraction=.05,
                           information_gain=.4, meta={"crossing_quality": .9})
        neighborhood = sample_neighborhood(2, [good, bad])
        self.assertEqual(neighborhood.candidates, (good,))
        self.assertIs(neighborhood.nearest_to(Point(0, 0)), good)

    def test_neighborhood_thresholds_are_explicit(self):
        neighborhood = sample_neighborhood(1, [], visibility_threshold=.3,
                                           crossing_threshold=.4, gain_threshold=.2)
        self.assertEqual((neighborhood.visibility_threshold,
                          neighborhood.crossing_threshold,
                          neighborhood.gain_threshold), (.3, .4, .2))


if __name__ == "__main__":
    unittest.main()
