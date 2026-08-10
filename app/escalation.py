from __future__ import annotations

from typing import Any

RULES = (
    (
        "safety",
        "urgent",
        (
            "fuel leak",
            "leaking fuel",
            "caught fire",
            "on fire",
            "overheating",
            "electric shock",
            "injury",
            "injured",
            "unsafe product",
        ),
        "Potential product-safety issue.",
    ),
    (
        "security",
        "urgent",
        (
            "account takeover",
            "hacked account",
            "unrecognized order",
            "not my order",
            "fraud",
            "stolen card",
            "identity theft",
        ),
        "Potential fraud or account-security issue.",
    ),
    (
        "billing",
        "high",
        (
            "charged twice",
            "duplicate charge",
            "chargeback",
            "billing dispute",
            "double charged",
        ),
        "Billing dispute requires specialist review.",
    ),
    (
        "privacy",
        "high",
        (
            "delete my data",
            "data deletion",
            "privacy request",
            "data access request",
            "gdpr",
            "ccpa",
        ),
        "Formal privacy request.",
    ),
    (
        "human_request",
        "normal",
        (
            "human agent",
            "real person",
            "speak to a person",
            "talk to someone",
            "supervisor",
        ),
        "Customer explicitly requested a person.",
    ),
)


def classify_escalation(
    message: str, tool_results: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    text = message.lower()
    for category, priority, phrases, reason in RULES:
        if any(phrase in text for phrase in phrases):
            return {
                "required": True,
                "category": category,
                "priority": priority,
                "reason": reason,
            }

    for result in tool_results or []:
        if result.get("human_review"):
            return {
                "required": True,
                "category": "warranty",
                "priority": "normal",
                "reason": "Warranty outcome requires human review.",
            }
        for case in result.get("cases", []):
            if (
                case.get("priority") in {"urgent", "high"}
                and case.get("status") != "resolved"
            ):
                return {
                    "required": True,
                    "category": case.get("category", "support"),
                    "priority": case["priority"],
                    "reason": f"Existing {case['priority']} case {case['case_id']} is open.",
                }

    return {
        "required": False,
        "category": None,
        "priority": None,
        "reason": None,
    }
