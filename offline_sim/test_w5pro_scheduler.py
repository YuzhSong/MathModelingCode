from __future__ import annotations

import unittest

from q4.w5pro_scheduler import AdaptiveScanScheduler, AdaptiveScanSession, BacklogState, GlobalMapMaturity, ScanMode


class W5ProSchedulerTests(unittest.TestCase):
    def test_clear_ready_has_higher_backlog_pressure(self):
        self.assertGreater(BacklogState(1, 1, 0, 0).pressure, BacklogState(2, 0, 0, 0).pressure)

    def test_modes_and_must_include_are_respected(self):
        scheduler = AdaptiveScanScheduler(mid_cap=1)
        self.assertEqual(scheduler.update_mode(discovered=0, hard_complete=False, backlog=BacklogState(0, 0, 0, 0)), ScanMode.EARLY)
        scheduler.set_must_include({9, 10})
        selected = scheduler.prioritize({1, 2, 3}, clear_ready={8})
        self.assertTrue({8, 9, 10} <= set(selected))
        self.assertEqual(scheduler.update_mode(discovered=5, hard_complete=True, backlog=BacklogState(0, 0, 0, 0)), ScanMode.VERIFICATION)
        self.assertEqual(scheduler.prioritize({1, 2}, clear_ready=set()), [9, 10])

    def test_map_maturity_is_observation_driven(self):
        maturity = GlobalMapMaturity()
        for channel in range(1, 15):
            maturity.observe(channel)
        self.assertFalse(maturity.mature)
        for channel in range(15, 21):
            maturity.observe(channel)
        self.assertTrue(maturity.mature)

    def test_adaptive_session_never_stops_hard_required_scan(self):
        session = AdaptiveScanSession()
        self.assertTrue(session.should_stop_optional(False, hard_required=False))
        self.assertFalse(session.should_stop_optional(False, hard_required=True))

    def test_clear_ready_and_must_include_preempt_search(self):
        scheduler = AdaptiveScanScheduler(mid_cap=1)
        scheduler.update_mode(discovered=2, hard_complete=False,
                              backlog=BacklogState(2, 1, 0, 0))
        selected = scheduler.prioritize({1, 2, 3}, clear_ready={3}, channel_value={1: 100, 2: 90})
        self.assertEqual(selected[0], 3)
        self.assertIn(3, selected)


if __name__ == "__main__":
    unittest.main()
