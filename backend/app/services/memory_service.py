"""Multi-tier agent memory service (WORKING, EPISODIC, SEMANTIC) with vector cosine similarity search."""

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
from app.core.exceptions import NotFoundError
from app.core.permissions import Principal
from app.core.security import sanitize_prompt_input
from app.db.models import MemoryRecord
from app.db.repositories import append_audit_log
from app.integrations.gemini import GeminiClient

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


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
        # Include character trigrams for subword similarity
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
    metadata: dict[str, Any] | None = None,
    importance_score: float = 0.5,
    ttl_seconds: int | None = None,
    settings: Settings,
) -> dict[str, Any]:
    """Store a tenant-scoped memory record with vector embedding and optional TTL."""
    clean_content = sanitize_prompt_input(content, reject_injection=True)
    embedding, embed_provider = _embed_with_honest_provider(clean_content, settings)
    meta = dict(metadata or {})
    meta["embedding_provider"] = embed_provider

    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        if ttl_seconds and ttl_seconds > 0
        else None
    )
    record = MemoryRecord(
        memory_id=f"mem_{uuid.uuid4().hex[:16]}",
        tenant_id=principal.tenant_id,
        agent_id=agent_id,
        memory_type=memory_type.upper(),
        namespace=namespace.strip() or "default",
        content=clean_content,
        metadata_json=json.dumps(meta, default=str),
        embedding_json=json.dumps(embedding),
        importance_score=max(0.0, min(1.0, float(importance_score))),
        expires_at=expires_at,
    )
    db.add(record)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="MEMORY_STORED",
        resource=record.memory_id,
        outcome=f"TYPE={record.memory_type}|EMBED={embed_provider}",
    )
    db.commit()
    db.refresh(record)
    return serialize_memory(record)


def search_memories(
    db: Session,
    *,
    tenant_id: str,
    query: str,
    namespace: str | None = None,
    memory_type: str | None = None,
    agent_id: str | None = None,
    limit: int = 10,
    settings: Settings,
) -> dict[str, Any]:
    """Hybrid semantic cosine-similarity + lexical overlap memory recall."""
    now = datetime.now(timezone.utc)
    stmt = select(MemoryRecord).where(MemoryRecord.tenant_id == tenant_id)
    if namespace:
        stmt = stmt.where(MemoryRecord.namespace == namespace)
    if memory_type:
        stmt = stmt.where(MemoryRecord.memory_type == memory_type.upper())
    if agent_id:
        stmt = stmt.where(MemoryRecord.agent_id == agent_id)

    rows = db.execute(stmt.order_by(MemoryRecord.created_at.desc()).limit(500)).scalars().all()
    q_vec, q_provider = _embed_with_honest_provider(query, settings)
    q_tokens = set(_TOKEN_RE.findall(query.lower()))

    scored: list[tuple[float, MemoryRecord]] = []
    for row in rows:
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
        "total_matches": len(results),
        "results": results,
    }


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
        "agent_id": record.agent_id,
        "memory_type": record.memory_type,
        "namespace": record.namespace,
        "content": record.content,
        "metadata": json.loads(record.metadata_json or "{}"),
        "importance_score": record.importance_score,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "created_at": record.created_at.isoformat(),
    }
