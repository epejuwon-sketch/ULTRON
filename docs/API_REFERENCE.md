# ULTRON OS 2026 — Complete REST & WebSocket API Reference

Interactive OpenAPI 3.1 documentation is served at `/docs` and `/openapi.json`.

All protected `/api/v1/*` routes require `Authorization: Bearer <access_token>` and enforce RBAC + tenant isolation (`X-Tenant-ID` mismatch returns `403`). Mutation routes such as `POST /api/v1/tasks` also support `Idempotency-Key` replay safety.

## 1. Health & 14-Capability Integrations
| Method | Path | Permission | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/health/live`, `/health/ready`, `/health` | Public | Liveness, DB readiness, and static integration summary |
| `GET` | `/api/v1/integrations/status` | `integrations:verify` | Static honest status across all 14 capabilities |
| `POST` | `/api/v1/integrations/verify` | `integrations:verify` | Live HTTP verification probes for configured providers |

## 2. Authentication & RBAC (`/api/v1/auth`)
| Method | Path | Permission | Purpose |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/bootstrap-owner` | Public (1x/tenant) | Initialize tenant OWNER account |
| `POST` | `/api/v1/auth/login` | Public | Argon2id login -> JWT + refresh token (lockout protected) |
| `POST` | `/api/v1/auth/refresh` | Public | Rotate refresh token & revoke previous JTI |
| `POST` | `/api/v1/auth/logout` | Authenticated | Immediately revoke current JTI |
| `GET` | `/api/v1/auth/me` | Authenticated | Caller identity, tenant, and permissions |
| `POST` / `GET` | `/api/v1/auth/users` | `users:manage` | Provision and list tenant users |

## 3. Specialist Agents (`/api/v1/agents`)
| Method | Path | Permission | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/agents` | `agents:read` | List 60 specialist agents + approved extensions |
| `GET` | `/api/v1/agents/{agent_id}` | `agents:read` | Agent summary & task counters |
| `GET` | `/api/v1/agents/{agent_id}/manifest` | `agents:read` | Full manifest, honest `execution_backing`, and performance metrics |
| `PATCH` | `/api/v1/agents/{agent_id}/state` | `agents:manage` | Update agent honest capability state |
| `POST` | `/api/v1/agents/{agent_id}/invoke` | `agents:invoke` | Execute agent via NEON |
| `POST` | `/api/v1/agents/register` | `agents:manage` | Propose dynamic extension agent (gated by ApprovalGate) |
| `POST` / `GET` | `/api/v1/agents/messages` | `agents:invoke` / `read` | Tenant-isolated inter-agent communication bus |

## 4. NEON Intelligence Engine (`/api/v1/neon`)
| Method | Path | Permission | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/neon/models` | `agents:read` | Multi-provider model capability & pricing registry |
| `GET` | `/api/v1/neon/tiers` | `agents:read` | 5-tier reasoning matrix |
| `POST` | `/api/v1/neon/route` | `agents:read` | Preview dynamic agent/tier selection & risk classification |
| `POST` | `/api/v1/neon/complete` | `agents:invoke` | Multi-provider failover completion with structured JSON & tool calling |
| `POST` | `/api/v1/neon/stream` | `agents:invoke` | Server-Sent Events (`text/event-stream`) streamed reasoning |
| `POST` / `GET` | `/api/v1/neon/conversations` | `agents:invoke` / `read` | Create & list multi-turn conversations |
| `GET` / `POST` | `/api/v1/neon/conversations/{id}` & `/messages` | `agents:read` / `invoke` | Read history & send context-aware turn |
| `GET` | `/api/v1/neon/usage` | `monitoring:read` | Token consumption & estimated API cost breakdown |

## 5. ARGON Tasks, Queue & Scheduler (`/api/v1/tasks`, `/api/v1/argon`)
| Method | Path | Permission | Purpose |
| :--- | :--- | :--- | :--- |
| `POST` / `GET` | `/api/v1/tasks` | `tasks:create` / `read` | Plan DAG task (idempotent with `Idempotency-Key`, ApprovalGate enforced) |
| `GET` | `/api/v1/tasks/{id}` | `tasks:read` | Task state, progress, DAG steps, result & verification report |
| `POST` | `/api/v1/tasks/{id}/execute` | `tasks:execute` | Execute parallel DAG waves + independent verification |
| `POST` | `/api/v1/tasks/{id}/enqueue` | `tasks:execute` | Queue task for persistent background worker (`202 Accepted`) |
| `POST` | `/api/v1/tasks/{id}/pause`, `/resume`, `/retry`, `/cancel` | `tasks:execute` / `cancel` | Full lifecycle control & failure recovery |
| `POST` / `GET` | `/api/v1/argon/jobs` & `/jobs/process` | `tasks:execute` / `jobs:manage` | Enqueue, list, and process background worker jobs |
| `POST` / `GET` | `/api/v1/argon/schedules` | `jobs:manage` / `tasks:read` | Manage recurring scheduled jobs |

## 6. ApprovalGate Governance (`/api/v1/approvals`)
| Method | Path | Permission | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/approvals` & `/{id}` | `approvals:read` | List & inspect pending/decided approvals |
| `POST` | `/api/v1/approvals/{id}/decide` | `approvals:decide` | Approve/reject tasks, finance outflows, deployments, comms, & agent extensions |

## 7. Multi-Tier Versioned Memory (`/api/v1/memory`)
| Method | Path | Permission | Purpose |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/memory` | `memory:write` | Store `SHORT_TERM`, `LONG_TERM`, `EPISODIC`, `SEMANTIC`, `PROJECT`, `USER_PREFERENCE` |
| `POST` | `/api/v1/memory/search` | `memory:read` | Hybrid cosine + lexical recall with `PRIVATE` access control |
| `PATCH` / `GET` | `/api/v1/memory/{id}` & `/{id}/history` | `memory:write` / `read` | Create new memory version & inspect revision history |
| `GET` / `PUT` | `/api/v1/memory/preferences` | `memory:read` / `write` | Read & update per-user preferences |
| `DELETE` / `POST` | `/api/v1/memory/{id}` & `/prune` | `memory:delete` | User-controlled deletion & retention TTL pruning |

## 8. Governed Tools, Vault & Audit (`/api/v1/tools`, `/api/v1/vault`, `/api/v1/audit`)
* `GET /api/v1/tools`, `POST /api/v1/tools/{name}/execute`, `GET /api/v1/tools/executions/history` (9 tools including `file_parse`, `code_analyze_python`, SSRF-safe `http_fetch_public`, ApprovalGate-governed `financial_transfer_request`, `email_dispatch_request`, `whatsapp_dispatch_request`).
* `POST/GET /api/v1/vault/secrets`, `GET /api/v1/vault/secrets/{name}/reveal`, `DELETE /api/v1/vault/secrets/{name}` (`OWNER`/`ADMIN` only).
* `GET /api/v1/audit/logs`, `GET /api/v1/audit/verify` (SHA-256 hash chain verification).

## 9. Financial Command Center (`/api/v1/finance`)
* `POST/GET /api/v1/finance/transactions` (revenue, expense, API spend, hosting, project cost, owner distributions — outflows `> $50` and owner distributions gated by ApprovalGate; never executes unverified live payment rails).
* `POST/GET /api/v1/finance/budgets`, `/investments`, `/reserves`.
* `GET /api/v1/finance/reports/summary`, `GET /api/v1/finance/audit`.

## 10. Developer & Coding Infrastructure (`/api/v1/projects`)
* `POST/GET /api/v1/projects`, `GET /api/v1/projects/{id}/repository`, `POST /api/v1/projects/{id}/analyze` (Python AST static analyzer), `POST /api/v1/projects/{id}/code-proposals` (never auto-merges or overwrites).
* `POST/GET /api/v1/projects/{id}/deployments` (production gated by ApprovalGate), `POST /api/v1/projects/{id}/deployments/{dep_id}/rollback`, `GET /api/v1/projects/{id}/activity`.

## 11. Notifications, Settings, Monitoring & WebSocket
* `GET /api/v1/notifications`, `POST /api/v1/notifications/{id}/read`, `POST /api/v1/notifications/read-all`.
* `GET/PUT /api/v1/settings` (includes `OWNER`-only `autonomous_execution_enabled` kill switch).
* `GET /api/v1/monitoring/overview`, `GET /api/v1/monitoring/metrics` (Prometheus text exposition).
* `WS /ws/v1/events?token=<jwt>` (authenticated tenant-scoped real-time event stream).

## 12. Unified Integration Manager & OAuth 2.0 (`/api/v1/integrations`)
* `GET /api/v1/integrations/connections` — Tenant-scoped encrypted connection inventory + Antigravity environment adapter.
* `GET /api/v1/integrations/antigravity?live=true|false` — Honest official Antigravity plugin adapter status.
* `POST /api/v1/integrations/{provider}/connect` — Store AES-256-GCM encrypted credentials (`OWNER`/`ADMIN`).
* `POST /api/v1/integrations/oauth/{provider}/start` & `/callback` — OAuth 2.0 + PKCE (`S256`) flow.
* `POST /api/v1/integrations/{provider}/refresh`, `/verify`, `/disconnect` — Token refresh, live verification, and upstream revocation.

## 13. Google Ecosystem (`/api/v1/google`)
* **Drive:** `GET /drive/files`, `GET /drive/files/{id}/read`, `POST /drive/folders`, `POST /drive/upload`
* **Gmail:** `GET /gmail/messages`, `GET /gmail/threads/{id}`, `POST /gmail/drafts`, `POST /gmail/send-request` (ApprovalGate enforced)
* **Calendar:** `GET /calendar/calendars`, `GET /calendar/events`, `POST /calendar/events`, `POST /calendar/availability`
* **Docs / Sheets / Slides:** `POST /docs`, `GET /docs/{id}`, `POST /docs/{id}/append`, `POST /sheets`, `GET/PUT /sheets/{id}/values`, `POST /slides`, `POST /slides/{id}/slides`
* **Google Cloud:** `GET /cloud/projects`, `GET /cloud/projects/{id}/services`

## 14. GitHub Engineering & Web Research (`/api/v1/github`, `/api/v1/research`)
* `GET /api/v1/github/repos`, `/repos/{owner}/{repo}`, `/branches`, `POST /branches`, `/commits`, `GET/PUT /file` (protected branches blocked), `GET/POST /pulls`, `GET/POST /issues`, `GET /workflows`, `GET /releases`.
* `POST /api/v1/research/search`, `POST /api/v1/research/fetch` (SSRF-safe with preserved citations).

## 15. Multi-Device Connectivity Mesh (`/api/v1/devices`)
* `POST /api/v1/devices/pair/init`, `POST /api/v1/devices/pair/complete`, `GET /api/v1/devices`.
* `POST /api/v1/devices/{id}/heartbeat` (`X-Device-Token`), `PATCH /api/v1/devices/{id}/permissions`, `POST /api/v1/devices/{id}/revoke`.
* `POST /api/v1/devices/{id}/tasks`, `GET /api/v1/devices/{id}/tasks/pending`, `POST /api/v1/devices/{id}/tasks/{tid}/report`.

## 16. Unified Natural-Language Orchestration
* `POST /api/v1/orchestrate` — Plain-language objective uniting Memory recall, authorized Integrations/Devices, NEON routing, ARGON DAG planning/execution, ApprovalGate checkpoints, and independent verification.

## 17. AEGIS Autonomous Security & Defence (`/api/v1/aegis`)
* `GET /api/v1/aegis/posture` — Live security risk score, FIM baseline count, and open incident count.
* `POST /api/v1/aegis/scans`, `GET /api/v1/aegis/scans` — Trigger & list security scans (`FAST`, `FULL`, `DEEP`).
* `GET /api/v1/aegis/incidents`, `POST /api/v1/aegis/incidents/{id}/remediate` — Safe low-risk remediation vs ApprovalGate-gated high-impact remediation.
* `POST /api/v1/aegis/fim/rebaseline`, `POST /api/v1/aegis/inspect-url`, `POST /api/v1/aegis/scan-code`.

## 18. EVOLVE Controlled Self-Development (`/api/v1/evolve`)
* `GET/POST /api/v1/evolve/proposals` — Propose self-development capability improvements.
* `POST /api/v1/evolve/proposals/{id}/verify` — Run isolated syntax/AST checks + AEGIS security scan and submit to ApprovalGate if clean.
* `POST /api/v1/evolve/proposals/{id}/promote` — Promote only after explicit ApprovalGate `APPROVED` decision.
* `POST /api/v1/evolve/proposals/{id}/rollback` — Roll back promoted proposal with audit trail.

## 19. SENTINEL Passkeys / WebAuthn & Recovery (`/api/v1/sentinel`)
* `GET /api/v1/sentinel/passkeys`, `POST /api/v1/sentinel/passkeys/register/options`, `POST /api/v1/sentinel/passkeys/register/complete`, `POST /api/v1/sentinel/passkeys/{credential_id}/revoke` (platform authenticators including iPhone Face ID — zero raw biometrics stored server-side).
* `POST /api/v1/sentinel/reauth/options`, `POST /api/v1/sentinel/reauth/complete` (issues 5-min sensitive-action `reauth_token`).
* `POST /api/v1/sentinel/recovery-codes/generate`, `POST /api/v1/sentinel/recovery-codes/verify`.

## 20. ORBIT Authorized Location & Geofences (`/api/v1/devices/*`)
* `POST /api/v1/devices/{id}/location` (`X-Device-Token`; requires `location` permission and unpaused state).
* `GET /api/v1/devices/locations`, `POST /api/v1/devices/{id}/location/control` (`PAUSE` | `RESUME` | `REVOKE`).
* `POST /api/v1/devices/{id}/location/alerts`, `GET /api/v1/devices/location/alerts`.

## 21. ATLAS Personal Assistant, 9-Status Orders & World Intelligence (`/api/v1/atlas`)
* `POST /api/v1/atlas/shopping/research` — Web-backed product comparison with citations.
* `GET/POST /api/v1/atlas/orders`, `PATCH /api/v1/atlas/orders/{id}/tracking` (9 verified statuses, ApprovalGate protected).
* `GET/PUT /api/v1/atlas/intelligence/topics`, `GET /api/v1/atlas/intelligence/weather` (Open-Meteo live/honest offline), `POST /api/v1/atlas/briefings/generate`, `GET /api/v1/atlas/briefings`.

## 22. Finance Tokenized Payment Methods & Forecast (`/api/v1/finance`)
* `POST/GET /api/v1/finance/payment-methods`, `PATCH /api/v1/finance/payment-methods/{id}/preferred`, `DELETE /api/v1/finance/payment-methods/{id}` (`VISA`, `MASTERCARD`, `VERVE`, `AMEX` — masked `last4` only; raw PAN/CVV rejected).
* `GET /api/v1/finance/transactions?scope=PERSONAL|BUSINESS`, `GET /api/v1/finance/reports/summary?scope=PERSONAL|BUSINESS`, `GET /api/v1/finance/forecast`.

## 23. FILE HUB (`/api/v1/files`)
* `POST /api/v1/files/upload` (multipart upload with AEGIS scan, VAULT secret redaction, prompt-injection tagging, multi-format extraction).
* `POST /api/v1/files/generate`, `POST /api/v1/files/generate-zip`, `GET /api/v1/files`, `GET /api/v1/files/{id}`, `GET /api/v1/files/{id}/download`.

## 24. FORGE & Sandboxed Live Preview (`/api/v1/forge`)
* `GET/POST /api/v1/forge/projects` (`react_vite`, `web_app`, `dashboard`, `landing_page`, `fastapi_service`).
* `GET /api/v1/forge/projects/{id}`, `GET /api/v1/forge/projects/{id}/preview` (CSP-sandboxed HTML preview).

## 25. Creative Studio, Voice, Visual, BRIDGE, PULSE & CARAVAN BI
* `POST /api/v1/creative/voice/turn`, `POST /api/v1/creative/visual/analyze`, `GET/POST /api/v1/creative/jobs`.
* `POST /api/v1/bridge/share`, `GET /api/v1/bridge/shares` (iPhone PWA Web Share Target with AEGIS URL validation).
* `GET/POST /api/v1/pulse/pages`, `GET /api/v1/pulse/pages/{id}/live`.
* `POST /api/v1/caravan/events`, `GET /api/v1/caravan/summary` (real aggregated BI; zero fabricated metrics).

## 26. TURBO Performance & Benchmarks (`/api/v1/turbo`)
* `GET /api/v1/turbo/stats`, `POST /api/v1/turbo/cache/flush`, `POST /api/v1/turbo/benchmarks`.

