from __future__ import annotations

import unittest

from q3.models import Point
from q4.w5pro_safety import LivelockGuard, ProgressSignature, SafetyShield
from q4.w5pro_tasks import W5ProTask


class W5ProSafetyTests(unittest.TestCase):
    def test_exit_requires_hard_completion(self):
        shield = SafetyShield()
        self.assertFalse(shield.can_exit(False))
        self.assertTrue(shield.can_exit(True))

    def test_clear_ready_is_protected_and_search_is_suppressed_after_16(self):
        shield = SafetyShield()
        tasks = [W5ProTask("CLEAR", Point(0, 0), channel=1), W5ProTask("SEARCH", Point(1, 1), search_index=1)]
        filtered = shield.filter(tasks, hard_complete=False, discovered_count=16, clear_ready_channels={1})
        self.assertEqual([t.kind for t in filtered], ["CLEAR"])

    def test_no_progress_guard_blacklists_and_rotates_family(self):
        guard = LivelockGuard(no_progress_limit=2)
        sig = ProgressSignature(1, 0, 10, 2, 100)
        self.assertFalse(guard.observe(sig))
        self.assertTrue(guard.observe(sig))
        p = Point(10, 10)
        guard.failed_action(1, "ring", p)
        self.assertTrue(guard.is_blacklisted(1, "ring", p))
        self.assertEqual(guard.next_family("ring"), "perpendicular")


if __name__ == "__main__":
    unittest.main()
