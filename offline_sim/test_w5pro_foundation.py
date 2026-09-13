from __future__ import annotations

import unittest

from q4.w5_geometry import W5GeometrySpec, w5_detection_points
from q4.w5_policy import W5_SELECTED_SPEC
from q4.w5pro_config import IDENTITY_CONFIG, W5ProConfig
from q4.w5pro_policy import W5ProPolicy


class MinimalRunner:
    virtual_time_s = 0.0
    position = (0.0, 0.0)
    current_channel = 1


class W5ProFoundationTests(unittest.TestCase):
    def test_identity_config_has_all_gates_off(self):
        self.assertTrue(IDENTITY_CONFIG.identity)
        self.assertEqual(IDENTITY_CONFIG, W5ProConfig())

    def test_identity_preserves_selected_geometry(self):
        policy = W5ProPolicy(MinimalRunner())
        self.assertTrue(policy.config.identity)
        self.assertEqual(policy.search_points, w5_detection_points(W5_SELECTED_SPEC))
        self.assertEqual(len(policy.search_points), 25)
        self.assertEqual(policy.geometry_spec, W5GeometrySpec(970.0, 140.0))

    def test_non_identity_is_explicit(self):
        policy = W5ProPolicy(MinimalRunner(), W5ProConfig(use_nbv=True))
        self.assertFalse(policy.config.identity)
        self.assertEqual(policy.variant, "w5pro")


if __name__ == "__main__":
    unittest.main()
