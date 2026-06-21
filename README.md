# Facebook / Meta Ads ETL

Production-grade ETL for Meta Graph API data into PostgreSQL and Google BigQuery, with multi-tenant profile support. Designed for agencies running many ad accounts behind a single deployment.

For exhaustive command-by-command behaviour see [DOCUMENTATION.md](DOCUMENTATION.md). For oncall procedures see [RUNBOOK.md](RUNBOOK.md). For BigQuery setup see [BIGQUERY_RUNBOOK.md](BIGQUERY_RUNBOOK.md). For Power BI modeling see [POWERBI_MODEL.md](POWERBI_MODEL.md).

## Quickstart

```bash
git clone <repo-url>
cd facebook_etl_new_big

cp .env.example .env
# fill in META_ACCESS_TOKEN, DB_CONN_STRING, optionally BQ_*

pip install -r requirements.txt
python -m alembic upgrade head    # create / migrate the schema
python main.py health-check       # validate Meta / Postgres / BigQuery
python main.py run-daily --to-bigquery
```

## Quickstart with Docker

```bash
cp .env.example .env              # fill in credentials
docker compose up -d postgres     # local Postgres
docker compose run --rm etl health-check
docker compose run --rm etl run-daily --to-bigquery
docker compose --profile scheduler up -d   # background scheduler
```

The container image runs `python main.py` as its entrypoint, so any CLI command works as `docker compose run --rm etl <command> [args...]`.

## Configuration

All configuration is environment-driven. Copy [.env.example](.env.example) and fill in the variables.

| Required | Variable |
|---|---|
| Meta API | `META_ACCESS_TOKEN`, `META_API_VERSION`, `META_AD_ACCOUNT_IDS` |
| Postgres | `DB_CONN_STRING` |
| BigQuery (optional) | `BQ_PROJECT_ID`, `BQ_DATASET`, `BQ_LOCATION`, `BQ_CREDENTIALS_PATH` |
| Alerts (optional) | `ALERT_SLACK_WEBHOOK_URL`, `ALERT_WEBHOOK_URL`, `ALERT_ENVIRONMENT` |
| Profiles (optional) | `REGISTERED_PROFILES`, `DB_CONN_STRING_<P>`, `META_AD_ACCOUNT_IDS_<P>`, `BQ_*_<P>` |

`REGISTERED_PROFILES` is an allow-list. With it set, an unknown `--db-profile` value is rejected at config-load time (prevents typos from silently falling back to the default tenant). Without it, the system still rejects profile names that have no matching env vars at all.

## Migrations

Schema changes are managed with Alembic.

```bash
python -m alembic upgrade head           # apply pending migrations
python -m alembic revision -m "add foo"  # create a new revision
python -m alembic downgrade -1           # roll back one
```

For multi-profile deployments target a specific database via:

```bash
ALEMBIC_DB_PROFILE=agency python -m alembic upgrade head
```

The runtime schema_manager still creates missing columns at write time, but Alembic is the source of truth for major changes (renames, new tables, type changes). The baseline migration is idempotent against a database that was bootstrapped by schema_manager.

## Token rotation

Meta long-lived user tokens expire ~60 days after issue. To rotate:

1. Generate a new short-lived user token in [Graph API Explorer](https://developers.facebook.com/tools/explorer/).
2. Run:
   ```bash
   python scripts/rotate_meta_token.py --short-token <short_token>
   ```
   This exchanges it for a long-lived token via `META_APP_ID` / `META_APP_SECRET` and writes `META_ACCESS_TOKEN` back into `.env`.

System User tokens (recommended for production) do not expire and bypass this step.

## Run history & alerts

Every CLI invocation is recorded in the `etl_run_log` table:

```sql
SELECT command, profile, status, started_at, duration_seconds, rows_loaded, error_message
FROM etl_run_log
ORDER BY started_at DESC
LIMIT 50;
```

If `ALERT_SLACK_WEBHOOK_URL` or `ALERT_WEBHOOK_URL` is configured, failures are pushed to those endpoints automatically.

## Insights resumability

`insights-range` writes a checkpoint row to `etl_insights_checkpoint` after each successfully loaded chunk. Re-running the same range silently skips already-completed chunks; pass `--force` to re-process them.

## CLI

Run `python main.py --help` for the full command list. The most common commands:

```bash
python main.py run-daily --to-bigquery           # full daily pipeline
python main.py accounts-insights --to-bigquery   # 2-hour refresh
python main.py dims-refresh --to-bigquery        # daily dims only
python main.py insights-range 2026-01-01 2026-04-30 --to-bigquery
python main.py full-refresh 2025-01-01 2025-12-31 --to-bigquery
python main.py health-check
python main.py materialize-combined --to-bigquery
```

All commands accept `--db-profile <name>` for multi-tenant routing.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Project layout

See [DOCUMENTATION.md §3](DOCUMENTATION.md#3-directory-structure) for the full directory tree.
