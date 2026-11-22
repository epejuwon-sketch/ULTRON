"""Structured JSON logging with request correlation IDs and automatic secret redaction."""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"(AIza[0-9A-Za-z\-_]{20,})"),
    re.compile(r"(sk-[A-Za-z0-9\-_]{16,})"),
    re.compile(r"(eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+)"),
    re.compile(r"(postgres(?:ql)?(?:\+[a-z0-9_]+)?://[^:\s/@]+:)([^@\s]+)(@)", re.IGNORECASE),
    re.compile(r"((?:api[_-]?key|token|secret|password)\s*[=:]\s*)([^\s,\"']+)", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Scrub bearer tokens, JWTs, API keys, DB credentials, and inline secret assignments from log lines."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 3:
            redacted = pattern.sub(r"\1[REDACTED]\3", redacted)
        elif pattern.groups >= 2:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


class JsonRedactingFormatter(logging.Formatter):
    """Emit structured JSON logs with secret redaction and correlation IDs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_ctx.get(),
            "message": redact_secrets(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure root ULTRON logger with structured JSON output."""
    root = logging.getLogger("ultron")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonRedactingFormatter())
        root.addHandler(handler)
    root.propagate = False
    return root
