from __future__ import annotations

import unittest

from q3.models import Point
from q4.w5pro_hypothesis import HypothesisGrid
from q4.w5pro_nbv import NBVCandidate, generate_candidates, score_candidates, select_minimax


class W5ProNBVTests(unittest.TestCase):
    def test_candidate_families_and_outside_arena_are_kept(self):
        current = Point(0.0, 0.0)
        candidates = generate_candidates(current, mec_center=Point(1, 1),
                                         region_centroid=Point(2, 2), bearing_deg=0,
                                         backbone_points=[Point(3, 3)], route_points=[Point(4, 4)])
        families = {c.family for c in candidates}
        self.assertTrue({"mec_center", "region_centroid", "ring", "perpendicular",
                         "backbone_opportunity", "route_waypoint"} <= families)
        self.assertTrue(any(c.point.x > 1000 for c in candidates))

    def test_identical_prior_viewpoint_is_pruned(self):
        p = Point(400.0, 0.0)
        candidates = generate_candidates(Point(0, 0), previous_points=[p])
        self.assertFalse(any(c.point == p for c in candidates))

    def test_minimax_score_has_required_diagnostics(self):
        grid = HypothesisGrid()
        candidate = select_minimax([NBVCandidate(Point(400, 0), "ring")], grid, 1, Point(0, 0))
        self.assertIsNotNone(candidate)
        self.assertGreaterEqual(candidate.miss_rate, 0.0)
        self.assertGreaterEqual(candidate.travel_time_s, 0.0)
        self.assertGreaterEqual(candidate.score, 0.0)

    def test_minimax_degrades_to_none_without_candidates_instead_of_blocking(self):
        grid = HypothesisGrid()
        self.assertIsNone(select_minimax([], grid, 1, Point(0, 0)))

    def test_crossing_quality_affects_candidate_score(self):
        grid = HypothesisGrid()
        good = NBVCandidate(Point(400, 0), "intersection", meta={"crossing_quality": 1.0})
        poor = NBVCandidate(Point(400, 0), "intersection", meta={"crossing_quality": 0.0})
        ranked = score_candidates([poor, good], grid, 1, Point(0, 0))
        self.assertIs(ranked[0], good)

    def test_novelty_penalty_prefers_viewpoint_farther_from_history(self):
        grid = HypothesisGrid()
        history = [Point(0, 0)]
        near = NBVCandidate(Point(10, 0), "ring")
        far = NBVCandidate(Point(100, 0), "ring")
        ranked = score_candidates([near, far], grid, 1, Point(500, 500),
                                   prior_points=history, lambda_novelty=100.0)
        self.assertIs(ranked[0], far)


if __name__ == "__main__":
    unittest.main()
