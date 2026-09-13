import unittest

from q3.models import Point
from q3.offline_policy import Task
from q4.w5pro_local_route import propose_routes


class TestLocalRoutePlanner(unittest.TestCase):
    def setUp(self):
        self.tasks = [
            Task("measure", 1, Point(10.0, 0.0)),
            Task("measure", 2, Point(20.0, 0.0)),
            Task("reacquire", 2, Point(30.0, 0.0)),
        ]

    def test_returns_bounded_routes_with_time_components(self):
        routes = propose_routes(Point(0.0, 0.0), self.tasks,
                                 horizon=3, beam_width=2)
        self.assertTrue(routes)
        self.assertLessEqual(len(routes), 2)
        self.assertEqual(len(routes[0].tasks), 3)
        self.assertAlmostEqual(routes[0].travel_s, 6.0)
        self.assertGreaterEqual(routes[0].switch_s, 1.0)
        self.assertAlmostEqual(routes[0].measure_s, 15.0)

    def test_invalid_parameters_rejected(self):
        with self.assertRaises(ValueError):
            propose_routes(Point(0.0, 0.0), self.tasks, horizon=0)
        with self.assertRaises(ValueError):
            propose_routes(Point(0.0, 0.0), self.tasks, future_discount=1.1)

    def test_transition_can_remove_state_incompatible_successors(self):
        routes = propose_routes(
            Point(0.0, 0.0), self.tasks, horizon=3, beam_width=6,
            transition=lambda prefix, task: not (
                prefix[-1].kind == "reacquire" and task.channel == 1))
        self.assertTrue(routes)
        for route in routes:
            for previous, current in zip(route.tasks, route.tasks[1:]):
                self.assertFalse(previous.kind == "reacquire" and current.channel == 1)


if __name__ == "__main__":
    unittest.main()
