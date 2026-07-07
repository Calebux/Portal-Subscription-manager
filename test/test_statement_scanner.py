#!/usr/bin/env python3
"""
Regression test for statement-scanner.detect_recurring's amount-stability
check. It originally compared each transaction against the *full-history*
average, so a genuine mid-history price increase made the whole merchant
look "unstable" and get rejected — exactly backwards for price-hike
detection. Fixed to check the two most recent occurrences instead.
"""

import sys
import importlib.util
import unittest
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "statement_scanner", Path(__file__).resolve().parent.parent / "statement-scanner.py"
)
statement_scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(statement_scanner)


def txn(date_str, amount):
    return {
        "merchant": "NETFLIX.COM 866-579-7172",
        "raw_description": "NETFLIX.COM 866-579-7172",
        "amount": amount,
        "date": datetime.strptime(date_str, "%Y-%m-%d"),
    }


class TestDetectRecurring(unittest.TestCase):
    def test_stable_monthly_charge_is_detected(self):
        txns = [txn("2026-04-06", 9.99), txn("2026-05-06", 9.99), txn("2026-06-06", 9.99)]
        candidates = statement_scanner.detect_recurring(txns)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["amount"], 9.99)
        self.assertEqual(candidates[0]["cycle"], "monthly")

    def test_price_hike_partway_through_is_still_detected_at_new_price(self):
        txns = [
            txn("2026-04-06", 9.99), txn("2026-05-06", 9.99),
            txn("2026-06-06", 12.99), txn("2026-07-06", 12.99),
        ]
        candidates = statement_scanner.detect_recurring(txns)
        self.assertEqual(len(candidates), 1, "a mid-history price change must not reject the whole merchant")
        self.assertEqual(candidates[0]["amount"], 12.99, "should reflect the current (most recent) price")

    def test_one_off_purchases_are_not_flagged_recurring(self):
        txns = [txn("2026-04-06", 42.10)]
        candidates = statement_scanner.detect_recurring(txns)
        self.assertEqual(candidates, [])

    def test_irregular_amounts_at_monthly_spacing_are_not_flagged(self):
        # Same merchant, ~monthly spacing, but wildly different amounts each
        # time (e.g. a grocery store) — should not be treated as a subscription.
        txns = [
            {**txn("2026-04-06", 20.0), "merchant": "WHOLE FOODS"},
            {**txn("2026-05-06", 85.0), "merchant": "WHOLE FOODS"},
            {**txn("2026-06-06", 12.0), "merchant": "WHOLE FOODS"},
        ]
        candidates = statement_scanner.detect_recurring(txns)
        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
