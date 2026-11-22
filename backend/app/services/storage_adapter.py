"""Persistent Storage Adapters for FILE HUB: Supabase Storage (Production) & Local Disk (Development).

Security Guarantees:
- Private buckets by default (`ultron-private-files`); files are NEVER exposed publicly.
- Strictly tenant-scoped object paths (`{tenant_id}/{file_id}_{safe_name}`).
- Optional AES-256-GCM at-rest encryption envelope prior to cloud upload.
- Short-lived signed download URLs (default 300s TTL).
- Full upload, download, soft-delete, and restore lifecycle.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import shutil
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import AuthorizationError, NotFoundError
from app.core.security import decrypt_vault_secret, encrypt_vault_secret


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    pad = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + pad)


def sign_local_download_token(
    *,
    file_id: str,
    tenant_id: str,
    secret_key: str,
    expires_in_seconds: int = 300,
) -> tuple[str, int]:
    """Generate a short-lived HMAC-SHA256 signed download token for local adapter URLs."""
    exp = int(time.time()) + max(30, min(3600, int(expires_in_seconds)))
    payload = _b64url_encode(json.dumps({"fid": file_id, "tid": tenant_id, "exp": exp}, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(secret_key.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}", exp


def verify_local_download_token(token: str, *, secret_key: str) -> dict[str, Any]:
    """Verify HMAC signature and expiry of a short-lived local download token."""
    if "." not in token:
        raise AuthorizationError("Malformed signed download token.")
    payload_b64, sig_hex = token.split(".", 1)
    expected = hmac.new(secret_key.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig_hex, expected):
        raise AuthorizationError("Invalid signed download token signature.")
    data = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    if int(data.get("exp", 0)) < int(time.time()):
        raise AuthorizationError("Signed download URL has expired.")
    return data


class BaseStorageAdapter(ABC):
    backend_name: str = "unknown"

    @abstractmethod
    def upload_bytes(self, *, tenant_id: str, object_key: str, data: bytes, mime_type: str) -> str:
        """Persist bytes under a tenant-scoped object path and return canonical storage_ref."""

    @abstractmethod
    def download_bytes(self, *, tenant_id: str, storage_ref: str) -> bytes:
        """Retrieve raw bytes for a tenant-scoped storage_ref."""

    @abstractmethod
    def soft_delete(self, *, tenant_id: str, storage_ref: str) -> str:
        """Move object to tenant-scoped trash prefix for recoverable deletion; return trash_ref."""

    @abstractmethod
    def restore(self, *, tenant_id: str, trash_ref: str, original_ref: str) -> str:
        """Restore a soft-deleted object back to its original tenant-scoped ref."""

    @abstractmethod
    def create_signed_url(
        self,
        *,
        tenant_id: str,
        file_id: str,
        storage_ref: str,
        expires_in_seconds: int = 300,
    ) -> dict[str, Any]:
        """Issue a short-lived signed download URL."""


class LocalStorageAdapter(BaseStorageAdapter):
    """Local filesystem storage adapter for development/testing with soft-delete trash & signed URLs."""

    backend_name = "local_disk"

    def __init__(self, settings: Settings, root_dir: Path | None = None) -> None:
        self.settings = settings
        self.root = root_dir or (Path(__file__).resolve().parents[3] / "data" / "file_hub")
        self.root.mkdir(parents=True, exist_ok=True)
        self.trash_root = self.root / ".trash"
        self.trash_root.mkdir(parents=True, exist_ok=True)

    def _resolve_safe(self, base: Path, tenant_id: str, object_key: str) -> Path:
        clean_key = object_key.lstrip("/").replace("..", "")
        tenant_dir = (base / tenant_id).resolve()
        tenant_dir.mkdir(parents=True, exist_ok=True)
        target = (tenant_dir / clean_key).resolve()
        if not str(target).startswith(str(tenant_dir)):
            raise AuthorizationError("Path traversal attempt rejected by storage adapter.")
        return target

    def upload_bytes(self, *, tenant_id: str, object_key: str, data: bytes, mime_type: str) -> str:
        target = self._resolve_safe(self.root, tenant_id, object_key)
        target.write_bytes(data)
        return f"local://{tenant_id}/{target.name}"

    def _ref_to_path(self, tenant_id: str, storage_ref: str, *, is_trash: bool = False) -> Path:
        prefix = f"local-trash://{tenant_id}/" if is_trash else f"local://{tenant_id}/"
        if storage_ref.startswith(prefix):
            name = storage_ref.removeprefix(prefix)
            return self._resolve_safe(self.trash_root if is_trash else self.root, tenant_id, name)
        # Backward compatibility for legacy absolute disk paths stored before adapter migration
        legacy = Path(storage_ref).resolve()
        tenant_dir = (self.root / tenant_id).resolve()
        if str(legacy).startswith(str(tenant_dir)):
            return legacy
        raise AuthorizationError("Cross-tenant or unrecognized storage reference denied.")

    def download_bytes(self, *, tenant_id: str, storage_ref: str) -> bytes:
        path = self._ref_to_path(tenant_id, storage_ref, is_trash=False)
        if not path.exists():
            raise NotFoundError("Stored file payload not found.")
        return path.read_bytes()

    def soft_delete(self, *, tenant_id: str, storage_ref: str) -> str:
        src = self._ref_to_path(tenant_id, storage_ref, is_trash=False)
        if not src.exists():
            raise NotFoundError("Stored file payload not found for deletion.")
        dst = self._resolve_safe(self.trash_root, tenant_id, src.name)
        shutil.move(str(src), str(dst))
        return f"local-trash://{tenant_id}/{dst.name}"

    def restore(self, *, tenant_id: str, trash_ref: str, original_ref: str) -> str:
        src = self._ref_to_path(tenant_id, trash_ref, is_trash=True)
        if not src.exists():
            raise NotFoundError("Soft-deleted file payload not found in trash.")
        dst = self._ref_to_path(tenant_id, original_ref, is_trash=False)
        shutil.move(str(src), str(dst))
        return f"local://{tenant_id}/{dst.name}"

    def create_signed_url(
        self,
        *,
        tenant_id: str,
        file_id: str,
        storage_ref: str,
        expires_in_seconds: int = 300,
    ) -> dict[str, Any]:
        # Verify object exists and belongs to tenant before issuing token
        path = self._ref_to_path(tenant_id, storage_ref, is_trash=False)
        if not path.exists():
            raise NotFoundError("Stored file payload not found.")
        tok, exp = sign_local_download_token(
            file_id=file_id,
            tenant_id=tenant_id,
            secret_key=self.settings.jwt_secret.get_secret_value(),
            expires_in_seconds=expires_in_seconds,
        )
        return {
            "storage_backend": self.backend_name,
            "signed_url": f"/api/v1/files/signed/{tok}",
            "expires_in_seconds": max(30, min(3600, int(expires_in_seconds))),
            "expires_at_epoch": exp,
            "private_bucket": True,
        }


class SupabaseStorageAdapter(BaseStorageAdapter):
    """Production Supabase Storage adapter using private buckets, tenant-scoped paths, optional AES-256-GCM encryption, and signed URLs."""

    backend_name = "supabase_storage"

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.Client | None = None,
        encrypt_at_rest: bool = True,
    ) -> None:
        self.settings = settings
        self.base_url = settings.supabase_url.rstrip("/")
        self.service_key = (
            settings.supabase_service_role_key.get_secret_value().strip()
            if settings.supabase_service_role_key
            else ""
        )
        self.bucket = settings.supabase_storage_bucket.strip() or "ultron-private-files"
        self.encrypt_at_rest = encrypt_at_rest
        self._client = http_client

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        hdrs = {
            "Authorization": f"Bearer {self.service_key}",
            "apikey": self.service_key,
        }
        if content_type:
            hdrs["Content-Type"] = content_type
        return hdrs

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self.base_url}{path}"
        if self._client is not None:
            return self._client.request(method, url, **kwargs)
        with httpx.Client(timeout=20.0) as client:
            return client.request(method, url, **kwargs)

    def _assert_tenant_path(self, tenant_id: str, storage_ref: str, *, expect_trash: bool = False) -> str:
        prefix = f"supabase://{self.bucket}/"
        if not storage_ref.startswith(prefix):
            raise AuthorizationError("Invalid Supabase storage reference.")
        rel = storage_ref.removeprefix(prefix)
        expected_scope = f"_trash/{tenant_id}/" if expect_trash else f"{tenant_id}/"
        if not rel.startswith(expected_scope) or ".." in rel:
            raise AuthorizationError("Cross-tenant Supabase object path access denied.")
        return rel

    def upload_bytes(self, *, tenant_id: str, object_key: str, data: bytes, mime_type: str) -> str:
        clean_key = object_key.lstrip("/").replace("..", "")
        rel_path = f"{tenant_id}/{clean_key}"
        payload_bytes = data
        upload_mime = mime_type
        if self.encrypt_at_rest:
            ct, nonce = encrypt_vault_secret(
                base64.b64encode(data).decode("ascii"),
                master_secret=self.settings.vault_master_key.get_secret_value(),
                aad=f"file:{tenant_id}:{rel_path}",
            )
            payload_bytes = json.dumps({"v": 1, "enc": "AES-256-GCM", "ct": ct, "nonce": nonce}).encode("utf-8")
            upload_mime = "application/octet-stream"

        resp = self._request(
            "POST",
            f"/storage/v1/object/{self.bucket}/{rel_path}",
            headers={**self._headers(upload_mime), "x-upsert": "true"},
            content=payload_bytes,
        )
        if resp.status_code not in {200, 201}:
            raise RuntimeError(f"Supabase Storage upload failed (HTTP {resp.status_code}): {resp.text[:240]}")
        return f"supabase://{self.bucket}/{rel_path}"

    def download_bytes(self, *, tenant_id: str, storage_ref: str) -> bytes:
        rel_path = self._assert_tenant_path(tenant_id, storage_ref, expect_trash=False)
        resp = self._request(
            "GET",
            f"/storage/v1/object/authenticated/{self.bucket}/{rel_path}",
            headers=self._headers(),
        )
        if resp.status_code == 404:
            raise NotFoundError("Object not found in Supabase Storage.")
        if resp.status_code != 200:
            raise RuntimeError(f"Supabase Storage download failed (HTTP {resp.status_code}): {resp.text[:240]}")
        raw = resp.content
        if self.encrypt_at_rest:
            try:
                env = json.loads(raw.decode("utf-8"))
                if env.get("enc") == "AES-256-GCM":
                    plain_b64 = decrypt_vault_secret(
                        env["ct"],
                        env["nonce"],
                        master_secret=self.settings.vault_master_key.get_secret_value(),
                        aad=f"file:{tenant_id}:{rel_path}",
                    )
                    return base64.b64decode(plain_b64)
            except Exception:
                pass
        return raw

    def soft_delete(self, *, tenant_id: str, storage_ref: str) -> str:
        rel_path = self._assert_tenant_path(tenant_id, storage_ref, expect_trash=False)
        trash_rel = f"_trash/{rel_path}"
        resp = self._request(
            "POST",
            "/storage/v1/object/move",
            headers=self._headers("application/json"),
            json={"bucketId": self.bucket, "sourceKey": rel_path, "destinationKey": trash_rel},
        )
        if resp.status_code not in {200, 201}:
            raise RuntimeError(f"Supabase Storage soft-delete failed (HTTP {resp.status_code}): {resp.text[:240]}")
        return f"supabase://{self.bucket}/{trash_rel}"

    def restore(self, *, tenant_id: str, trash_ref: str, original_ref: str) -> str:
        trash_rel = self._assert_tenant_path(tenant_id, trash_ref, expect_trash=True)
        orig_rel = self._assert_tenant_path(tenant_id, original_ref, expect_trash=False)
        resp = self._request(
            "POST",
            "/storage/v1/object/move",
            headers=self._headers("application/json"),
            json={"bucketId": self.bucket, "sourceKey": trash_rel, "destinationKey": orig_rel},
        )
        if resp.status_code not in {200, 201}:
            raise RuntimeError(f"Supabase Storage restore failed (HTTP {resp.status_code}): {resp.text[:240]}")
        return f"supabase://{self.bucket}/{orig_rel}"

    def create_signed_url(
        self,
        *,
        tenant_id: str,
        file_id: str,
        storage_ref: str,
        expires_in_seconds: int = 300,
    ) -> dict[str, Any]:
        rel_path = self._assert_tenant_path(tenant_id, storage_ref, expect_trash=False)
        ttl = max(30, min(3600, int(expires_in_seconds)))
        resp = self._request(
            "POST",
            f"/storage/v1/object/sign/{self.bucket}/{rel_path}",
            headers=self._headers("application/json"),
            json={"expiresIn": ttl},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Supabase Storage signed URL creation failed (HTTP {resp.status_code}): {resp.text[:240]}")
        body = resp.json()
        signed_path = body.get("signedURL") or body.get("signedUrl") or ""
        full_url = f"{self.base_url}/storage/v1{signed_path}" if signed_path.startswith("/") else signed_path
        return {
            "storage_backend": self.backend_name,
            "signed_url": full_url,
            "expires_in_seconds": ttl,
            "expires_at_epoch": int(time.time()) + ttl,
            "private_bucket": True,
        }


def get_storage_adapter(settings: Settings) -> BaseStorageAdapter:
    """Return SupabaseStorageAdapter when Supabase credentials are configured; otherwise LocalStorageAdapter."""
    if (
        settings.supabase_url.strip()
        and settings.supabase_service_role_key
        and settings.supabase_service_role_key.get_secret_value().strip()
    ):
        return SupabaseStorageAdapter(settings)
    return LocalStorageAdapter(settings)
