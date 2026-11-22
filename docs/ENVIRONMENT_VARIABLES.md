# ULTRON OS 2026 — Environment Variables & Secret Management

Never commit `.env` files, API keys, service-role keys, or private credentials to GitHub or Google Drive. Use `.env.example` as a template and configure production values via Vercel Environment Variables, Cloudflare Worker Secrets, and Supabase Project Settings.

## Variable Matrix

| Variable | Required | Default | Purpose |
| :--- | :--- | :--- | :--- |
| `ULTRON_ENV` | Recommended | `development` | Runtime mode: `development`, `test`, `staging`, `production` |
| `ULTRON_APP_NAME` | No | `ULTRON OS 2026 Backend` | OpenAPI title & health response service name |
| `ULTRON_APP_VERSION` | No | `2026.1.0` | Application version |
| `ULTRON_HOST` | No | `0.0.0.0` | Uvicorn bind host |
| `ULTRON_PORT` | No | `8000` | Uvicorn bind port |
| `ULTRON_LOG_LEVEL` | No | `INFO` | Structured JSON logger level |
| `ULTRON_CORS_ORIGINS` | Recommended | `http://localhost:3000,http://localhost:5173` | Comma-separated allowed CORS origins |
| `ULTRON_JWT_SECRET` | **Required in prod** | Ephemeral dev CSPRNG | HS256 JWT signing secret (`>= 32` chars; placeholders rejected in production) |
| `ULTRON_VAULT_MASTER_KEY` | **Required in prod** | Ephemeral dev CSPRNG | HKDF input key material for AES-256-GCM vault (`>= 32` chars) |
| `ULTRON_ACCESS_TOKEN_TTL_SECONDS` | No | `900` | Access JWT lifetime in seconds (15 min default) |
| `ULTRON_REFRESH_TOKEN_TTL_DAYS` | No | `7` | Rotating refresh token lifetime in days |
| `ULTRON_MAX_FAILED_LOGINS` | No | `5` | Consecutive failed logins before lockout |
| `ULTRON_LOCKOUT_MINUTES` | No | `15` | Account lockout duration |
| `ULTRON_APPROVAL_SOFT_LIMIT_USD` | No | `50.0` | ApprovalGate automatic financial soft limit (USD) |
| `ULTRON_DEFAULT_TENANT_ID` | No | `TENANT-ULTRON-01` | Default organization tenant identifier |
| `ULTRON_DATABASE_URL` | **Required in prod** | `""` (uses SQLite WAL) | SQLAlchemy Postgres URL (e.g. `postgresql+psycopg://postgres:<pw>@db.<ref>.supabase.co:5432/postgres?sslmode=require`) |
| `ULTRON_SQLITE_PATH` | Dev/Test | `./data/ultron_os_2026.db` | Local SQLite WAL file path when `ULTRON_DATABASE_URL` is unset |
| `SUPABASE_URL` | Optional | `""` | Supabase project URL (`https://<ref>.supabase.co`) |
| `SUPABASE_ANON_KEY` | Optional | `None` | Supabase public anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Optional | `None` | Supabase service role key (server-side only; never expose to frontend) |
| `GEMINI_API_KEY` | Optional | `None` | Google Gemini API key (sent via `x-goog-api-key` header) |
| `GEMINI_BASE_URL` | No | `https://generativelanguage.googleapis.com/v1beta` | Gemini API base URL |
| `GEMINI_MODEL_FAST` | No | `gemini-2.0-flash-lite` | Tier 1 fast operations model |
| `GEMINI_MODEL_STANDARD` | No | `gemini-2.0-flash` | Tier 2–3 standard/engineering model |
| `GEMINI_MODEL_REASONING` | No | `gemini-2.5-pro` | Tier 4–5 deep reasoning & orchestration model |
| `GEMINI_MODEL_EMBEDDING` | No | `text-embedding-004` | Semantic memory embedding model |
| `VERCEL_TOKEN` | Optional | `None` | Vercel API token for deployment/project verification |
| `VERCEL_PROJECT_ID` | Optional | `""` | Vercel project ID |
| `VERCEL_ORG_ID` | Optional | `""` | Vercel team/organization ID |
| `VERCEL_WEBHOOK_SECRET` | Optional | `None` | HMAC-SHA1 secret for validating Vercel webhooks |
| `CLOUDFLARE_API_TOKEN` | Optional | `None` | Scoped Cloudflare API token for verification & Workers KV |
| `CLOUDFLARE_ACCOUNT_ID` | Optional | `""` | Cloudflare account ID |
| `CLOUDFLARE_ZONE_ID` | Optional | `""` | Cloudflare DNS zone ID |
| `CLOUDFLARE_KV_NAMESPACE_ID` | Optional | `""` | Cloudflare Workers KV namespace ID |
| `CLOUDFLARE_R2_BUCKET` | Optional | `""` | Cloudflare R2 bucket name |
| `CLOUDFLARE_TURNSTILE_SECRET_KEY` | Optional | `None` | Cloudflare Turnstile server-side secret |

## Generating Production Secrets

```bash
python3 -c "import secrets; print('ULTRON_JWT_SECRET=' + secrets.token_urlsafe(48))"
python3 -c "import secrets; print('ULTRON_VAULT_MASTER_KEY=' + secrets.token_urlsafe(48))"
```
