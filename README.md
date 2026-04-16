# Facebook Delivery Insights ETL

Focused ETL pipeline for Meta Ads data with two supported flows:
- `accounts-info` for account metadata
- `accounts-registry` for a curated account include/exclude list
- `insights-daily` / `insights-range` for ad delivery insights
- `sync-to-bigquery` for exporting PostgreSQL tables into existing BigQuery tables

The project is intentionally trimmed to this scope to reduce maintenance overhead and keep runtime paths simple.

Step-by-step BigQuery setup and sync instructions are in [BIGQUERY_RUNBOOK.md](BIGQUERY_RUNBOOK.md).
Power BI modeling guidance is in [POWERBI_MODEL.md](POWERBI_MODEL.md).

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```
2. Create `.env` from the template:
```bash
cp .env.example .env
```
Then fill in your values. Minimum required:
```ini
META_ACCESS_TOKEN=your_access_token
META_API_VERSION=v25.0

DB_CONN_STRING=postgresql://user:pass@localhost:5432/dbname

# BigQuery (optional)
BQ_PROJECT_ID=your-gcp-project-id
BQ_DATASET=meta_ads
BQ_LOCATION=US

# Preferred keyless auth (works when key creation is disabled)
# 1) Authenticate locally: gcloud auth application-default login
# 2) Optional: impersonate a service account
BQ_IMPERSONATE_SERVICE_ACCOUNT=etl-loader@your-gcp-project-id.iam.gserviceaccount.com

# Legacy key-file auth (only if your org allows service account keys)
# BQ_CREDENTIALS_PATH=C:\\path\\to\\service-account.json
```

Optional profile-specific values:
```ini
DB_CONN_STRING_AGENCY=postgresql://user:pass@localhost:5432/agency_db
BQ_PROJECT_ID_AGENCY=your-gcp-project-id
BQ_DATASET_AGENCY=meta_ads_agency

DB_CONN_STRING_FREELANCE=postgresql://user:pass@localhost:5432/freelance_db
BQ_PROJECT_ID_FREELANCE=your-gcp-project-id
BQ_DATASET_FREELANCE=meta_ads_freelance
```

## CLI

Run all commands through `main.py`.

### Accounts
```bash
python main.py accounts-info
python main.py accounts-info data/accounts.csv --no-db
python main.py accounts-info --no-db --to-bigquery
python main.py accounts-registry
python main.py accounts-registry data/account_registry.csv --no-db
```

`accounts-registry` creates a curated CSV with:
- `account_id`
- `account_name`
- `account_status`
- `profile_name`
- `include_in_etl`
- `notes`

If you rerun it later, it refreshes the live account names/statuses while preserving your existing `profile_name`, `include_in_etl`, and `notes` values.
The ETL now reads included accounts from this registry first. `META_AD_ACCOUNT_IDS` remains only as a fallback if the registry file does not exist yet.
For strict separation, assign `profile_name` values like `agency` and `freelance`, then run ETL separately with `--db-profile`.

### Insights (daily preset)
```bash
python main.py insights-daily
python main.py insights-daily ad --date-preset last_7d --breakdowns age,gender
python main.py insights-daily --no-db --to-bigquery
```

### Insights (date range)
```bash
python main.py insights-range 2026-03-01 2026-03-05
python main.py insights-range 2026-03-01 2026-03-05 ad 3 --workers 4
python main.py insights-range 2026-03-01 2026-03-05 --no-db --to-bigquery
```

### PostgreSQL -> BigQuery sync
```bash
python main.py sync-to-bigquery dim_meta_accounts --mode truncate
python main.py sync-to-bigquery fact_meta_delivery_ad
python main.py sync-to-bigquery fact_meta_delivery_ad fact_meta_delivery_account
python main.py sync-to-bigquery all
```

Important sync behavior:
- sync exports data from PostgreSQL into BigQuery
- target BigQuery tables must already exist
- `all` syncs only the overlap between PostgreSQL tables and existing BigQuery tables
- `auto` mode uses merge for `fact_meta_delivery_ad` and `fact_meta_delivery_account`
- other tables default to truncate/load in `auto` mode

### Shared options
- `--db-profile PROFILE`: use registry rows with `profile_name=<PROFILE>`, plus `DB_CONN_STRING_<PROFILE>` and `BQ_*_<PROFILE>` when configured
- `--no-db`: skip database writes
- `--csv PATH`: export pipeline output to CSV
- `--to-bigquery`: load normalized output into BigQuery
- `--bq-write-disposition`: `WRITE_APPEND` (default), `WRITE_TRUNCATE`, `WRITE_EMPTY`
- `--bq-table`: override target BigQuery table name

### Sync options
- `sync-to-bigquery <table_name> [<table_name> ...]`: export PostgreSQL tables into existing BigQuery tables
- `sync-to-bigquery all`: export only tables that already exist in both PostgreSQL and BigQuery
- `--mode`: `auto` (default), `merge`, `truncate`, `append`
- `--chunk-size`: rows per PostgreSQL read chunk (default `50000`)
- `--bq-table`: optional target BigQuery table override for single-table syncs

### Profile-separated runs
```bash
python main.py insights-daily ad --date-preset last_7d --db-profile agency --to-bigquery
python main.py insights-daily ad --date-preset last_7d --db-profile freelance --to-bigquery
```

With `BQ_DATASET_AGENCY` and `BQ_DATASET_FREELANCE`, those runs land in separate BigQuery datasets automatically.

## Fast refresh

Use:
```bash
run_full_refresh.bat
```

This runs:
1. `accounts-info`
2. `insights-daily --date-preset last_7d`
3. `ads-info`
4. `insights-daily --date-preset today`
