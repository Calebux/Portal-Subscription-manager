#!/usr/bin/env python3
"""
Regression tests for sub_store.merge_subscription — the fix for the bug
where gmail-scanner.py silently overwrote scanned-subscriptions.json on
every scan, wiping user edits and price history.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sub_store


class TestMergeSubscription(unittest.TestCase):
    def test_new_subscription_is_appended(self):
        result = sub_store.merge_subscription([], {"id": "netflix", "monthly_cost": 9.99})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "netflix")

    def test_user_edited_fields_survive_a_rescan(self):
        existing = [{
            "id": "netflix", "name": "Netflix", "monthly_cost": 9.99, "currency": "USD",
            "status": "active", "health_score": 42, "use_case": "personal",
            "notes": "my custom note", "category": "streaming",
        }]
        new_scan = {
            "id": "netflix", "name": "Netflix", "monthly_cost": 9.99, "currency": "USD",
            "status": "active", "health_score": 70, "use_case": "",
            "notes": "Auto-detected", "category": "other",
        }
        result = sub_store.merge_subscription(existing, new_scan)
        merged = result[0]
        self.assertEqual(merged["health_score"], 42)
        self.assertEqual(merged["use_case"], "personal")
        self.assertEqual(merged["notes"], "my custom note")
        self.assertEqual(merged["category"], "streaming")

    def test_price_change_appends_to_history(self):
        existing = [{
            "id": "netflix", "monthly_cost": 9.99, "currency": "USD",
            "last_used": "2026-06-06", "price_history": [],
        }]
        new_scan = {"id": "netflix", "monthly_cost": 12.99, "currency": "USD"}
        result = sub_store.merge_subscription(existing, new_scan)
        merged = result[0]
        self.assertEqual(merged["monthly_cost"], 12.99)
        self.assertEqual(len(merged["price_history"]), 1)
        self.assertEqual(merged["price_history"][0]["amount"], 9.99)
        self.assertIn("price_changed_at", merged)

    def test_unchanged_price_does_not_append_history(self):
        existing = [{"id": "netflix", "monthly_cost": 9.99, "currency": "USD", "price_history": []}]
        new_scan = {"id": "netflix", "monthly_cost": 9.99, "currency": "USD"}
        result = sub_store.merge_subscription(existing, new_scan)
        self.assertEqual(result[0]["price_history"], [])
        self.assertNotIn("price_changed_at", result[0])

    def test_other_source_subscriptions_are_preserved(self):
        existing = [{"id": "csv-imported-sub", "monthly_cost": 5.0, "source": "csv-import"}]
        new_scan = {"id": "netflix", "monthly_cost": 9.99, "source": "gmail-scan"}
        result = sub_store.merge_subscription(existing, new_scan)
        ids = {s["id"] for s in result}
        self.assertEqual(ids, {"csv-imported-sub", "netflix"})


if __name__ == "__main__":
    unittest.main()
