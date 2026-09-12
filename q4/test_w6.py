from __future__ import annotations

import unittest
from dataclasses import asdict

from offline_sim.harness import run_episode
from q3.models import Point, Measurement
from q4.run_w6_benchmark import assert_isolated, normal_case
from q4.stress_cases import tail_stress_cases
from q4.tail_robustness import longitudinal_extent, ObservedW5Policy
from q4.w5_policy import W5SymmetricDetectionPolicy
from q4.w6_policy import W6Policy
from q4.w2_policy import TargetLifecycle


class MinimalRunner:
    def record_policy_diagnostic(self,event): pass


class W6Tests(unittest.TestCase):
    def test_isolation(self):
        assert_isolated()

    def test_extent(self):
        self.assertEqual(longitudinal_extent([Point(100,-10),Point(300,10)],Point(0,0),0),(100,300))
        self.assertEqual(longitudinal_extent([],Point(0,0),0),(None,None))

    def test_disabled_and_observer_reproduce_baseline_actions(self):
        results=[]
        for cls in (W5SymmetricDetectionPolicy,ObservedW5Policy,lambda runner: W6Policy(runner,"disabled")):
            r=run_episode(normal_case("random",0),lambda runner:cls(runner).run(),include_oracles=False)
            self.assertTrue(r.success,r.error)
            self.assertEqual(r.n_clear_fail,0)
            results.append(([asdict(a) for a in r.action_log],r.virtual_time_s))
        self.assertEqual(results[0],results[1])
        self.assertEqual(results[0],results[2])

    def test_geometry_and_router_unchanged(self):
        w5=W5SymmetricDetectionPolicy(MinimalRunner())
        for variant in ("w6a","w6b","w6c"):
            w6=W6Policy(MinimalRunner(),variant)
            self.assertEqual(w5.search_points,w6.search_points)
            self.assertEqual(w5.routing_method,w6.routing_method)
            self.assertEqual(w5.max_steps,w6.max_steps)

    def test_failed_acceleration_cannot_repeat_without_new_bearing(self):
        w6=W6Policy(MinimalRunner(),"w6a")
        track=w6.tracks[1]
        track.add_measurement(Measurement(Point(0,0),1,"direction",0.0,1))
        track.add_measurement(Measurement(Point(10,0),1,"direction",0.0,2))
        w6.localization_state=lambda track:([Point(1000,-10),Point(1050,10)],None)
        w6.local_states[1].step_m=5.0
        state=w6.target_states[1]; state.lifecycle=TargetLifecycle.REACQUIRE
        w6.reacquisition_point(track,state)
        self.assertEqual(w6._probe_plans[1].kind,"geometry")
        w6._accelerated_observations.add((1,2))
        w6.reacquisition_point(track,state)
        self.assertNotEqual(w6._probe_plans[1].kind,"geometry")
        self.assertEqual(track.status.value,"found")

    def test_fixtures_deterministic_and_legal(self):
        first=tail_stress_cases(); second=tail_stress_cases()
        self.assertEqual([c.to_json() for _,_,c,_ in first],[c.to_json() for _,_,c,_ in second])
        self.assertEqual(len(first),24)
        for _,_,case,_ in first:
            self.assertTrue(10<=case.total<=16)
            self.assertGreater(case.n_dir,0)
            self.assertGreater(case.n_omni,0)
            self.assertTrue(all(j.x*j.x+j.y*j.y<=1800**2+1e-6 for j in case.jammers))

    def test_failed_rescue_explicitly_defers_without_dropping_target(self):
        w6=W6Policy(MinimalRunner(),"w6b")
        track=w6.tracks[1]
        track.add_measurement(Measurement(Point(0,0),1,"direction",0,1))
        w6._defer_after_rescue(1)
        self.assertEqual(w6.target_states[1].lifecycle,TargetLifecycle.DEFERRED)
        self.assertEqual(track.status.value,"found")
        self.assertEqual(w6.target_states[1].resume_after_search_count,1)
        w6.remaining_search_indices.clear()
        tasks=w6.build_dynamic_tasks()
        self.assertTrue(any(t.channel==1 for t in tasks))


if __name__=="__main__": unittest.main()
