from __future__ import annotations

import unittest

from q4.w5pro_metrics import summarize_sources


class W5ProMetricsTests(unittest.TestCase):
    def test_core_metrics_follow_requested_formulas(self):
        sources = [{"cleared": "1", "found_to_clear_s": "10"}, {"cleared": "1", "found_to_clear_s": "20"}, {"cleared": "0", "found_to_clear_s": ""}]
        details = [{"total_time_s": "100"}]
        result = summarize_sources(sources, details)
        self.assertEqual(result["clear_ratio"], 2 / 3)
        self.assertEqual(result["total_localization_clear_time_s"], 30.0)
        self.assertEqual(result["mean_localization_clear_time_s"], 15.0)
        self.assertEqual(result["episode_time_per_cleared_source_s"], 50.0)


if __name__ == "__main__":
    unittest.main()
