# Meta ETL Runbook

Operational procedures for incident response, routine maintenance, and onboarding. Audience: oncall engineer or agency operator.

---

## 1. Did the last run succeed?

```sql
SELECT command, profile, status, started_at, duration_seconds, rows_loaded, error_message
FROM etl_run_log
ORDER BY started_at DESC
LIMIT 20;
```

A `STARTED` row that's older than the expected duration indicates a hard crash (the wrap context manager couldn't write a final state). A `FAILED` row carries the exception text in `error_message`.

If alerts are configured, failures show up in Slack / your webhook destination automatically. Check `ALERT_SLACK_WEBHOOK_URL` and `ALERT_WEBHOOK_URL` in `.env` if you expected an alert and didn't get one.

---

## 2. Re-run a failed window

`insights-range` is checkpointed: a re-run skips chunks already in `etl_insights_checkpoint`.

```bash
# Same args as the failed run; it will resume from the failed chunk.
python main.py insights-range 2026-01-01 2026-04-30 --to-bigquery

# Force re-process every chunk (e.g. after a transform bug fix):
python main.py insights-range 2026-01-01 2026-04-30 --to-bigquery --force
```

To re-process a single window without `--force`:

```sql
DELETE FROM etl_insights_checkpoint
WHERE since = '2026-03-15' AND until = '2026-03-21'
  AND profile = 'agency' AND level = 'ad' AND breakdowns_key = 'none';
```

---

## 3. Rotate the Meta access token

Long-lived user tokens expire ~60 days after issue. System User tokens do not expire and are the recommended production choice.

```bash
# 1. Get a fresh short-lived token from Graph API Explorer.
# 2. Exchange and persist:
python scripts/rotate_meta_token.py --short-token EAAG...
# 3. Verify:
python main.py health-check
```

`META_APP_ID` and `META_APP_SECRET` must be set in `.env`.

---

## 4. Add a column

Two paths depending on the source.

**API field that arrives in pipeline JSON:**
1. Re-run the affected pipeline once. New fields are auto-registered as `pending` rows in `data/api_field_rename_template.csv` and logged at WARN.
2. Edit the CSV: set `rename_to` and change `status` to `approved`.
3. Re-run the pipeline. The schema_manager will add the column automatically.

**Manual / derived column:**
1. `python -m alembic revision -m "add fact_meta_delivery_ad.my_col"`
2. Edit the generated revision in `migrations/versions/`.
3. `python -m alembic upgrade head`

---

## 5. Add a new ad account (existing profile)

1. Append a row to `data/account_registry.csv`:
   ```csv
   act_999999999,Client X,1,agency,TRUE,
   ```
2. Run accounts pipelines:
   ```bash
   python main.py accounts-info --db-profile agency --to-bigquery
   python main.py accounts-registry --db-profile agency --to-bigquery
   python main.py dims-refresh --db-profile agency --to-bigquery
   ```
3. Backfill insights:
   ```bash
   python main.py insights-range 2026-01-01 2026-04-30 --db-profile agency --to-bigquery
   ```

---

## 6. Add a new profile (new tenant)

1. Add to `.env`:
   ```env
   REGISTERED_PROFILES=agency,client,newtenant
   DB_CONN_STRING_NEWTENANT=postgresql://user:pass@host:5432/newtenant_db
   META_AD_ACCOUNT_IDS_NEWTENANT=act_111,act_222
   BQ_PROJECT_ID_NEWTENANT=gcp-newtenant-project
   BQ_DATASET_NEWTENANT=meta_ads_newtenant
   BQ_LOCATION_NEWTENANT=US
   ```
2. Migrate the new database:
   ```bash
   ALEMBIC_DB_PROFILE=newtenant python -m alembic upgrade head
   ```
3. Verify:
   ```bash
   python main.py health-check --db-profile newtenant
   ```
4. First-time data load:
   ```bash
   python main.py accounts-info --db-profile newtenant --to-bigquery
   python main.py accounts-registry --db-profile newtenant --to-bigquery
   python main.py full-refresh 2025-01-01 2026-04-30 --db-profile newtenant --to-bigquery
   ```

If `--db-profile newtenant` errors with "Unknown profile" you forgot step 1 — `REGISTERED_PROFILES` must include the name.

---

## 7. Recover from a corrupted upsert

```bash
# Discover backups:
python main.py list-backups --db-profile <profile>

# Restore the most recent (DESTRUCTIVE — overwrites public schema tables):
python main.py restore-backup --db-profile <profile> --schema backup_YYYYMMDD_HHMMSS

# After restore, replay any insights chunks that ran since the backup:
python main.py insights-range <since-backup> <today> --db-profile <profile> --to-bigquery --force
```

If the database itself is gone (host failure / dropped DB):
1. Provision a new Postgres instance and update `DB_CONN_STRING_<PROFILE>`.
2. `ALEMBIC_DB_PROFILE=<profile> python -m alembic upgrade head`
3. Replay from BigQuery if needed; otherwise full-refresh from the Meta API.

---

## 8. BigQuery is out of sync

```bash
python main.py reset-bigquery --db-profile <profile>
```

This drops all BigQuery tables and rebuilds from PostgreSQL. Safe to run anytime — Postgres is the source of truth.

---

## 9. Containerized deployment

```bash
# Build:
docker compose build etl

# One-shot run:
docker compose run --rm etl run-daily --to-bigquery

# Long-running scheduler (alternative to Windows Task Scheduler / cron):
docker compose --profile scheduler up -d scheduler

# Tail scheduler logs:
docker compose logs -f scheduler
```

Logs are persisted to `./logs` on the host via the bind mount.

---

## 10. Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `Application request limit reached` | Meta rate limit | Reduce `--workers`, increase `--chunk-days` |
| `Unknown profile 'foo'` | `REGISTERED_PROFILES` doesn't include it, or no `*_FOO` env vars | Add to `.env` per §6 |
| BigQuery merge fails on schema mismatch | New column in PG, missing in BQ | `python main.py sync-to-bigquery <table> --mode truncate` or `reset-bigquery` |
| `0 rows deleted` from `delete-account-data` | `act_` prefix mismatch (rare since fix) | Verify CSV has `act_` prefix; check `delete=TRUE` |
| pre-commit `psycopg2 NaT` errors | `pandas.NaT` slipped past coercion | The loader normalizes these — file a bug if it recurs |

For more in-depth debugging see [DOCUMENTATION.md §24 Troubleshooting](DOCUMENTATION.md#24-troubleshooting).
