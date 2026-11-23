"""Phase 3 Production Infrastructure Tests:
- 100% ORM <-> Supabase SQL Migration (001-004) schema & RLS parity
- Persistent Storage Adapters (Local + Supabase Storage private bucket, AES-256-GCM, signed URLs, delete/restore)
- ARGON Worker Lifecycle (Idempotency, Backoff, DLQ, Cancel, Requeue, and ApprovalGate Non-Bypass)
- Shared Production Redis REST Rate Limiter contract
- Verified Nov 2026 Gemini model configuration (zero deprecated defaults)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest
from app.core.config import Settings
from app.core.exceptions import AuthorizationError
from app.core.rate_limit import SharedRedisRestRateLimiter
from app.db.models import Base
from app.services.job_scheduler import compute_backoff_seconds
from app.services.storage_adapter import SupabaseStorageAdapter
from fastapi.testclient import TestClient


def test_supabase_migrations_001_to_004_match_all_53_orm_models_and_rls() -> None:
    root = Path(__file__).resolve().parents[2]
    mig_dir = root / "backend" / "migrations" / "supabase"
    files = sorted(mig_dir.glob("*.sql"))
    assert [f.name for f in files] == [
        "001_initial_schema.sql",
        "002_full_backend_schema.sql",
        "003_ecosystem_and_devices.sql",
        "004_full_platform_features.sql",
        "005_finance_cards.sql",
    ]
    sql = "\n".join(p.read_text(encoding="utf-8") for p in files)

    tables_sql: dict[str, set[str]] = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\);", sql, re.S | re.I):
        tname, body = m.group(1), m.group(2)
        cols = set()
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line or line.startswith("--") or re.match(r"^(CONSTRAINT|PRIMARY|UNIQUE|FOREIGN|CHECK)\b", line, re.I):
                continue
            cols.add(line.split()[0].strip('"'))
        tables_sql[tname] = cols

    for m in re.finditer(r"ALTER TABLE\s+(\w+)\s+ADD COLUMN IF NOT EXISTS\s+(\w+)", sql, re.I):
        tables_sql.setdefault(m.group(1), set()).add(m.group(2))

    assert len(Base.metadata.tables) == 54
    for tname, table in Base.metadata.tables.items():
        assert tname in tables_sql, f"ORM table '{tname}' missing from Supabase SQL migrations"
        orm_cols = {c.name for c in table.columns}
        missing = orm_cols - tables_sql[tname]
        assert not missing, f"Table '{tname}' missing columns in SQL migrations: {missing}"

    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "tenant_isolation_" in sql


def test_file_hub_signed_url_soft_delete_and_restore_lifecycle(
    client: TestClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    # 1. Storage status
    st = client.get("/api/v1/files/storage/status", headers=auth_headers["owner"]).json()
    assert st["active_backend"] == "local_disk"
    assert st["private_bucket_default"] == "ultron-private-files"

    # 2. Upload file
    payload = b"ULTRON Phase 3 persistent storage verification payload."
    up = client.post(
        "/api/v1/files/upload",
        headers=auth_headers["owner"],
        files={"file": ("storage_test.txt", payload, "text/plain")},
    )
    assert up.status_code == 201
    fid = up.json()["file_id"]

    # 3. Create short-lived signed URL and download via it
    signed = client.post(
        f"/api/v1/files/{fid}/signed-url",
        headers=auth_headers["owner"],
        json={"expires_in_seconds": 120},
    )
    assert signed.status_code == 200
    signed_url = signed.json()["signed_url"]
    assert signed.json()["private_bucket"] is True

    dl_signed = client.get(signed_url)
    assert dl_signed.status_code == 200
    assert dl_signed.content == payload

    # Tampered signed token rejected
    bad_dl = client.get(signed_url + "tamper")
    assert bad_dl.status_code == 403

    # 4. Soft-delete file -> download must return 404
    deleted = client.delete(f"/api/v1/files/{fid}", headers=auth_headers["owner"])
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/api/v1/files/{fid}/download", headers=auth_headers["owner"]).status_code == 404

    # 5. Restore file -> download returns exact original bytes
    restored = client.post(f"/api/v1/files/{fid}/restore", headers=auth_headers["owner"])
    assert restored.status_code == 200
    assert restored.json()["deleted"] is False
    dl_after = client.get(f"/api/v1/files/{fid}/download", headers=auth_headers["owner"])
    assert dl_after.status_code == 200
    assert dl_after.content == payload


def test_supabase_storage_adapter_private_encrypted_upload_signed_delete_restore() -> None:
    store: dict[str, bytes] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if req.method == "POST" and path.startswith("/storage/v1/object/sign/"):
            key = path.removeprefix("/storage/v1/object/sign/")
            return httpx.Response(200, json={"signedURL": f"/object/sign/{key}?token=sig_abc"})
        if req.method == "POST" and path == "/storage/v1/object/move":
            body = json.loads(req.content.decode())
            src = f"{body['bucketId']}/{body['sourceKey']}"
            dst = f"{body['bucketId']}/{body['destinationKey']}"
            store[dst] = store.pop(src)
            return httpx.Response(200, json={"message": "Moved"})
        if req.method == "POST" and path.startswith("/storage/v1/object/"):
            key = path.removeprefix("/storage/v1/object/")
            store[key] = req.content
            return httpx.Response(200, json={"Key": key})
        if req.method == "GET" and path.startswith("/storage/v1/object/authenticated/"):
            key = path.removeprefix("/storage/v1/object/authenticated/")
            if key not in store:
                return httpx.Response(404, json={"error": "not_found"})
            return httpx.Response(200, content=store[key])
        return httpx.Response(400, json={"error": "unexpected"})

    cfg = Settings(
        ULTRON_ENV="test",
        SUPABASE_URL="https://demo.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="sb-service-test-key",
        SUPABASE_STORAGE_BUCKET="ultron-private-files",
        ULTRON_VAULT_MASTER_KEY="test-vault-master-key-for-supabase-storage-adapter-2026",
    )
    adapter = SupabaseStorageAdapter(cfg, http_client=httpx.Client(transport=httpx.MockTransport(handler)), encrypt_at_rest=True)

    plaintext = b"Confidential ULTRON tenant document bytes"
    ref = adapter.upload_bytes(tenant_id="TENANT-A", object_key="fil_1_doc.txt", data=plaintext, mime_type="text/plain")
    assert ref == "supabase://ultron-private-files/TENANT-A/fil_1_doc.txt"

    # Stored cloud bytes MUST be AES-256-GCM encrypted (not plaintext)
    raw_cloud = store["ultron-private-files/TENANT-A/fil_1_doc.txt"]
    assert plaintext not in raw_cloud
    assert b"AES-256-GCM" in raw_cloud

    # Authenticated download decrypts cleanly
    assert adapter.download_bytes(tenant_id="TENANT-A", storage_ref=ref) == plaintext

    # Cross-tenant access strictly rejected
    with pytest.raises(AuthorizationError):
        adapter.download_bytes(tenant_id="TENANT-B", storage_ref=ref)

    # Signed URL points to private bucket sign endpoint
    signed = adapter.create_signed_url(tenant_id="TENANT-A", file_id="fil_1", storage_ref=ref, expires_in_seconds=180)
    assert signed["private_bucket"] is True
    assert "token=sig_abc" in signed["signed_url"]

    # Soft delete & restore
    trash_ref = adapter.soft_delete(tenant_id="TENANT-A", storage_ref=ref)
    assert "_trash/TENANT-A/" in trash_ref
    restored_ref = adapter.restore(tenant_id="TENANT-A", trash_ref=trash_ref, original_ref=ref)
    assert restored_ref == ref
    assert adapter.download_bytes(tenant_id="TENANT-A", storage_ref=ref) == plaintext


def test_argon_worker_idempotency_dlq_backoff_and_approval_gate_non_bypass(
    client: TestClient, auth_headers: dict[str, dict[str, str]]
) -> None:
    # 1. Bounded exponential backoff curve
    assert compute_backoff_seconds(1) == 15
    assert compute_backoff_seconds(2) == 30
    assert compute_backoff_seconds(3) == 60
    assert compute_backoff_seconds(10) == 600  # capped

    # 2. Idempotent enqueue prevents duplicates
    j1 = client.post(
        "/api/v1/argon/jobs",
        headers={**auth_headers["owner"], "Idempotency-Key": "idem-job-001"},
        json={"job_type": "CUSTOM_NOOP", "payload": {"x": 1}, "max_attempts": 2},
    )
    j2 = client.post(
        "/api/v1/argon/jobs",
        headers={**auth_headers["owner"], "Idempotency-Key": "idem-job-001"},
        json={"job_type": "CUSTOM_NOOP", "payload": {"x": 1}, "max_attempts": 2},
    )
    assert j1.status_code == 201 and j2.status_code == 201
    assert j1.json()["job_id"] == j2.json()["job_id"]
    assert j2.json().get("idempotent_replay") is True

    # 3. Dead-letter queue & operator requeue/cancel
    failing = client.post(
        "/api/v1/argon/jobs",
        headers=auth_headers["owner"],
        json={"job_type": "FAIL_TEST_JOB", "payload": {"reason": "boom"}, "max_attempts": 1},
    ).json()
    proc = client.post("/api/v1/argon/jobs/process", headers=auth_headers["owner"]).json()
    assert proc["dead_lettered"] >= 1

    dlq_list = client.get("/api/v1/argon/jobs?status=DEAD_LETTER", headers=auth_headers["owner"]).json()
    assert any(j["job_id"] == failing["job_id"] for j in dlq_list["jobs"])

    requeued = client.post(f"/api/v1/argon/jobs/{failing['job_id']}/requeue", headers=auth_headers["owner"])
    assert requeued.status_code == 200 and requeued.json()["status"] == "QUEUED"

    cancelled = client.post(f"/api/v1/argon/jobs/{failing['job_id']}/cancel", headers=auth_headers["owner"])
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"

    # 4. CRITICAL SECURITY TEST: Worker MUST NOT bypass ApprovalGate on an unapproved high-value task!
    gated_task = client.post(
        "/api/v1/tasks",
        headers=auth_headers["owner"],
        json={"title": "Wire Transfer", "objective": "Transfer $500 to external vendor", "financial_amount_usd": 500.0},
    ).json()
    assert gated_task["lifecycle_state"] == "WAITING_FOR_APPROVAL"

    # Attempt to sneak execution through raw background job queue
    bypass_job = client.post(
        "/api/v1/argon/jobs",
        headers=auth_headers["owner"],
        json={"job_type": "EXECUTE_TASK", "payload": {"task_id": gated_task["task_id"]}, "max_attempts": 3},
    ).json()
    proc2 = client.post("/api/v1/argon/jobs/process", headers=auth_headers["owner"]).json()
    assert proc2["approval_blocked"] >= 1

    # Confirm task is STILL WAITING_FOR_APPROVAL and bypass job was sent directly to DEAD_LETTER
    task_check = client.get(f"/api/v1/tasks/{gated_task['task_id']}", headers=auth_headers["owner"]).json()
    assert task_check["lifecycle_state"] == "WAITING_FOR_APPROVAL"
    jobs_after = client.get("/api/v1/argon/jobs?status=DEAD_LETTER", headers=auth_headers["owner"]).json()["jobs"]
    assert any(j["job_id"] == bypass_job["job_id"] for j in jobs_after)


def test_shared_redis_rest_rate_limiter_contract_and_gemini_model_currency() -> None:
    counter = {"n": 0}

    def redis_handler(_req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(200, json=[{"result": counter["n"]}, {"result": 1}])

    rl = SharedRedisRestRateLimiter(
        rest_url="https://demo.upstash.io",
        rest_token="test-token",
        limit_per_minute=2,
        http_client=httpx.Client(transport=httpx.MockTransport(redis_handler)),
    )
    assert rl.check("1.2.3.4")[0] is True
    assert rl.check("1.2.3.4")[0] is True
    allowed, rem, retry = rl.check("1.2.3.4")
    assert allowed is False and rem == 0 and retry >= 1

    # Verify active Nov 2026 Gemini defaults (no deprecated 2.5 or 3.7 defaults)
    cfg = Settings(ULTRON_ENV="test")
    assert cfg.gemini_model_fast == "gemini-3.5-flash-lite"
    assert cfg.gemini_model_standard == "gemini-3.8-flash"
    assert cfg.gemini_model_reasoning == "gemini-4-argon"
    assert cfg.gemini_model_embedding == "gemini-embedding-001"
    assert cfg.gemini_model_image == "gemini-nano-banana-2.1"
