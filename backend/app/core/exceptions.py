"""Standardized ULTRON OS 2026 domain exceptions and HTTP error envelope."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import request_id_ctx


class UltronError(Exception):
    """Base structured domain error."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.details = details or {}


class AuthenticationError(UltronError):
    status_code = 401
    code = "AUTHENTICATION_ERROR"


class AccountLockedError(UltronError):
    status_code = 423
    code = "ACCOUNT_LOCKED"


class AuthorizationError(UltronError):
    status_code = 403
    code = "AUTHORIZATION_ERROR"


class NotFoundError(UltronError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(UltronError):
    status_code = 409
    code = "CONFLICT"


class ValidationError(UltronError):
    status_code = 422
    code = "VALIDATION_ERROR"


class SecurityViolationError(UltronError):
    status_code = 400
    code = "SECURITY_VIOLATION"


class ApprovalRequiredError(UltronError):
    status_code = 202
    code = "APPROVAL_REQUIRED"


class IntegrationError(UltronError):
    status_code = 502
    code = "INTEGRATION_ERROR"


class ConfigurationError(UltronError):
    status_code = 503
    code = "CONFIGURATION_ERROR"


class DatabaseConfigurationError(ConfigurationError):
    status_code = 503
    code = "DATABASE_CONFIGURATION_ERROR"


def register_exception_handlers(app: FastAPI) -> None:
    """Install consistent JSON error handlers on the FastAPI application."""

    @app.exception_handler(UltronError)
    async def handle_ultron_error(_request: Request, exc: UltronError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": request_id_ctx.get(),
                }
            },
        )
