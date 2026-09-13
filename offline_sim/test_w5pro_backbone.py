from __future__ import annotations

import unittest

from q4.w5pro_backbone import W5BackboneState, anchor_certificate_masks
from q4.w5pro_triangle_certificate import frozen_w5_certificate


class W5ProBackboneTests(unittest.TestCase):
    def test_masks_and_marginal_gain(self):
        points, triangles = frozen_w5_certificate()
        state = W5BackboneState(points)
        masks = anchor_certificate_masks(state, triangles)
        self.assertEqual(len(state.anchors), 25)
        self.assertEqual(len(masks), 25)
        self.assertGreater(state.certificate_marginal_gain(0, {t.triangle_id for t in triangles}), 0)

    def test_ranking_uses_gain_and_debt(self):
        state = W5BackboneState()
        state.set_certificate_masks({0: {1}, 1: {1, 2}})
        state.set_coverage_debt({3: 10.0})
        ranked = state.ranked({1, 2, 3}, travel_time_s=1, scan_time_s=1)
        self.assertEqual(ranked[1].index, 0)
        self.assertEqual(ranked[0].index, 1)

    def test_required_anchors_cannot_be_deleted_early(self):
        state = W5BackboneState()
        self.assertEqual(len(state.required_indices(5, False)), 25)
        self.assertEqual(state.required_indices(16, False), set())
        self.assertEqual(state.required_indices(5, True), set())

    def test_visited_channel_has_zero_channel_gain(self):
        state = W5BackboneState()
        state.set_certificate_masks({0: {7}})
        self.assertEqual(state.channel_gain(0, 7), 1.0)
        state.mark_visited(0, 7)
        self.assertEqual(state.channel_gain(0, 7), 0.0)


if __name__ == "__main__":
    unittest.main()
