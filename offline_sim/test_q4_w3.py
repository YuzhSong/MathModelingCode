from __future__ import annotations

import unittest

from q3.models import ChannelStatus, Point
from q4.run_w3_benchmark import assert_w3_ground_truth_isolated
from q4.w2_policy import TargetLifecycle
from q4.w3_policy import COARSE_MIN_STEP_M, W3CoarseToFinePolicy


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
        self.virtual_time_s += 5.0
        return {"virtual_time_s": self.virtual_time_s, "clear_result": "success"}

    def exit(self) -> dict:
        return {"virtual_time_s": self.virtual_time_s, "exit_reason": "user_exit"}

    def record_policy_diagnostic(self, event: dict) -> None:
        self.diagnostics.append(dict(event))


class Q4W3LocalReacquisitionTests(unittest.TestCase):
    def test_policy_has_no_ground_truth_import_or_access(self) -> None:
        assert_w3_ground_truth_isolated()

    def test_direction_uses_coarse_probe_and_no_signal_keeps_target(self) -> None:
        runner = ScriptedRunner(
            [
                {"virtual_time_s": 5.0, "measure_result": "direction", "svd_deg": 0.0},
                {"virtual_time_s": 110.0, "measure_result": "no_signal"},
            ]
        )
        policy = W3CoarseToFinePolicy(runner, mode="adaptive")
        policy.client.enter()
        policy._measure_role = "search_discovery"
        policy.measure_channel(Point(0.0, 0.0), 7)

        track = policy.tracks[7]
        state = policy.target_states[7]
        probe = policy.reacquisition_point(track, state)
        self.assertIsNotNone(probe)
        assert probe is not None
        self.assertGreaterEqual(probe.x, COARSE_MIN_STEP_M)

        policy._measure_role = "reacquire"
        policy.measure_channel(probe, 7)
        self.assertEqual(track.status, ChannelStatus.FOUND)
        self.assertEqual(state.lifecycle, TargetLifecycle.REACQUIRE)
        self.assertEqual(len(state.no_signal_observations), 1)
        self.assertGreater(policy.local_states[7].failed_coarse_probes, 0)

    def test_successful_coarse_probe_records_outcome(self) -> None:
        runner = ScriptedRunner(
            [
                {"virtual_time_s": 5.0, "measure_result": "direction", "svd_deg": 0.0},
                {"virtual_time_s": 110.0, "measure_result": "direction", "svd_deg": 0.0},
            ]
        )
        policy = W3CoarseToFinePolicy(runner, mode="adaptive")
        policy.client.enter()
        policy._measure_role = "search_discovery"
        policy.measure_channel(Point(0.0, 0.0), 3)
        probe = policy.reacquisition_point(policy.tracks[3], policy.target_states[3])
        assert probe is not None
        policy._measure_role = "reacquire"
        policy.measure_channel(probe, 3)

        self.assertEqual(policy.target_states[3].reacquisition_successes, 1)
        self.assertEqual(policy.local_states[3].successful_coarse_steps, 1)
        outcomes = [row for row in runner.diagnostics if row.get("event") == "w3_probe_outcome"]
        self.assertEqual(outcomes[-1]["result"], "direction")


if __name__ == "__main__":
    unittest.main()
