from __future__ import annotations

import unittest

from q3.models import ChannelStatus, Point
from q4.run_w2_benchmark import assert_w2_ground_truth_isolated
from q4.w2_policy import TargetLifecycle, W2PersistentDirectionalPolicy


class ScriptedRunner:
    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.virtual_time_s = 0.0
        self.position = (0.0, 0.0)
        self.current_channel = 1
        self.diagnostics: list[dict] = []

    def enter(self) -> dict:
        return {"virtual_time_s": 0.0}

    def measure(self, x: float, y: float, channel: int) -> dict:
        response = self.responses.pop(0)
        self.virtual_time_s = float(response["virtual_time_s"])
        self.position = (x, y)
        self.current_channel = channel
        return response

    def clear(self, x: float, y: float, channel: int) -> dict:
        self.position = (x, y)
        return {"virtual_time_s": self.virtual_time_s + 5.0, "clear_result": "success"}

    def exit(self) -> dict:
        return {"virtual_time_s": self.virtual_time_s, "exit_reason": "user_exit"}

    def record_policy_diagnostic(self, event: dict) -> None:
        self.diagnostics.append(dict(event))


class Q4W2LifecycleTests(unittest.TestCase):
    def test_policy_has_no_ground_truth_import_or_access(self) -> None:
        assert_w2_ground_truth_isolated()

    def test_no_signal_after_found_keeps_target_persistent(self) -> None:
        runner = ScriptedRunner(
            [
                {"virtual_time_s": 5.0, "measure_result": "direction", "svd_deg": 15.0},
                {"virtual_time_s": 11.0, "measure_result": "no_signal"},
            ]
        )
        policy = W2PersistentDirectionalPolicy(runner)
        policy.client.enter()
        policy._measure_role = "search_discovery"
        policy.measure_channel(Point(0.0, 0.0), 7)
        self.assertEqual(policy.tracks[7].status, ChannelStatus.FOUND)

        policy._measure_role = "supplement"
        policy.measure_channel(Point(5.0, 0.0), 7)
        self.assertEqual(policy.tracks[7].status, ChannelStatus.FOUND)
        self.assertEqual(policy.target_states[7].lifecycle, TargetLifecycle.REACQUIRE)
        self.assertEqual(len(policy.target_states[7].no_signal_observations), 1)
        self.assertIsNotNone(policy.reacquisition_point(policy.tracks[7], policy.target_states[7]))


if __name__ == "__main__":
    unittest.main()
