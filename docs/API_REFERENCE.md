# ULTRON OS 2026 — REST API Reference

Interactive OpenAPI documentation is automatically served at `/docs` (Swagger UI) and `/openapi.json`.

All `/api/v1/*` endpoints (except `/api/v1/auth/bootstrap-owner`, `/api/v1/auth/login`, and `/api/v1/auth/refresh`) require:
- `Authorization: Bearer <access_token>`
- Optional `X-Tenant-ID: <tenant_id>` (must match authenticated principal's bound tenant; mismatches return `403`).

All domain errors return a standardized JSON envelope:
```json
{
  "error": {
    "code": "AUTHORIZATION_ERROR",
    "message": "Role 'OPERATOR' lacks required permission 'approvals:decide'.",
    "details": {},
    "request_id": "req_a1b2c3d4e5f6"
  }
}
```

## Health & Integrations

| Method | Path | Auth / Permission | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health/live` | Public | Lightweight liveness probe |
| `GET` | `/health/ready` | Public | Database connectivity probe & non-sensitive runtime summary |
| `GET` | `/health` | Public | Combined health + static integration configuration status |
| `GET` | `/api/v1/integrations/status` | `integrations:verify` | Static configuration status for Supabase, Gemini, Vercel, Cloudflare |
| `POST` | `/api/v1/integrations/verify` | `integrations:verify` | Live HTTP verification probes against configured cloud providers |

## Authentication & RBAC (`/api/v1/auth`)

| Method | Path | Auth / Permission | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/bootstrap-owner` | Public (one-time/tenant) | Initialize tenant OWNER account (`409` if already initialized) |
| `POST` | `/api/v1/auth/login` | Public | Argon2id login returning `access_token` (JWT) + `refresh_token` |
| `POST` | `/api/v1/auth/refresh` | Public | Rotate refresh token and revoke previous session JTI |
| `POST` | `/api/v1/auth/logout` | Authenticated | Immediately revoke current session JTI |
| `GET` | `/api/v1/auth/me` | Authenticated | Return caller identity, role, tenant, and permissions |
| `POST` | `/api/v1/auth/users` | `users:manage` (`OWNER`/`ADMIN`) | Create tenant user (`ADMIN`, `OPERATOR`, `VIEWER`, `AGENT`) |
| `GET` | `/api/v1/auth/users` | `users:manage` | List tenant users (never returns password hashes) |

## Specialist Agents & NEON Router (`/api/v1/agents`)

| Method | Path | Permission | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/agents` | `agents:read` | List 60 agents (`?tier=CORE_25\|EXTENSIBLE_35&domain=...&capability_state=...`) |
| `GET` | `/api/v1/agents/reasoning-tiers` | `agents:read` | List 5-tier NEON model routing matrix |
| `POST` | `/api/v1/agents/route` | `agents:read` | Preview agent/tier routing and ApprovalGate risk assessment |
| `GET` | `/api/v1/agents/{agent_id}` | `agents:read` | Get details for a specific agent (`AGT-01`–`AGT-60`) |
| `PATCH` | `/api/v1/agents/{agent_id}/state` | `agents:manage` | Update agent honest capability state |
| `POST` | `/api/v1/agents/{agent_id}/invoke` | `agents:invoke` | Invoke specialist agent via Gemini API (or honest offline fallback) |

## ARGON Tasks & Orchestration (`/api/v1/tasks`)

| Method | Path | Permission | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/tasks` | `tasks:create` | Create & plan DAG task (triggers ApprovalGate if high-risk or >$50) |
| `GET` | `/api/v1/tasks` | `tasks:read` | List tenant tasks (`?state=...&limit=...`) |
| `GET` | `/api/v1/tasks/{task_id}` | `tasks:read` | Get task details including DAG steps and outputs |
| `POST` | `/api/v1/tasks/{task_id}/execute` | `tasks:execute` | Execute READY task steps in topological order |
| `POST` | `/api/v1/tasks/{task_id}/transition` | `tasks:execute` | Apply validated lifecycle state transition |
| `POST` | `/api/v1/tasks/{task_id}/cancel` | `tasks:cancel` | Cancel an active task |

## ApprovalGate Governance (`/api/v1/approvals`)

| Method | Path | Permission | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/approvals` | `approvals:read` | List ApprovalGate requests (`?status=PENDING\|APPROVED\|REJECTED`) |
| `GET` | `/api/v1/approvals/{approval_id}` | `approvals:read` | Inspect approval request details |
| `POST` | `/api/v1/approvals/{approval_id}/decide` | `approvals:decide` (`OWNER`/`ADMIN`) | Approve (`READY`) or reject (`CANCELLED`) a pending request |

## Multi-Tier Memory (`/api/v1/memory`)

| Method | Path | Permission | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/memory` | `memory:write` | Store `WORKING`, `EPISODIC`, or `SEMANTIC` memory with vector embedding |
| `POST` | `/api/v1/memory/search` | `memory:read` | Hybrid semantic cosine + lexical similarity recall |
| `DELETE` | `/api/v1/memory/{memory_id}` | `memory:delete` | Delete a tenant memory entry |
| `POST` | `/api/v1/memory/prune` | `memory:delete` | Prune expired TTL memories |

## Governed Tool Harness (`/api/v1/tools`)

| Method | Path | Permission | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/tools` | `tools:read` | List registered tools and JSON input schemas |
| `POST` | `/api/v1/tools/{tool_name}/execute` | `tools:execute` (+ tool perm) | Execute a governed tool with SSRF/ApprovalGate checks |
| `GET` | `/api/v1/tools/executions/history` | `tools:read` | View tenant tool execution logs |

## ARGON Cryptographic Vault (`/api/v1/vault`)

| Method | Path | Permission | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/vault/secrets` | `vault:write` (`OWNER`/`ADMIN`) | Encrypt and store/rotate AES-256-GCM secret |
| `GET` | `/api/v1/vault/secrets` | `vault:read` (`OWNER`/`ADMIN`) | List secret metadata only (never returns secret values) |
| `GET` | `/api/v1/vault/secrets/{name}/reveal` | `vault:read` | Decrypt secret for owning tenant (audit-logged) |
| `DELETE` | `/api/v1/vault/secrets/{name}` | `vault:write` | Delete secret from vault |

## Immutable Audit Ledger (`/api/v1/audit`)

| Method | Path | Permission | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/audit/logs` | `audit:read` | Query tenant audit events (`?action=...&limit=...`) |
| `GET` | `/api/v1/audit/verify` | `audit:read` | Verify SHA-256 hash-chain integrity across all audit entries |
