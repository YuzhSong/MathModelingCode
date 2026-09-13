from __future__ import annotations

import unittest

from q4.w5pro_diagnostics import collect_diagnostics


class W5ProDiagnosticsTests(unittest.TestCase):
    def test_required_event_fields_and_fallback_rate(self):
        events = [{"event": "w5pro_nbv_selected"}, {"event": "w5pro_nbv_effective"},
                  {"event": "w5pro_legacy_backbone_fallback"}]
        result = collect_diagnostics(events, decisions=4)
        self.assertEqual(result.counts["nbv_selected_count"], 1)
        self.assertEqual(result.counts["nbv_effective_count"], 1)
        self.assertEqual(result.fallback_count, 1)
        self.assertEqual(result.fallback_rate, 0.25)


if __name__ == "__main__":
    unittest.main()
