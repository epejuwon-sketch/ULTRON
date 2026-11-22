"""ULTRON OS 2026 — FastAPI Application Factory."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, request_id_ctx
from app.db.session import init_database
from app.routers import agents, approvals, audit, auth, health, memory, tasks, tools, vault


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the modular ULTRON OS 2026 FastAPI application."""
    cfg = settings or get_settings()
    logger = configure_logging(cfg.log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_database(cfg)
        logger.info("ULTRON OS 2026 initialized (env=%s, db=%s)", cfg.ultron_env, cfg.database_backend)
        yield

    application = FastAPI(
        title=cfg.app_name,
        version=cfg.app_version,
        description=(
            "Modular autonomous multi-agent intelligence operating system backend "
            "(NEON cognitive routing, ARGON security/vault/orchestration, ApprovalGate, "
            "60-agent catalog, multi-tier memory, and Supabase/Gemini/Vercel/Cloudflare integrations)."
        ),
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Tenant-ID", "X-Request-ID"],
    )

    @application.middleware("http")
    async def request_context_and_security_headers(request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        token = request_id_ctx.set(req_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("%s %s (%dms)", request.method, request.url.path, elapsed_ms)
            request_id_ctx.reset(token)

        response.headers["X-Request-ID"] = req_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    register_exception_handlers(application)

    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(agents.router)
    application.include_router(tasks.router)
    application.include_router(approvals.router)
    application.include_router(memory.router)
    application.include_router(tools.router)
    application.include_router(vault.router)
    application.include_router(audit.router)

    @application.get("/", tags=["Root"])
    def root() -> dict:
        return {
            "service": cfg.app_name,
            "version": cfg.app_version,
            "docs": "/docs",
            "health": "/health",
        }

    return application


app = create_app()
