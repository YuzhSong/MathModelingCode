from __future__ import annotations

import unittest

from q3.models import Point
from q4.w5pro_rotation import SkeletonRotationSelector, rotate_points


class W5ProRotationTests(unittest.TestCase):
    def test_rotation_preserves_radius(self):
        p = rotate_points([Point(10, 0)], 30)[0]
        self.assertAlmostEqual(p.x*p.x+p.y*p.y, 100)

    def test_rotation_freezes_after_traversal(self):
        selector = SkeletonRotationSelector()
        selector.select({angle: angle for angle in selector.angles})
        selector.start_traversal()
        with self.assertRaises(RuntimeError):
            selector.select({angle: 0 for angle in selector.angles})


if __name__ == "__main__":
    unittest.main()
