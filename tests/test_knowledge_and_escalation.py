import unittest
from pathlib import Path

from app.escalation import classify_escalation
from app.knowledge import KnowledgeBase

ROOT = Path(__file__).resolve().parent.parent


class KnowledgeAndEscalationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.knowledge = KnowledgeBase(ROOT / "knowledge")

    def test_student_search_prefers_authoritative_policy(self):
        hits = self.knowledge.search(
            "student discount verification cooldown final sale", top_k=5
        )

        self.assertTrue(hits)
        self.assertEqual(hits[0]["source"], "discount_policy.md")
        self.assertEqual(hits[0]["authority"], "authoritative_policy_or_playbook")

    def test_natural_delivery_question_retrieves_shipping_knowledge(self):
        hits = self.knowledge.search("How long until my package arrives?", top_k=5)

        self.assertTrue(hits)
        self.assertTrue(
            any(hit["source"] in {"shipping_policy.md", "faq.md"} for hit in hits[:3])
        )

    def test_safety_escalates_urgently(self):
        result = classify_escalation("My camp stove is leaking fuel near the valve.")

        self.assertTrue(result["required"])
        self.assertEqual(result["category"], "safety")
        self.assertEqual(result["priority"], "urgent")

    def test_normal_discount_question_does_not_escalate(self):
        result = classify_escalation("Can I use my student discount on boots?")

        self.assertFalse(result["required"])


if __name__ == "__main__":
    unittest.main()
