"""Authenticated tenant-scoped WebSocket real-time event stream."""

from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.auth_service import authenticate_bearer_token
from app.services.realtime_hub import realtime_hub

router = APIRouter(tags=["WebSocket Realtime"])


@router.websocket("/ws/v1/events")
async def websocket_events(websocket: WebSocket, token: str = Query(default="")) -> None:
    """Authenticate via `?token=<jwt>` or `Authorization: Bearer <jwt>` and stream tenant events."""
    raw_token = token.strip()
    if not raw_token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            raw_token = auth_header.split(" ", 1)[1].strip()

    if not raw_token:
        await websocket.close(code=4401, reason="Missing authentication token")
        return

    settings = get_settings()
    try:
        with get_session_factory(settings)() as db:
            principal = authenticate_bearer_token(db, token=raw_token, settings=settings)
    except Exception:
        await websocket.close(code=4401, reason="Invalid or revoked token")
        return

    await realtime_hub.connect(principal.tenant_id, websocket)
    await websocket.send_json(
        {
            "event_type": "connection.ready",
            "tenant_id": principal.tenant_id,
            "username": principal.username,
            "role": principal.role.value,
        }
    )
    try:
        while True:
            msg = await websocket.receive_text()
            if msg.strip().lower() == "ping":
                await websocket.send_json({"event_type": "pong", "tenant_id": principal.tenant_id})
    except WebSocketDisconnect:
        await realtime_hub.disconnect(principal.tenant_id, websocket)
