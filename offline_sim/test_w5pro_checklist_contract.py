from __future__ import annotations

import inspect
import importlib
import csv
import json
import math
from pathlib import Path
import unittest

from q3.models import Point
from q4.w5_geometry import W5GeometrySpec, analytic_geometry_checks, w5_detection_points
from q4.w5_policy import W5_SELECTED_SPEC
from q4.w5pro_config import IDENTITY_CONFIG, PRODUCTION_CONFIG
from q4.w5pro_experiment_matrix import ERROR_FIELD_NAMES, STRESS_SUITE_NAMES, full_matrix
from q4.w5pro_safety import LivelockGuard, ProgressSignature, SafetyShield
from q4.w5pro_tasks import W5ProTask
from q4.w5pro_state import W5ProTargetState
from q4.w5pro_clear import ClearLifecycle
from q4.w5pro_hypothesis import HypothesisGrid
from q4.w5pro_observations import adapt_measurement
from q4.w2_policy import TargetLifecycle


class W5ProChecklistContractTests(unittest.TestCase):
    def test_all_w5pro_modules_import_without_runtime_side_effects(self):
        names = (
            "acceptance", "backbone", "clear", "config", "corridor", "diagnostics",
            "experiment_matrix", "feasible", "future_cost", "geometry_sweep", "hypothesis",
            "information_ridge", "metrics", "nbv", "outcomes", "planner", "policy",
            "rotation", "route_repair", "safety", "scheduler", "spatial", "state",
            "tail_fallback", "tasks", "triangle_certificate", "tspn",
        )
        for name in names:
            module = importlib.import_module(f"q4.w5pro_{name}")
            self.assertIsNotNone(module)

    def test_identity_and_production_gates_are_distinct(self):
        gates = ("use_hypothesis", "adaptive_backbone", "use_nbv", "use_task_pool",
                 "use_wait_for_route", "use_spatial_stop", "use_future_cost",
                 "adaptive_scan", "use_tail_rescue", "use_intersection")
        self.assertTrue(all(not getattr(IDENTITY_CONFIG, gate) for gate in gates))
        self.assertTrue(all(getattr(PRODUCTION_CONFIG, gate) for gate in gates))
        self.assertTrue(IDENTITY_CONFIG.identity)
        self.assertFalse(PRODUCTION_CONFIG.identity)
        self.assertFalse(IDENTITY_CONFIG.use_nbv)
        self.assertTrue(PRODUCTION_CONFIG.use_nbv)
        self.assertEqual(IDENTITY_CONFIG.risk_mode, "expected")
        self.assertEqual(IDENTITY_CONFIG.outcome_mode, "robust")
        with self.assertRaises(ValueError):
            type(IDENTITY_CONFIG)(risk_mode="bad")

    def test_fixed_w5_baseline_artifact_matches_checklist_contract(self):
        root = Path(__file__).parents[1]
        artifact = root / "results" / "q4" / "w5_baseline_7case"
        metadata = json.loads((artifact / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["problem"], 4)
        self.assertEqual(metadata["margin_m"], 0.0)
        self.assertEqual(metadata["fixed_detection_point_count"], 25)
        self.assertEqual(metadata["strategies"], ["a970_p140"])
        path = artifact / "summary.csv"
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        overall = next(row for row in rows if row["suite"] == "overall")
        self.assertEqual(int(overall["episodes"]), 7)
        self.assertEqual(float(overall["clear_rate"]), 1.0)
        self.assertAlmostEqual(float(overall["mean_total_time_s"]), 6982.483458, places=3)
        self.assertAlmostEqual(float(overall["mean_reacquisition_attempts"]), 99.714285, places=4)
        self.assertAlmostEqual(float(overall["mean_no_signal_after_found"]), 72.142857, places=4)
        self.assertAlmostEqual(float(overall["mean_intersection_attempts"]), 0.0, places=6)
        with (artifact / "details.csv").open(encoding="utf-8", newline="") as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 7)

    def test_fixed_paired_artifact_has_unique_same_seed_rows(self):
        path = (Path(__file__).parents[1] / "results" / "q4" /
                "w5pro_paired_7case_final" / "paired_comparison.csv")
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        keys = [(r["suite"], r["error_field"], r["seed"]) for r in rows]
        self.assertEqual(len(rows), 7)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(r["w5_clear"] == "1" and r["w5pro_clear"] == "1" for r in rows))
        self.assertTrue(all(float(r["w5_time_s"]) >= 0 and float(r["w5pro_time_s"]) >= 0 for r in rows))

    def test_frozen_geometry_is_unchanged_and_analytically_valid(self):
        self.assertEqual(W5_SELECTED_SPEC.side_m, 970.0)
        self.assertEqual(W5_SELECTED_SPEC.cap_extension_m, 140.0)
        points = w5_detection_points(W5_SELECTED_SPEC)
        self.assertEqual(len(points), 25)
        self.assertEqual(analytic_geometry_checks(W5GeometrySpec(970.0, 140.0))["analytical_pass"], 1)

    def test_matrix_is_formal_and_contains_all_error_fields(self):
        self.assertEqual(len(ERROR_FIELD_NAMES), 5)
        self.assertGreaterEqual(len(STRESS_SUITE_NAMES), 10)
        matrix = full_matrix(seed=17)
        self.assertEqual(len(matrix), (1 + len(STRESS_SUITE_NAMES)) * len(ERROR_FIELD_NAMES))
        self.assertTrue(all(case.mode == "formal" for _, case in matrix))

    def test_matrix_does_not_access_ground_truth_in_strategy_modules(self):
        import q4.w5pro_policy as policy
        source = inspect.getsource(policy)
        self.assertNotIn("case.sources", source)
        self.assertNotIn("ground_truth", source.lower())

    def test_safety_enforces_clear_and_exit_gates(self):
        task = W5ProTask(kind="CLEAR", channel=2, point=Point(0, 0))
        shield = SafetyShield()
        self.assertEqual(shield.filter([task], hard_complete=False, discovered_count=0), [])
        self.assertEqual(shield.filter([task], hard_complete=False, discovered_count=0,
                                       clear_ready_channels={2}), [task])
        self.assertFalse(shield.can_exit(False))
        self.assertTrue(shield.can_exit(True))

    def test_livelock_signature_rotates_and_blacklists_failed_action(self):
        guard = LivelockGuard(no_progress_limit=2)
        sig = ProgressSignature(1, 0, 3, 2, 10.0)
        self.assertFalse(guard.observe(sig))
        self.assertTrue(guard.observe(sig))
        point = Point(20, 40)
        guard.failed_action(2, "ring", point)
        self.assertTrue(guard.is_blacklisted(2, "ring", point))
        self.assertEqual(guard.next_family("ring"), "perpendicular")

    def test_planner_state_does_not_replace_execution_authority(self):
        state = W5ProTargetState(channel=3)
        self.assertEqual(state.lifecycle, TargetLifecycle.ACTIVE)
        self.assertFalse(hasattr(state, "status"))
        self.assertFalse(hasattr(state, "source_type"))
        self.assertTrue(hasattr(state, "mec_center"))
        self.assertTrue(hasattr(state, "region_diameter"))

    def test_clear_requires_ready_and_rejects_immediate_repeat_after_failure(self):
        lifecycle = ClearLifecycle(channel=4)
        point = Point(10, 20)
        self.assertTrue(lifecycle.can_try(point))
        lifecycle.mark_failed(point)
        self.assertFalse(lifecycle.can_try(point))
        other = Point(11, 20)
        self.assertTrue(lifecycle.can_try(other))
        lifecycle.mark_ready(12.5)
        task = lifecycle.task(other)
        self.assertTrue(lifecycle.ready)
        self.assertEqual(task.kind, "CLEAR")
        self.assertEqual(task.meta["clear_ready_time_s"], 12.5)

    def test_hypothesis_grid_is_channel_local_and_conservative(self):
        grid = HypothesisGrid(spacing_m=60.0, heading_bins=36)
        grid.add_channel(1)
        grid.add_channel(2)
        before = grid.alive_count(1)
        grid.update_no_signal(1, Point(0, 0))
        self.assertLess(grid.alive_count(1), before)
        self.assertEqual(grid.alive_count(2), len(grid.cells) * 37)
        far = next(i for i, cell in enumerate(grid.cells)
                   if math.hypot(cell.center.x, cell.center.y) > 1100.0)
        self.assertIn(far, grid._omni[1])

    def test_observation_adapter_exposes_only_public_measurement_kinds(self):
        self.assertEqual(adapt_measurement(None).kind, "NO_SIGNAL")
        self.assertEqual(adapt_measurement(None, clear_result=True).kind, "CLEAR_RESULT")
        self.assertEqual(adapt_measurement(type("M", (), {"result": "near"})()).kind, "NEAR")


if __name__ == "__main__":
    unittest.main()
