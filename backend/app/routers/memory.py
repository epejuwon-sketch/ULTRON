"""Multi-tier agent memory storage, versioning, user preferences, semantic search, and pruning routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.schemas import (
    SearchMemoryRequest,
    SetPreferenceRequest,
    StoreMemoryRequest,
    UpdateMemoryRequest,
)
from app.services.memory_service import (
    delete_memory,
    get_memory_history,
    get_user_preferences,
    prune_expired_memories,
    search_memories,
    set_user_preference,
    store_memory,
    update_memory_version,
)

router = APIRouter(prefix="/api/v1/memory", tags=["Memory & Semantic Recall"])


@router.post("", status_code=status.HTTP_201_CREATED)
def api_store_memory(
    body: StoreMemoryRequest,
    principal: Principal = Depends(require_perm("memory:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return store_memory(
        db,
        principal=principal,
        content=body.content,
        memory_type=body.memory_type,
        namespace=body.namespace,
        agent_id=body.agent_id,
        project_id=body.project_id,
        access_level=body.access_level,
        metadata=body.metadata,
        importance_score=body.importance_score,
        ttl_seconds=body.ttl_seconds,
        settings=settings,
    )


@router.post("/search")
def api_search_memory(
    body: SearchMemoryRequest,
    principal: Principal = Depends(require_perm("memory:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return search_memories(
        db,
        tenant_id=principal.tenant_id,
        query=body.query,
        namespace=body.namespace,
        memory_type=body.memory_type,
        agent_id=body.agent_id,
        project_id=body.project_id,
        viewer_user_id=principal.user_id,
        limit=body.limit,
        settings=settings,
    )


@router.get("/preferences")
def api_get_preferences(
    principal: Principal = Depends(require_perm("memory:read")),
    db: Session = Depends(get_db),
) -> dict:
    return {"user_id": principal.user_id, "preferences": get_user_preferences(db, principal=principal)}


@router.put("/preferences")
def api_set_preference(
    body: SetPreferenceRequest,
    principal: Principal = Depends(require_perm("memory:write")),
    db: Session = Depends(get_db),
) -> dict:
    return set_user_preference(db, principal=principal, key=body.key, value=body.value)


@router.patch("/{memory_id}")
def api_update_memory_version(
    memory_id: str,
    body: UpdateMemoryRequest,
    principal: Principal = Depends(require_perm("memory:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return update_memory_version(
        db,
        principal=principal,
        memory_id=memory_id,
        new_content=body.content,
        importance_score=body.importance_score,
        settings=settings,
    )


@router.get("/{memory_id}/history")
def api_memory_history(
    memory_id: str,
    principal: Principal = Depends(require_perm("memory:read")),
    db: Session = Depends(get_db),
) -> dict:
    versions = get_memory_history(db, principal=principal, memory_id=memory_id)
    return {"total_versions": len(versions), "versions": versions}


@router.delete("/{memory_id}", status_code=status.HTTP_200_OK)
def api_delete_memory(
    memory_id: str,
    principal: Principal = Depends(require_perm("memory:delete")),
    db: Session = Depends(get_db),
) -> dict:
    delete_memory(db, principal=principal, memory_id=memory_id)
    return {"deleted": True, "memory_id": memory_id}


@router.post("/prune")
def api_prune_memory(
    principal: Principal = Depends(require_perm("memory:delete")),
    db: Session = Depends(get_db),
) -> dict:
    removed = prune_expired_memories(db, principal=principal)
    return {"pruned_count": removed}
