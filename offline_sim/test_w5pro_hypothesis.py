from __future__ import annotations

import math
import random
import unittest

from q3.models import Point
from q4.w5pro_hypothesis import HypothesisGrid


class HypothesisGridTests(unittest.TestCase):
    def test_random_far_source_cells_survive_conservative_negative_updates(self):
        rng = random.Random(20260913)
        grid = HypothesisGrid(spacing_m=60.0)
        grid.add_channel(7)
        candidates = [i for i, cell in enumerate(grid.cells)
                      if 1200.0 < math.hypot(cell.center.x, cell.center.y) < 1700.0]
        for index in rng.sample(candidates, 12):
            source = grid.cells[index].center
            observer = Point(0.0, 0.0)
            grid.update_no_signal(7, observer)
            self.assertIn(index, grid._omni[7], msg=f"removed legal source cell {source}")
    def test_no_signal_preserves_a_legal_far_source_cell(self):
        grid = HypothesisGrid(spacing_m=60.0)
        grid.add_channel(1)
        source = next(cell for cell in grid.cells
                      if 1100.0 < math.hypot(cell.center.x, cell.center.y) < 1500.0)
        index = grid.cells.index(source)
        grid.update_no_signal(1, Point(0.0, 0.0))
        self.assertIn(index, grid._omni[1])
    def test_boundary_cells_are_retained(self):
        grid = HypothesisGrid()
        self.assertTrue(any(math.hypot(c.center.x, c.center.y) > 1800 for c in grid.cells))

    def test_no_signal_uses_guaranteed_radius_not_upper_radius(self):
        grid = HypothesisGrid(spacing_m=60.0)
        grid.add_channel(1)
        before = grid.alive_count(1)
        grid.update_no_signal(1, Point(0.0, 0.0))
        self.assertLess(grid.alive_count(1), before)
        # A cell whose corners are outside 1000m must remain possible.
        far = next(i for i, c in enumerate(grid.cells) if math.hypot(c.center.x, c.center.y) > 1100)
        self.assertIn(far, grid._omni[1])

    def test_random_observers_preserve_cells_outside_guaranteed_certificate(self):
        rng = random.Random(314159)
        grid = HypothesisGrid(spacing_m=60.0)
        grid.add_channel(4)
        for _ in range(20):
            observer = Point(rng.uniform(-1800, 1800), rng.uniform(-1800, 1800))
            safe = [i for i, cell in enumerate(grid.cells) if i in grid._omni[4]
                    if max(math.hypot(p.x-observer.x, p.y-observer.y) for p in cell.corners)
                    > grid.guaranteed_radius_m]
            grid.update_no_signal(4, observer)
            self.assertTrue(set(safe).issubset(grid._omni[4]))

    def test_bearing_and_near_reduce_hypotheses(self):
        grid = HypothesisGrid()
        grid.add_channel(1)
        before = grid.alive_count(1)
        grid.update_bearing(1, Point(0.0, 0.0), 0.0)
        self.assertLess(grid.alive_count(1), before)
        before_near = grid.alive_count(1)
        grid.update_near(1, Point(100.0, 0.0))
        self.assertLessEqual(grid.alive_count(1), before_near)

    def test_directional_no_signal_uses_both_heading_bin_edges(self):
        grid = HypothesisGrid(spacing_m=60.0, heading_bins=36)
        grid.add_channel(9)
        before = {h: set(values) for h, values in grid._directional[9].items()}
        grid.update_no_signal(9, Point(0.0, 0.0))
        self.assertEqual(set(before), set(range(36)))
        self.assertTrue(all(grid._directional[9][h] <= before[h] for h in range(36)))
        self.assertTrue(any(grid._directional[9][h] != before[h] for h in range(36)))


if __name__ == "__main__":
    unittest.main()
