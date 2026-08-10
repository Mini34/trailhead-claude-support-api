from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _as_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def _as_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    anthropic_api_key: str | None
    claude_model: str
    max_tokens: int
    max_tool_rounds: int
    request_timeout_seconds: float
    support_api_key: str | None
    cors_origins: tuple[str, ...]
    data_dir: Path
    knowledge_dir: Path

    @classmethod
    def from_env(cls) -> Settings:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip() or None
        service_key = os.getenv("SUPPORT_API_KEY", "").strip() or None
        origins = tuple(
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
            if origin.strip()
        )
        return cls(
            anthropic_api_key=api_key,
            claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5").strip()
            or "claude-sonnet-5",
            max_tokens=_as_int("CLAUDE_MAX_TOKENS", 900, 128, 4096),
            max_tool_rounds=_as_int("CLAUDE_MAX_TOOL_ROUNDS", 5, 1, 8),
            request_timeout_seconds=_as_float(
                "CLAUDE_TIMEOUT_SECONDS", 45.0, 5.0, 120.0
            ),
            support_api_key=service_key,
            cors_origins=origins,
            data_dir=Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data")).resolve(),
            knowledge_dir=Path(
                os.getenv("KNOWLEDGE_DIR", PROJECT_ROOT / "knowledge")
            ).resolve(),
        )
