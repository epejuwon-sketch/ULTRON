"""Multi-tier agent memory service with versioning, user preferences, project memory, retention policies, and pgvector/local cosine search."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AuthorizationError, NotFoundError
from app.core.permissions import Principal, Role
from app.core.secret_interceptor import intercept_and_redact_secrets
from app.core.security import sanitize_prompt_input
from app.db.models import MemoryRecord, UserPreferenceRecord
from app.db.repositories import append_audit_log
from app.integrations.gemini import GeminiClient

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")

VALID_MEMORY_TYPES = frozenset(
    {"WORKING", "SHORT_TERM", "LONG_TERM", "EPISODIC", "SEMANTIC", "PROJECT", "USER_PREFERENCE"}
)

DEFAULT_RETENTION_SECONDS: dict[str, int | None] = {
    "WORKING": 86400,           # 24 hours
    "SHORT_TERM": 86400 * 7,    # 7 days
    "EPISODIC": 86400 * 90,     # 90 days
    "SEMANTIC": None,           # retained until user deletion
    "LONG_TERM": None,
    "PROJECT": None,
    "USER_PREFERENCE": None,
}


def compute_local_embedding(text: str, dims: int = 64) -> list[float]:
    """Deterministic L2-normalized feature-hashing vector for offline semantic recall."""
    vec = [0.0] * dims
    tokens = _TOKEN_RE.findall((text or "").lower())
    if not tokens:
        return vec
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "big") % dims
        sign = 1.0 if (digest[2] & 1) == 0 else -1.0
        vec[idx] += sign
        for i in range(max(0, len(tok) - 2)):
            tri = tok[i : i + 3]
            td = hashlib.sha256(tri.encode("utf-8")).digest()
            t_idx = int.from_bytes(td[:2], "big") % dims
            vec[t_idx] += 0.35 if (td[2] & 1) == 0 else -0.35
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [round(v / norm, 6) for v in vec]
    return vec


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _embed_with_honest_provider(text: str, settings: Settings) -> tuple[list[float], str]:
    gemini = GeminiClient(settings)
    if gemini.is_configured():
        try:
            vec = gemini.embed_text(text)
            if vec:
                return vec, "gemini"
        except Exception:
            pass
    return compute_local_embedding(text), "local_hash_v1"


def store_memory(
    db: Session,
    *,
    principal: Principal,
    content: str,
    memory_type: str = "EPISODIC",
    namespace: str = "default",
    agent_id: str = "AGT-21",
    project_id: str | None = None,
    access_level: str = "TENANT",
    metadata: dict[str, Any] | None = None,
    importance_score: float = 0.5,
    ttl_seconds: int | None = None,
    settings: Settings,
) -> dict[str, Any]:
    """Store a version-1 tenant-scoped memory record with embedding, secret redaction, and retention TTL."""
    raw_clean = sanitize_prompt_input(content, reject_injection=True)
    interception = intercept_and_redact_secrets(
        raw_clean,
        db=db,
        principal=principal,
        settings=settings,
        source_context=f"memory:{namespace}",
        auto_vault=True,
    )
    clean_content = interception.sanitized_text
    m_type = memory_type.upper()
    if m_type not in VALID_MEMORY_TYPES:
        m_type = "EPISODIC"

    embedding, embed_provider = _embed_with_honest_provider(clean_content, settings)
    meta = dict(metadata or {})
    meta["embedding_provider"] = embed_provider
    if interception.redaction_count > 0:
        meta["secrets_vaulted"] = interception.secrets_vaulted
        meta["payment_data_blocked"] = interception.payment_data_blocked

    effective_ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_RETENTION_SECONDS.get(m_type)
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=effective_ttl)
        if effective_ttl and effective_ttl > 0
        else None
    )
    record = MemoryRecord(
        memory_id=f"mem_{uuid.uuid4().hex[:16]}",
        tenant_id=principal.tenant_id,
        owner_user_id=principal.user_id,
        project_id=project_id,
        agent_id=agent_id,
        memory_type=m_type,
        namespace=namespace.strip() or "default",
        content=clean_content,
        metadata_json=json.dumps(meta, default=str),
        embedding_json=json.dumps(embedding),
        importance_score=max(0.0, min(1.0, float(importance_score))),
        version=1,
        parent_memory_id=None,
        is_latest=True,
        access_level=access_level.upper() if access_level.upper() in {"TENANT", "PRIVATE"} else "TENANT",
        expires_at=expires_at,
    )
    db.add(record)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="MEMORY_STORED",
        resource=record.memory_id,
        outcome=f"TYPE={record.memory_type}|V1|EMBED={embed_provider}",
    )
    db.commit()
    db.refresh(record)
    return serialize_memory(record)


def update_memory_version(
    db: Session,
    *,
    principal: Principal,
    memory_id: str,
    new_content: str,
    importance_score: float | None = None,
    settings: Settings,
) -> dict[str, Any]:
    """Create a new versioned revision of an existing memory record preserving full history."""
    existing = db.execute(
        select(MemoryRecord).where(
            MemoryRecord.memory_id == memory_id,
            MemoryRecord.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if existing is None:
        raise NotFoundError(f"Memory '{memory_id}' not found.")
    if existing.access_level == "PRIVATE" and existing.owner_user_id != principal.user_id and principal.role != Role.OWNER:
        raise AuthorizationError("Cannot modify another user's PRIVATE memory.")

    clean_content = sanitize_prompt_input(new_content, reject_injection=True)
    embedding, embed_provider = _embed_with_honest_provider(clean_content, settings)
    meta = json.loads(existing.metadata_json or "{}")
    meta["embedding_provider"] = embed_provider

    root_id = existing.parent_memory_id or existing.memory_id
    existing.is_latest = False

    revised = MemoryRecord(
        memory_id=f"mem_{uuid.uuid4().hex[:16]}",
        tenant_id=existing.tenant_id,
        owner_user_id=existing.owner_user_id,
        project_id=existing.project_id,
        agent_id=existing.agent_id,
        memory_type=existing.memory_type,
        namespace=existing.namespace,
        content=clean_content,
        metadata_json=json.dumps(meta, default=str),
        embedding_json=json.dumps(embedding),
        importance_score=existing.importance_score if importance_score is None else max(0.0, min(1.0, importance_score)),
        version=existing.version + 1,
        parent_memory_id=root_id,
        is_latest=True,
        access_level=existing.access_level,
        expires_at=existing.expires_at,
    )
    db.add(revised)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="MEMORY_VERSIONED",
        resource=revised.memory_id,
        outcome=f"PARENT={root_id}|V{revised.version}",
    )
    db.commit()
    db.refresh(revised)
    return serialize_memory(revised)


def get_memory_history(db: Session, *, principal: Principal, memory_id: str) -> list[dict[str, Any]]:
    target = db.execute(
        select(MemoryRecord).where(
            MemoryRecord.memory_id == memory_id,
            MemoryRecord.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if target is None:
        raise NotFoundError(f"Memory '{memory_id}' not found.")
    root_id = target.parent_memory_id or target.memory_id
    rows = db.execute(
        select(MemoryRecord)
        .where(
            MemoryRecord.tenant_id == principal.tenant_id,
            (MemoryRecord.memory_id == root_id) | (MemoryRecord.parent_memory_id == root_id),
        )
        .order_by(MemoryRecord.version.asc())
    ).scalars().all()
    return [serialize_memory(r) for r in rows]


def search_memories(
    db: Session,
    *,
    tenant_id: str,
    query: str,
    namespace: str | None = None,
    memory_type: str | None = None,
    agent_id: str | None = None,
    project_id: str | None = None,
    viewer_user_id: str | None = None,
    limit: int = 10,
    settings: Settings,
) -> dict[str, Any]:
    """Hybrid semantic cosine-similarity + lexical overlap memory recall over latest versions."""
    now = datetime.now(timezone.utc)
    stmt = select(MemoryRecord).where(
        MemoryRecord.tenant_id == tenant_id,
        MemoryRecord.is_latest.is_(True),
    )
    if namespace:
        stmt = stmt.where(MemoryRecord.namespace == namespace)
    if memory_type:
        stmt = stmt.where(MemoryRecord.memory_type == memory_type.upper())
    if agent_id:
        stmt = stmt.where(MemoryRecord.agent_id == agent_id)
    if project_id:
        stmt = stmt.where(MemoryRecord.project_id == project_id)

    rows = db.execute(stmt.order_by(MemoryRecord.created_at.desc()).limit(500)).scalars().all()
    q_vec, q_provider = _embed_with_honest_provider(query, settings)
    q_tokens = set(_TOKEN_RE.findall(query.lower()))

    scored: list[tuple[float, MemoryRecord]] = []
    for row in rows:
        if row.access_level == "PRIVATE" and viewer_user_id and row.owner_user_id != viewer_user_id:
            continue
        exp = row.expires_at
        if exp is not None:
            exp_utc = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
            if now >= exp_utc:
                continue
        row_vec = json.loads(row.embedding_json or "[]")
        vec_score = cosine_similarity(q_vec, row_vec) if len(q_vec) == len(row_vec) else 0.0
        row_tokens = set(_TOKEN_RE.findall(row.content.lower()))
        lexical = (len(q_tokens & row_tokens) / len(q_tokens)) if q_tokens else 0.0
        blended = (0.65 * max(0.0, vec_score)) + (0.25 * lexical) + (0.10 * row.importance_score)
        scored.append((round(blended, 4), row))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, row in scored[:limit]:
        item = serialize_memory(row)
        item["relevance_score"] = score
        results.append(item)

    return {
        "query": query,
        "embedding_provider": q_provider,
        "vector_backend": "pgvector_ready" if settings.database_backend == "postgresql" else "sqlite_cosine",
        "total_matches": len(results),
        "results": results,
    }


def set_user_preference(db: Session, *, principal: Principal, key: str, value: Any) -> dict[str, Any]:
    clean_key = key.strip()
    existing = db.execute(
        select(UserPreferenceRecord).where(
            UserPreferenceRecord.tenant_id == principal.tenant_id,
            UserPreferenceRecord.user_id == principal.user_id,
            UserPreferenceRecord.pref_key == clean_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.pref_value_json = json.dumps(value, default=str)
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(
            UserPreferenceRecord(
                pref_id=f"prf_{uuid.uuid4().hex[:16]}",
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                pref_key=clean_key,
                pref_value_json=json.dumps(value, default=str),
            )
        )
    db.commit()
    return {"key": clean_key, "value": value, "user_id": principal.user_id}


def get_user_preferences(db: Session, *, principal: Principal) -> dict[str, Any]:
    rows = db.execute(
        select(UserPreferenceRecord).where(
            UserPreferenceRecord.tenant_id == principal.tenant_id,
            UserPreferenceRecord.user_id == principal.user_id,
        )
    ).scalars().all()
    return {r.pref_key: json.loads(r.pref_value_json) for r in rows}


def delete_memory(db: Session, *, principal: Principal, memory_id: str) -> None:
    record = db.execute(
        select(MemoryRecord).where(
            MemoryRecord.memory_id == memory_id,
            MemoryRecord.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if record is None:
        raise NotFoundError(f"Memory '{memory_id}' not found.")
    db.delete(record)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="MEMORY_DELETED",
        resource=memory_id,
        outcome="DELETED",
    )
    db.commit()


def prune_expired_memories(db: Session, *, principal: Principal) -> int:
    """Delete all expired memories belonging to the caller's tenant."""
    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(MemoryRecord).where(
            MemoryRecord.tenant_id == principal.tenant_id,
            MemoryRecord.expires_at.is_not(None),
        )
    ).scalars().all()
    removed = 0
    for row in rows:
        exp = row.expires_at
        if exp is not None:
            exp_utc = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
            if now >= exp_utc:
                db.delete(row)
                removed += 1
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="MEMORY_PRUNED",
        resource=principal.tenant_id,
        outcome=f"REMOVED_{removed}",
    )
    db.commit()
    return removed


def serialize_memory(record: MemoryRecord) -> dict[str, Any]:
    return {
        "memory_id": record.memory_id,
        "tenant_id": record.tenant_id,
        "owner_user_id": record.owner_user_id,
        "project_id": record.project_id,
        "agent_id": record.agent_id,
        "memory_type": record.memory_type,
        "namespace": record.namespace,
        "content": record.content,
        "metadata": json.loads(record.metadata_json or "{}"),
        "importance_score": record.importance_score,
        "version": record.version,
        "parent_memory_id": record.parent_memory_id,
        "is_latest": record.is_latest,
        "access_level": record.access_level,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "created_at": record.created_at.isoformat(),
    }
