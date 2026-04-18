# Trading Agent Ultra (v1 Skeleton)

This repository contains a modular Python + LangGraph skeleton for an A-share research assistant.

## Product docs
- PRD (v1 baseline): [`docs/PRD_v1.md`](docs/PRD_v1.md)
- Release + iteration checklist: [`docs/V1_release_iteration_checklist.md`](docs/V1_release_iteration_checklist.md)
- Macro intel module doc: [`docs/macro_intel_v1.md`](docs/macro_intel_v1.md)
- Macro eval Week 1 runbook: [`docs/macro_eval_week1_runbook.md`](docs/macro_eval_week1_runbook.md)

## Storage decisions (locked)
- Structured source-of-truth storage: Supabase PostgreSQL.
- Access pattern: direct PostgreSQL connection from Python (`SQLAlchemy` + `psycopg`).
- Migrations: Alembic.
- Security (v1): service-role backend access, dedicated schema, RLS deferred.
- Vector/semantic store: optional auxiliary layer only (not source-of-truth).

## Key env vars
- `SUPABASE_DB_URL`
- `SUPABASE_SCHEMA`
- `TUSHARE_API_KEY`
- `TAVILY_API_KEY`
- `BOCHA_API_KEY`
- `RESEND_API_KEY`
- `RESEND_FROM_EMAIL`

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

## Stock/financial table updates (manual)
```bash
# 1) Update daily stock price table for a trade date
.venv/bin/python scripts/run_stock_price_update.py --trade-date 2026-04-15

# 2) Update financial table (auto period by month window)
.venv/bin/python scripts/run_financial_data_update.py --trade-date 2026-04-15

# 3) Run both updates in one command
.venv/bin/python scripts/run_scheduled_table_updates.py --trade-date 2026-04-15
```

## Macro cron (08:00 / 20:00 Asia/Shanghai)
```bash
chmod +x scripts/run_macro_intel_cron.sh scripts/setup_macro_cron.sh
./scripts/setup_macro_cron.sh --install
./scripts/setup_macro_cron.sh --show
```

## Macro digest email (24h events/views)
```bash
.venv/bin/python scripts/send_macro_digest_email.py --hours 24 --dry-run
```

## Macro eval email (daily human review samples)
```bash
.venv/bin/python scripts/send_macro_digest_email.py --eval-mode --dry-run
```

## Macro eval weekly report (from feedback CSV)
```bash
.venv/bin/python scripts/build_macro_eval_weekly_report.py --input-csv logs/macro_eval_feedback_week.csv --week-label 2026-W15
```
