"""ULTRON OS 2026 — FastAPI Application Factory."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.core.exceptions import DatabaseConfigurationError, register_exception_handlers
from app.core.logging import configure_logging, request_id_ctx
from app.core.rate_limit import build_rate_limiter
from app.db.session import classify_database_error, init_database
from app.routers import (
    aegis,
    agents,
    approvals,
    argon,
    atlas,
    audit,
    auth,
    bridge,
    caravan,
    creative,
    devices,
    evolve,
    files,
    finance,
    forge,
    github,
    google,
    health,
    integrations,
    memory,
    monitoring,
    neon,
    notifications,
    projects,
    pulse,
    sentinel,
    settings as settings_router,
    tasks,
    tools,
    turbo,
    vault,
    ws,
)
from app.services.realtime_hub import metrics_tracker


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the unified ULTRON OS 2026 FastAPI application."""
    cfg = settings or get_settings()
    logger = configure_logging(cfg.log_level)
    rate_limiter = build_rate_limiter(cfg)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            init_database(cfg)
            logger.info(
                "ULTRON OS 2026 initialized (env=%s, db=%s, rl=%s)",
                cfg.ultron_env,
                cfg.database_backend,
                rate_limiter.backend_name,
            )
        except (DatabaseConfigurationError, SQLAlchemyError) as exc:
            err_code, detail = classify_database_error(exc, cfg)
            logger.error(
                "ULTRON OS 2026 started in degraded mode (%s): %s",
                err_code,
                detail,
            )
        yield

    application = FastAPI(
        title=cfg.app_name,
        version=cfg.app_version,
        description=(
            "Unified autonomous multi-agent intelligence operating system backend: "
            "NEON intelligence engine (Gemini primary), ARGON orchestration & ApprovalGate governance, "
            "AEGIS autonomous security, EVOLVE controlled self-development, SENTINEL WebAuthn Passkeys, "
            "60 specialist agents, multi-tier versioned memory, VAULT secret interception, "
            "ORBIT multi-device & location mesh, ATLAS personal/world intelligence, FILE HUB, "
            "FORGE & Live Preview, Creative Studio, BRIDGE, PULSE, CARAVAN BI, TURBO benchmarks, "
            "Financial Command Center, and Supabase/Vercel/Cloudflare/Google/GitHub integrations."
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
            "X-Reauth-Token",
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
        if not request.url.path.endswith("/preview"):
            response.headers["X-Frame-Options"] = "DENY"
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none';")
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    register_exception_handlers(application)

    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(sentinel.router)
    application.include_router(aegis.router)
    application.include_router(evolve.router)
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
    application.include_router(atlas.router)
    application.include_router(files.router)
    application.include_router(forge.router)
    application.include_router(creative.router)
    application.include_router(bridge.router)
    application.include_router(pulse.router)
    application.include_router(caravan.router)
    application.include_router(turbo.router)
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
