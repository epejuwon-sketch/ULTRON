# Caravan & ULTRON OS — Production Deployment, Backup, Recovery & Rollback Runbook

## 1. Environment Separation
| Environment | `ULTRON_ENV` | Database | Rate Limiter | Live Payments |
|---|---|---|---|---|
| Local Development | `development` | SQLite WAL (`./ultron_local.db`) or local Postgres | `in_memory` | Disabled (`false`) |
| Staging | `staging` | Dedicated Staging Supabase PostgreSQL (`sslmode=require`, port `6543` pooler) | `redis` (`ULTRON_REDIS_URL`) | Disabled (`false`, sandbox only) |
| Production | `production` | Dedicated Production Supabase PostgreSQL (`sslmode=require`, port `6543` pooler) | `redis` (`ULTRON_REDIS_URL`) | Disabled until explicit owner authorization |

## 2. Required Environment Variable Validation
On startup, `Settings` (`backend/app/core/config.py`) enforces:
- `ULTRON_DATABASE_URL`: PostgreSQL URI required in `staging`/`production` (SQLite is rejected).
- `ULTRON_JWT_SECRET` & `ULTRON_VAULT_MASTER_KEY`: Ephemeral dev keys are rejected in `production`.
- `ULTRON_CORS_ORIGINS`: Explicit allowed origins (no wildcard `*` with credentials in production).
- `ULTRON_REDIS_URL`: Required for distributed rate limiting across multiple API replicas.
- `ULTRON_GEMINI_API_KEY`: Optional; if absent, NEON/BI operate in deterministic degraded mode.
- `ULTRON_FLUTTERWAVE_WEBHOOK_HASH` / payment secrets: Stored in backend/VAULT only, never in frontend env.

## 3. Database Migration Procedure
1. Take a pre-migration snapshot/backup in Supabase (Dashboard -> Database -> Backups).
2. Run ordered SQL migrations `001` through `013` from `backend/migrations/supabase/` (tracked in `schema_migrations` via `MIGRATION_REGISTRY` in `backend/app/db/session.py`).
3. Verify `/health/ready` returns `status: "ready"` and `/api/v1/monitoring/overview` lists `001`..`013` in `applied_migrations`.

## 4. Persistent Worker Startup
The persistent worker executes ARGON scheduled discovery, `CARAVAN_DEADLINE_SWEEP`, `CARAVAN_NOTIFICATION_DISPATCH`, and `CARAVAN_SUBSCRIPTION_LIFECYCLE`:
```bash
cd backend
python -m worker 5.0
```
- Deploy as a dedicated always-on service (systemd / Docker / Railway / Fly.io), NOT inside serverless HTTP functions.
- Monitor `worker_heartbeats` via `GET /api/v1/monitoring/overview`.

## 5. Backup & Recovery Runbook
- **Automated Backups**: Enable Supabase Point-in-Time Recovery (PITR) + daily logical `pg_dump` backups encrypted at rest.
- **Recovery Steps**:
  1. Put API in maintenance mode / pause worker (`SIGTERM` graceful stop).
  2. Restore Supabase PITR to target timestamp or restore `pg_dump` to a new database instance.
  3. Verify `schema_migrations` integrity and row counts (`users`, `caravan_customer_accounts`, `caravan_funding_opportunities`, `caravan_payment_events`).
  4. Resume API and `python -m worker`.

## 6. Rollback Procedure
1. Roll back Vercel/frontend deployment to previous immutable build.
2. Roll back backend container/service to previous Git SHA.
3. Never run destructive `DROP TABLE` rollbacks on customer data; use forward-compatible additive migrations (`012`, `013` are additive and safe).

## 7. Production Smoke-Test Checklist
- [ ] `GET /health/live` returns `200 OK` (`status: ok`).
- [ ] `GET /health/ready` returns `200 OK` (`status: ready`, `database.healthy: true`).
- [ ] `POST /api/v1/auth/register` -> `POST /api/v1/auth/login` -> `GET /api/v1/auth/me` succeeds with `VIEWER` role.
- [ ] `POST /api/v1/auth/password-reset/request` returns generic non-enumerating `200 OK`.
- [ ] `GET /api/v1/caravan/pricing` returns `FREE`, `PRO`, `INSTITUTIONAL` plans.
- [ ] `GET /api/v1/caravan/opportunities` returns only `VERIFIED` listings to customers.
- [ ] `GET /api/v1/monitoring/overview` shows fresh `worker_heartbeats` timestamp.
