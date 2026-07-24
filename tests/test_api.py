from datetime import date
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from app.config import Settings
from app.data_store import DataStore
from app.knowledge import KnowledgeBase
from app.main import create_app


ROOT = Path(__file__).resolve().parent.parent


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = Settings(
            anthropic_api_key=None,
            claude_model="test-model",
            max_tokens=500,
            max_tool_rounds=3,
            request_timeout_seconds=10.0,
            support_api_key=None,
            cors_origins=(),
            data_dir=ROOT / "data",
            knowledge_dir=ROOT / "knowledge",
        )
        cls.store = DataStore(ROOT / "data", today=date(2026, 7, 23))
        cls.knowledge = KnowledgeBase(ROOT / "knowledge")
        cls.client = TestClient(
            create_app(cls.settings, cls.store, cls.knowledge)
        )

    def test_health_explains_missing_claude_configuration(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "needs_configuration")
        self.assertFalse(body["claude_configured"])
        self.assertEqual(body["data"]["orders"], 40)

    def test_public_catalog_search(self):
        response = self.client.get(
            "/v1/catalog/search", params={"q": "Trailrunner shoes"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["products"][0]["product_id"], "TSC-1011"
        )

    def test_demo_scenarios_endpoint(self):
        response = self.client.get("/v1/demo/scenarios")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()["scenarios"]), 7)

    def test_chat_rejects_invalid_email(self):
        response = self.client.post(
            "/v1/support/chat",
            json={"message": "Where is order 1032?", "customer_email": "not-an-email"},
        )

        self.assertEqual(response.status_code, 422)

    def test_chat_rejects_unknown_response_detail(self):
        response = self.client.post(
            "/v1/support/chat",
            json={
                "message": "Where is order 1032?",
                "customer_email": "liam.carter@example.com",
                "response_detail": "extremely_long",
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_chat_without_claude_key_returns_safe_configuration_error(self):
        response = self.client.post(
            "/v1/support/chat",
            json={
                "message": "Where is order 1032?",
                "customer_email": "liam.carter@example.com",
            },
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("ANTHROPIC_API_KEY", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
