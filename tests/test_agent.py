from datetime import date
from pathlib import Path
from types import SimpleNamespace
import copy
import unittest

from app.agent import SupportAgent, TOOLS
from app.config import Settings
from app.data_store import DataStore
from app.knowledge import KnowledgeBase


ROOT = Path(__file__).resolve().parent.parent


class FakeMessages:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        if len(self.calls) == 1:
            return SimpleNamespace(
                content=[
                    {
                        "type": "tool_use",
                        "id": "toolu_test_1",
                        "name": "get_verified_order",
                        "input": {"order_id": "1032"},
                    }
                ],
                usage=SimpleNamespace(input_tokens=100, output_tokens=12),
            )
        return SimpleNamespace(
            content=[
                {
                    "type": "text",
                    "text": (
                        "Order 1032 is still Processing, so a cancellation can be "
                        "requested. I have not cancelled it. "
                        "[Source: exchange_and_cancellation_policy.md]"
                    ),
                }
            ],
            usage=SimpleNamespace(input_tokens=120, output_tokens=38),
        )


class AgentTests(unittest.IsolatedAsyncioTestCase):
    def test_strict_tool_schemas_use_supported_keywords(self):
        unsupported = {"minimum", "maximum", "minItems", "maxItems"}

        def walk(value):
            if isinstance(value, dict):
                self.assertFalse(unsupported & value.keys())
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(TOOLS)

    async def test_tool_loop_and_usage(self):
        settings = Settings(
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
        store = DataStore(ROOT / "data", today=date(2026, 7, 23))
        knowledge = KnowledgeBase(ROOT / "knowledge")
        fake_messages = FakeMessages()
        client = SimpleNamespace(messages=fake_messages)
        agent = SupportAgent(settings, store, knowledge, client=client)

        reply = await agent.respond(
            "Please cancel order 1032.", "liam.carter@example.com"
        )

        self.assertIn("Processing", reply.answer)
        self.assertEqual(reply.tools_used, ["get_verified_order"])
        self.assertEqual(reply.usage["input_tokens"], 220)
        self.assertEqual(reply.usage["output_tokens"], 50)
        second_call_messages = fake_messages.calls[1]["messages"]
        self.assertEqual(
            second_call_messages[-1]["content"][0]["type"], "tool_result"
        )
        self.assertIn(
            "exchange_and_cancellation_policy.md", reply.sources
        )


if __name__ == "__main__":
    unittest.main()
