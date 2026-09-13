from __future__ import annotations

import unittest

from q3.models import Point
from q4.w5pro_information_ridge import CandidateFeatures, build_ridges, pareto_prune
from q4.w5pro_tasks import W5ProTask


class W5ProInformationTests(unittest.TestCase):
    def test_ridge_requires_shared_multi_channel_gain(self):
        ridges = build_ridges([Point(0, 0), Point(100, 0)], [1, 2], lambda p, c: 1 if p.x == 0 or c == 1 else 0, lambda p: 10)
        self.assertEqual(len(ridges), 1)
        self.assertEqual(ridges[0].channels, (1, 2))

    def test_pareto_pruning_protects_mandatory_and_clear(self):
        a = W5ProTask("REFINE", Point(0, 0), channel=1)
        b = W5ProTask("REFINE", Point(1, 0), channel=2)
        clear = W5ProTask("CLEAR", Point(2, 0), channel=3)
        mandatory = W5ProTask("VERIFY", Point(3, 0), mandatory=True)
        f = {id(a): CandidateFeatures(10, 0, 1, 0, 0), id(b): CandidateFeatures(5, 1, 2, 1, 1)}
        out = pareto_prune([a, b, clear, mandatory], f)
        self.assertNotIn(a, out)
        self.assertTrue({id(b), id(clear), id(mandatory)} <= {id(item) for item in out})


if __name__ == "__main__":
    unittest.main()
