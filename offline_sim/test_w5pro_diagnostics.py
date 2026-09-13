from __future__ import annotations

import unittest

from q4.w5pro_diagnostics import collect_diagnostics


class W5ProDiagnosticsTests(unittest.TestCase):
    def test_required_event_fields_and_fallback_rate(self):
        events = [{"event": "w5pro_nbv_selected"}, {"event": "w5pro_nbv_effective", "applied": True},
                  {"event": "w5pro_legacy_backbone_fallback"}]
        result = collect_diagnostics(events, decisions=4)
        self.assertEqual(result.counts["nbv_selected_count"], 1)
        self.assertEqual(result.counts["nbv_effective_count"], 1)
        self.assertEqual(result.fallback_count, 1)
        self.assertEqual(result.fallback_rate, 0.25)

    def test_rejected_information_actions_do_not_count_as_effective(self):
        events = [
            {"event": "w5pro_nbv_selected"},
            {"event": "w5pro_nbv_effective", "applied": False},
            {"event": "w5pro_intersection_selected", "applied": False},
            {"event": "w5pro_route_repair", "repair_needed": False},
        ]
        result = collect_diagnostics(events)
        self.assertEqual(result.counts["nbv_selected_count"], 1)
        self.assertEqual(result.counts["nbv_effective_count"], 0)
        self.assertEqual(result.counts["intersection_selected_count"], 0)
        self.assertEqual(result.counts["route_repair_count"], 0)


if __name__ == "__main__":
    unittest.main()
