# Trading Agent Ultra (v1 Skeleton)

This repository contains a modular Python + LangGraph skeleton for an A-share research assistant.

## Product docs
- PRD (v1 baseline): [`docs/PRD_v1.md`](docs/PRD_v1.md)
- Release + iteration checklist: [`docs/V1_release_iteration_checklist.md`](docs/V1_release_iteration_checklist.md)
- Macro intel module doc: [`docs/macro_intel_v1.md`](docs/macro_intel_v1.md)

## Storage decisions (locked)
- Structured source-of-truth storage: Supabase PostgreSQL.
- Access pattern: direct PostgreSQL connection from Python (`SQLAlchemy` + `psycopg`).
- Migrations: Alembic.
- Security (v1): service-role backend access, dedicated schema, RLS deferred.
- Vector/semantic store: optional auxiliary layer only (not source-of-truth).

## Key env vars
- `SUPABASE_DB_URL`
- `SUPABASE_SCHEMA`
- `APP_ENV`

Recommended `SUPABASE_DB_URL` format for v1:
- Use Supabase Session Pooler (port `6543`) with `sslmode=require`.
- Example: `postgresql+psycopg://postgres.<project-ref>:<password>@<pooler-host>:6543/postgres?sslmode=require`

## Modules
- `macro/`: macro thesis snapshots, deltas, mappings, daily run logs.
- `industry/`: industry thesis snapshots/latest, deltas, refresh metadata.
- `company/`: company context snapshots and analysis outputs.
- `integration/`: macro->industry linkage and recheck queue.
- `contracts/`: shared DTO contracts and enums.

## Run migrations
```bash
alembic upgrade head
```

## Macro cron (08:00 / 20:00 Asia/Shanghai)
```bash
chmod +x scripts/run_macro_intel_cron.sh scripts/setup_macro_cron.sh
./scripts/setup_macro_cron.sh --install
./scripts/setup_macro_cron.sh --show
```
