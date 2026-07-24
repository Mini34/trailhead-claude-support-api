from __future__ import annotations

import hmac
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Annotated, Literal

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from . import __version__
from .agent import SupportAgent, SupportAgentError
from .config import Settings
from .data_store import DataStore
from .knowledge import KnowledgeBase


logger = logging.getLogger("trailhead_support")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    customer_email: str | None = Field(default=None, max_length=254)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=12)
    response_detail: Literal["concise", "standard", "comprehensive"] = "comprehensive"

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message cannot be blank")
        return value

    @field_validator("customer_email")
    @classmethod
    def valid_email(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip().lower()
        if not EMAIL_PATTERN.match(value):
            raise ValueError("customer_email must be a valid email address")
        return value


class ChatResponse(BaseModel):
    request_id: str
    answer: str
    sources: list[str]
    tools_used: list[str]
    escalation: dict
    model: str
    usage: dict[str, int]


def create_app(
    settings: Settings | None = None,
    store: DataStore | None = None,
    knowledge: KnowledgeBase | None = None,
    agent: SupportAgent | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    store = store or DataStore(settings.data_dir)
    knowledge = knowledge or KnowledgeBase(settings.knowledge_dir)
    agent = agent or SupportAgent(settings, store, knowledge)

    app = FastAPI(
        title="Trailhead Customer Support API",
        description=(
            "A grounded, read-only customer-support bot powered by the Anthropic "
            "Claude API and local business records."
        ),
        version=__version__,
    )
    app.state.settings = settings
    app.state.store = store
    app.state.knowledge = knowledge
    app.state.agent = agent

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "X-Support-API-Key", "X-Request-ID"],
        )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id[:100]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def require_service_key(
        x_support_api_key: Annotated[str | None, Header()] = None,
    ) -> None:
        expected = settings.support_api_key
        if expected and (
            not x_support_api_key
            or not hmac.compare_digest(x_support_api_key, expected)
        ):
            raise HTTPException(status_code=401, detail="Invalid support API key.")

    @app.exception_handler(SupportAgentError)
    async def support_agent_error_handler(
        request: Request, exc: SupportAgentError
    ) -> JSONResponse:
        status_by_kind = {
            "not_configured": 503,
            "authentication": 503,
            "model_unavailable": 503,
            "invalid_request": 502,
            "rate_limit": 429,
            "upstream_unavailable": 503,
            "upstream_error": 502,
        }
        return JSONResponse(
            status_code=status_by_kind.get(exc.kind, 502),
            content={
                "detail": exc.safe_message,
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.get("/")
    async def root() -> dict:
        return {
            "service": "Trailhead Customer Support API",
            "version": __version__,
            "docs": "/docs",
            "health": "/health",
            "chat": "/v1/support/chat",
        }

    @app.get("/health")
    async def health() -> dict:
        configured = bool(settings.anthropic_api_key)
        return {
            "status": "ready" if configured else "needs_configuration",
            "claude_configured": configured,
            "model": settings.claude_model,
            "data": store.stats,
            "knowledge_documents": len(knowledge.sources),
        }

    @app.get("/v1/catalog/search")
    async def catalog_search(
        q: Annotated[str, Query(min_length=1, max_length=200)],
        in_stock_only: bool = False,
        limit: Annotated[int, Query(ge=1, le=10)] = 5,
    ) -> dict:
        return store.search_products(q, in_stock_only, limit)

    @app.get("/v1/demo/scenarios")
    async def demo_scenarios() -> dict:
        path = settings.data_dir / "demo_scenarios.json"
        scenarios = json.loads(path.read_text(encoding="utf-8"))
        return {"reference_date": "2026-07-23", "scenarios": scenarios}

    @app.post(
        "/v1/support/chat",
        response_model=ChatResponse,
        dependencies=[Depends(require_service_key)],
    )
    async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
        reply = await agent.respond(
            payload.message,
            payload.customer_email,
            [item.model_dump() for item in payload.history],
            payload.response_detail,
        )
        logger.info(
            "support_request_completed request_id=%s tools=%s escalation=%s",
            request.state.request_id,
            ",".join(reply.tools_used) or "none",
            reply.escalation.get("required"),
        )
        return ChatResponse(
            request_id=request.state.request_id,
            answer=reply.answer,
            sources=reply.sources,
            tools_used=reply.tools_used,
            escalation=reply.escalation,
            model=settings.claude_model,
            usage=reply.usage,
        )

    return app


app = create_app()
