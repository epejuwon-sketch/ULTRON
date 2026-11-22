"""ULTRON OS 2026 — FastAPI Application Factory."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, request_id_ctx
from app.core.rate_limit import SlidingWindowRateLimiter
from app.db.session import init_database
from app.routers import (
    agents,
    approvals,
    argon,
    audit,
    auth,
    devices,
    finance,
    github,
    google,
    health,
    integrations,
    memory,
    monitoring,
    neon,
    notifications,
    projects,
    settings as settings_router,
    tasks,
    tools,
    vault,
    ws,
)
from app.services.realtime_hub import metrics_tracker


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the unified ULTRON OS 2026 FastAPI application."""
    cfg = settings or get_settings()
    logger = configure_logging(cfg.log_level)
    rate_limiter = SlidingWindowRateLimiter(limit_per_minute=cfg.rate_limit_requests_per_minute)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_database(cfg)
        logger.info("ULTRON OS 2026 initialized (env=%s, db=%s)", cfg.ultron_env, cfg.database_backend)
        yield

    application = FastAPI(
        title=cfg.app_name,
        version=cfg.app_version,
        description=(
            "Unified autonomous multi-agent intelligence operating system backend: "
            "NEON intelligence engine (Gemini primary), ARGON orchestration & ApprovalGate governance, "
            "60 specialist agents, multi-tier versioned memory, unified OAuth 2.0 IntegrationManager, "
            "Google Ecosystem, GitHub Engineering, Web Research, Multi-Device Mesh, Financial Command Center, "
            "Developer Infrastructure, and Supabase/Vercel/Cloudflare integrations."
        ),
        lifespan=lifespan,
    )

    application.state.rate_limiter = rate_limiter

    application.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Tenant-ID",
            "X-Request-ID",
            "Idempotency-Key",
            "X-Device-Token",
        ],
    )

    @application.middleware("http")
    async def request_context_rate_limit_and_headers(request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        token = request_id_ctx.set(req_id)
        started = time.perf_counter()

        # Skip rate limiting for lightweight liveness probes
        client_host = request.client.host if request.client else "unknown"
        if request.url.path not in {"/health/live", "/health/ready"}:
            allowed, remaining, retry_after = rate_limiter.check(client_host)
            if not allowed:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                metrics_tracker.record(request.url.path, 429, elapsed_ms)
                request_id_ctx.reset(token)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": "Rate limit exceeded. Please retry later.",
                            "details": {"retry_after_seconds": retry_after},
                            "request_id": req_id,
                        }
                    },
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(rate_limiter.limit),
                        "X-RateLimit-Remaining": "0",
                        "X-Request-ID": req_id,
                    },
                )
        else:
            remaining = rate_limiter.limit

        try:
            response = await call_next(request)
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("%s %s (%dms)", request.method, request.url.path, elapsed_ms)
            request_id_ctx.reset(token)

        metrics_tracker.record(request.url.path, response.status_code, elapsed_ms)
        response.headers["X-Request-ID"] = req_id
        response.headers["X-RateLimit-Limit"] = str(rate_limiter.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    register_exception_handlers(application)

    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(integrations.router)
    application.include_router(google.router)
    application.include_router(github.router)
    application.include_router(devices.router)
    application.include_router(agents.router)
    application.include_router(neon.router)
    application.include_router(argon.router)
    application.include_router(tasks.router)
    application.include_router(approvals.router)
    application.include_router(memory.router)
    application.include_router(tools.router)
    application.include_router(vault.router)
    application.include_router(audit.router)
    application.include_router(finance.router)
    application.include_router(projects.router)
    application.include_router(notifications.router)
    application.include_router(settings_router.router)
    application.include_router(monitoring.router)
    application.include_router(ws.router)

    @application.get("/", tags=["Root"])
    def root() -> dict:
        return {
            "service": cfg.app_name,
            "version": cfg.app_version,
            "docs": "/docs",
            "health": "/health",
            "websocket": "/ws/v1/events",
        }

    return application


app = create_app()
