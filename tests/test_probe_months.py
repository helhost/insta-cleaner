import unittest
from tools.probe_months import ranges, compare


class MonthProbeTests(unittest.TestCase):
    def test_calendar_boundaries(self):
        self.assertEqual(
            ranges("2024-12-01"),
            [("2024-12-01", "2025-01-01"), ("2025-01-01", "2025-02-01")],
        )
        with self.assertRaises(ValueError):
            ranges("2024-12-02")

    def test_overlap_deduplicates_but_missing_items_and_limits_fail(self):
        b = {"ids": ["1", "2", "3"], "reason": "no next instruction"}
        parts = [
            {"ids": ["1", "2"], "reason": "no next instruction"},
            {"ids": ["2", "3"], "reason": "no next instruction"},
        ]
        self.assertTrue(compare(b, parts, parts)["comparison_passed"])
        self.assertEqual(compare(b, parts, parts)["boundary_overlap"], 1)
        self.assertFalse(
            compare({**b, "reason": "page limit"}, parts, parts)["comparison_passed"]
        )
        self.assertFalse(
            compare({**b, "ids": ["4"]}, parts, parts)["comparison_passed"]
        )
