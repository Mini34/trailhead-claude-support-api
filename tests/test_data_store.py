import unittest
from datetime import date
from pathlib import Path

from app.data_store import DataStore

ROOT = Path(__file__).resolve().parent.parent


class DataStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = DataStore(ROOT / "data", today=date(2026, 7, 23))

    def test_order_lookup_requires_matching_customer(self):
        verified = self.store.lookup_order(1033, "sofia.nguyen@example.com")
        denied = self.store.lookup_order(1033, "liam.carter@example.com")

        self.assertEqual(verified["status"], "verified")
        self.assertEqual(verified["shipment"]["delivered_date"], "2026-07-18")
        self.assertEqual(denied["status"], "verification_required")
        self.assertNotIn("order", denied)

    def test_delivery_estimate_explains_timing_and_status(self):
        result = self.store.get_delivery_estimate(1032, "liam.carter@example.com")

        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["shipment_status"], "Processing")
        self.assertEqual(result["estimated_delivery"], "2026-07-31")
        self.assertEqual(result["calendar_days_until_estimate"], 8)
        self.assertEqual(result["timing"], "estimated_in_days")
        self.assertIn("being packed", result["what_status_means"])

    def test_student_discount_calculation(self):
        result = self.store.check_discount_eligibility(
            "STUDENT15",
            "sofia.nguyen@example.com",
            [{"product_id": "TSC-1011", "quantity": 1}],
        )

        self.assertEqual(result["status"], "eligible")
        self.assertEqual(result["eligible_subtotal"], 129.00)
        self.assertEqual(result["estimated_discount"], 19.35)
        self.assertEqual(result["estimated_discounted_subtotal"], 109.65)

    def test_student_discount_cooldown(self):
        result = self.store.check_discount_eligibility(
            "STUDENT15", "ava.bennett@example.com"
        )

        self.assertEqual(result["status"], "cooldown")
        self.assertEqual(result["next_eligible_date"], "2026-08-09")

    def test_expired_student_verification(self):
        result = self.store.check_discount_eligibility(
            "STUDENT15", "mia.thompson@example.com"
        )

        self.assertEqual(result["status"], "verification_required")
        self.assertEqual(result["verification_status"], "expired")

    def test_trail_club_footwear_return(self):
        result = self.store.check_return_eligibility(
            1033,
            "TSC-1011",
            "sofia.nguyen@example.com",
            item_condition="tried_on_indoors",
            issue_type="preference_return",
        )

        self.assertEqual(result["status"], "eligible")
        self.assertEqual(result["return_window_days"], 60)
        self.assertEqual(result["return_deadline"], "2026-09-16")

    def test_standard_return_window_ended(self):
        result = self.store.check_return_eligibility(
            1038,
            "TSC-1018",
            "jack.rivera@example.com",
            item_condition="unused_with_tags",
            issue_type="preference_return",
        )

        self.assertEqual(result["status"], "not_eligible")
        self.assertEqual(result["reason"], "return_window_ended")

    def test_final_sale_defect_routes_to_warranty(self):
        result = self.store.check_return_eligibility(
            1036,
            "TSC-1003",
            "ethan.park@example.com",
            issue_type="manufacturing_defect",
        )

        self.assertEqual(result["status"], "warranty_review")
        self.assertTrue(result["is_final_sale"])
        self.assertEqual(result["warranty_months"], 24)


if __name__ == "__main__":
    unittest.main()
