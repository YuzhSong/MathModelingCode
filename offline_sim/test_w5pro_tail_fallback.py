from __future__ import annotations

import unittest

from q4.w5pro_tail_fallback import TailFallbackController


class W5ProTailFallbackTests(unittest.TestCase):
    def test_w6_is_conditional_and_ordered(self):
        controller = TailFallbackController(no_signal_limit=2)
        self.assertIsNone(controller.choose(nbv_gain=1, route_opportunity=True, no_progress=False))
        self.assertIsNone(controller.choose(nbv_gain=1, route_opportunity=True, no_progress=False, result="no_signal"))
        self.assertEqual(controller.choose(nbv_gain=1, route_opportunity=True, no_progress=False, result="no_signal"), "w6_rescue")
        self.assertEqual(controller.choose(nbv_gain=0, route_opportunity=True, no_progress=False, result="direction"), "w3_coarse")
        self.assertEqual(controller.choose(nbv_gain=1, route_opportunity=False, no_progress=False, result="direction"), "w2_fallback")

    def test_budget_switches_strategy_and_stops_repeating_state(self):
        controller = TailFallbackController(no_signal_limit=1,
                                             per_channel_budget=1,
                                             per_state_budget=1)
        self.assertEqual(controller.choose(nbv_gain=0, route_opportunity=True,
                                           no_progress=False, result="no_signal",
                                           channel=7, state="reacquire"),
                         "w6_rescue")
        self.assertEqual(controller.choose(nbv_gain=0, route_opportunity=True,
                                           no_progress=False, result="no_signal",
                                           channel=7, state="reacquire"),
                         "switch_strategy")
        self.assertIsNone(controller.choose(nbv_gain=0, route_opportunity=True,
                                            no_progress=False, result="no_signal",
                                            channel=7, state="reacquire"))


if __name__ == "__main__":
    unittest.main()
