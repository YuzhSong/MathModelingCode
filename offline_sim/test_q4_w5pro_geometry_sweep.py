from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from q4.w5pro_geometry_sweep import constrained_sweep, write_sweep


class W5ProGeometrySweepTests(unittest.TestCase):
    def test_sweep_is_constrained_and_reproducible(self):
        rows = constrained_sweep([970, 990], [140, 160])
        self.assertEqual(len(rows), 4)
        self.assertTrue(any(row["analytical_pass"] for row in rows))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "geometry.csv"
            written = write_sweep(path, [970], [140])
            self.assertTrue(path.exists())
            self.assertEqual(written[0]["side_m"], 970.0)


if __name__ == "__main__":
    unittest.main()
