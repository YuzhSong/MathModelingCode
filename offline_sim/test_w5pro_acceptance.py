from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from q4.w5pro_acceptance import check


class W5ProAcceptanceTests(unittest.TestCase):
    def _write(self, directory: Path, *, success: str, reason: str) -> None:
        fields = ["total_time_s", "move_time_s", "measure_time_s", "clear_time_s",
                  "channel_switch_time_s", "termination_reason", "success"]
        with (directory / "details.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerow({"total_time_s": "10", "move_time_s": "1", "measure_time_s": "5",
                             "clear_time_s": "4", "channel_switch_time_s": "0",
                             "termination_reason": reason, "success": success})
        (directory / "core_metrics.json").write_text("{}", encoding="utf-8")

    def test_truncated_episode_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name)
            self._write(path, success="0", reason="max_macro_steps")
            self.assertFalse(check(path)["accepted"])

    def test_complete_episode_is_accepted(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name)
            self._write(path, success="1", reason="hard_complete")
            self.assertTrue(check(path)["accepted"])


if __name__ == "__main__":
    unittest.main()
