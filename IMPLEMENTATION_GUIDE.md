# Meta (Facebook) Marketing ETL - Implementation Guide

## Purpose
This project extracts marketing data from the Meta (Facebook) Graph API, stores raw JSON payloads, normalizes them into analytics-ready tables, and optionally exports CSV files. It is designed to be portable so you can deploy it on another machine or environment with minimal changes.

## What This ETL Covers
- Insights (daily or date range) at ad, adset, campaign, or account level
- Accounts, campaigns, adsets, ads (settings), creatives
- Optional ad previews per ad_id and format
- Raw append-only tables + cleaned dimension/fact tables
- Automatic Postgres schema creation and column extension
- Replay/clean pipelines that rebuild facts/dims from raw tables

## High-Level Architecture
1) Extract: Graph API requests with pagination and retry logic.
2) Raw Load: Store full JSON payloads in raw tables for replay.
3) Transform: Flatten JSON, expand list metrics, normalize types, dedupe.
4) Load: Upsert into dimension/fact tables or export to CSV.

## Requirements
- Python 3.12+
- Postgres 12+ (optional, but required for DB mode and for replay commands)
- Network access to `https://graph.facebook.com`
- A valid Meta Marketing API access token with required permissions

Python packages (from `requirements.txt`):
- python-dotenv
- requests
- pandas
- SQLAlchemy

Notes:
- You also need a Postgres driver for SQLAlchemy (e.g., `psycopg2-binary` or `psycopg`) installed in the environment.
- The code uses JSONB columns; no extra Postgres extensions are required.

## Repository Structure (Key Paths)
- `main.py`: CLI entry point
- `src/config/`: environment loading and config objects
- `src/clients/graph_client.py`: Graph API client with retries/pagination
- `src/etl/extract/`: Graph API extractors
- `src/etl/transform/`: flattening and normalization
- `src/etl/load/`: CSV/DB loaders + schema manager
- `src/schema/`: table schemas and unique keys
- `src/fields/`: field lists per endpoint

## Environment Configuration
The app loads `.env` from the repo root (or OS env vars if `.env` is missing).

### Required
- `META_ACCESS_TOKEN`: Graph API access token
- `META_AD_ACCOUNT_IDS`: comma-separated list of ad account ids (`act_...`)
- `DB_CONN_STRING` or `DB_CONN_STRING_DEFAULT`: Postgres connection string

### Optional
- `META_API_VERSION`: Graph API version (default in code is `v21.0`)
- `DB_CONN_STRING_<PROFILE>`: profile-specific DB connection string
- `META_AD_ACCOUNT_IDS_<PROFILE>`: profile-specific ad account list
- `DATA_DIR`: default data directory (currently not used by code paths, but available)

### Example `.env` Template (Use Placeholders)
```
META_ACCESS_TOKEN=REPLACE_WITH_LONG_LIVED_TOKEN
META_API_VERSION=v22.0

# Default accounts/DB
META_AD_ACCOUNT_IDS=act_123456789012345,act_987654321098765
DB_CONN_STRING=postgresql://user:password@host:5432/ads_db

# Optional profile overrides (selected via --db-profile PROFILE)
DB_CONN_STRING_AGENCY=postgresql://user:password@host:5432/agency_ads_db
META_AD_ACCOUNT_IDS_AGENCY=act_111111111111111,act_222222222222222

DATA_DIR=./data
```

### Profile Behavior
- `--db-profile PROFILE` in the CLI uses:
  - `DB_CONN_STRING_<PROFILE>` for Postgres
  - `META_AD_ACCOUNT_IDS_<PROFILE>` for ad accounts (if set)
- If the profile-specific account list is missing, it falls back to `META_AD_ACCOUNT_IDS`.

## Meta API Permissions
Your token must have access to the ad accounts and marketing endpoints used.
Common permissions for the Marketing API:
- `ads_read` and/or `ads_management`
- `read_insights`
- `business_management` (for multi-account access)
Preview endpoints can also require page/instagram permissions depending on creative type.

## Database Setup (Postgres)
The app auto-creates the database (if possible) and all tables/columns on first run.
You still need a Postgres user and a database with permission to create tables.

Example setup:
```
CREATE ROLE ads_etl_user WITH LOGIN PASSWORD 'strong_password';
CREATE DATABASE ads_db OWNER ads_etl_user;
GRANT ALL PRIVILEGES ON DATABASE ads_db TO ads_etl_user;
```

Connection string format:
```
postgresql://ads_etl_user:strong_password@hostname:5432/ads_db
```

## Data Model

### Raw Tables (Append-Only)
All raw tables store a JSONB payload and minimal identifiers.
- `meta_insights_raw`: account_id, level, date_start, date_stop, breakdowns, payload
- `meta_accounts_raw`: account_id, payload
- `meta_creatives_raw`: creative_id, account_id, payload
- `meta_campaigns_raw`: campaign_id, account_id, payload
- `meta_adsets_raw`: adset_id, account_id, campaign_id, payload
- `meta_ads_raw`: ad_id, account_id, adset_id, campaign_id, payload
- `meta_ads_previews_raw`: ad_id, account_id, payload

### Dimension Tables
- `dim_meta_accounts`: account metadata (billing-related fields)
- `dim_meta_campaigns`: campaign metadata
- `dim_meta_adsets`: adset metadata + targeting (JSONB)
- `dim_meta_ads_settings`: ad settings and creative id/name
- `dim_meta_creatives`: creative payload and metadata
- `dim_meta_ads`: ad preview URLs/HTML (optional)

### Fact Tables
Base tables:
- `fact_meta_delivery_ad`
- `fact_meta_delivery_adset`
- `fact_meta_delivery_campaign`
- `fact_meta_delivery_account`

Breakdown tables (examples):
- `fact_meta_delivery_ad__age`
- `fact_meta_delivery_ad__age_gender`
- `fact_meta_delivery_adset__country`
- `fact_meta_delivery_campaign__gender`

Table naming for breakdowns:
```
fact_meta_delivery_<level>__<breakdown1>_<breakdown2>...
```
Breakdowns are sorted alphabetically before naming.

### Unique Keys (Upsert Keys)
See `src/schema/unique_keys.py` for the canonical list. Examples:
- `fact_meta_delivery_ad`: `["ad_id", "date_start"]`
- `fact_meta_delivery_ad__age_gender`: `["ad_id", "date_start", "age", "gender"]`
- `dim_meta_creatives`: `["creative_id"]`
- `dim_meta_ads_settings`: `["ad_id"]`

## Pipelines and Data Flow

### Insights Daily
Command:
```
python main.py insights-daily [level] [--date-preset PRESET] [--breakdowns b1,b2] [--csv PATH] [--workers N]
```
Flow:
1) Fetch `/act_<id>/insights` for each account using `date_preset`.
2) Insert raw rows into `meta_insights_raw`.
3) Normalize with `normalize_insights` (flatten JSON, expand list metrics, fix duplicates).
4) Upsert into `fact_meta_delivery_<level>` or a breakdown table.

### Insights Range
Command:
```
python main.py insights-range <from> <to> [level] [chunk_days] [--breakdowns b1,b2] [--csv PATH] [--workers N]
```
Flow:
- Splits the date range into chunks (default 7 days).
- Retries once after a 60s sleep on a rate limit error.
- Adds a 1s delay between chunks.

### Insights Clean (Replay From Raw)
Command:
```
python main.py insights-clean [level] [--breakdowns b1,b2] [--from-date] [--to-date] [--limit N]
```
Flow:
- Reads `meta_insights_raw` using filters.
- If multiple breakdown sets exist and none are specified, the command fails and asks for `--breakdowns`.
- Normalizes and upserts into the appropriate fact table.

### Clean Dim (Replay From Raw)
Command:
```
python main.py clean-dim <entity> [--limit N]
```
Entities:
- `accounts`, `creatives`, `campaigns`, `adsets`, `ads`, `ad-previews`

Flow:
- Reads the raw table for the entity.
- Normalizes and upserts into the target dimension table.

### Dimension Fetchers
Commands:
```
python main.py accounts-info [csv_path]
python main.py campaigns-info [csv_path]
python main.py adsets-info [csv_path]
python main.py ads-info [csv_path]
python main.py creatives-info [csv_path]
```
Notes:
- These fetch data from `me/adaccounts` or `act_<id>/<endpoint>`.
- They write to raw tables and upsert into dims.

### Ad Previews
Command:
```
python main.py ad-previews [csv_path] [started_after]
```
Flow:
- Fetches ads (with creative metadata) from `/act_<id>/ads`.
- Optionally filters ads by `created_time >= started_after`.
- Calls `/ad_id/previews` per ad and per format (default formats in code).
- Upserts into `dim_meta_ads`.

## Transformation Details
- JSON flattening via `pandas.json_normalize`.
- List metrics (actions, results, video metrics, etc.) are expanded into columns.
- `results` is collapsed into `results_indicator` and `results_value` to avoid column explosion.
- Duplicate columns (e.g., `col`, `col.1`) are merged.
- ID columns are kept as TEXT to avoid bigint issues.
- Numeric-like columns are coerced and NaN is filled with 0; non-numeric columns preserve nulls.

## Schema Management
The schema manager (`src/etl/load/schema_manager.py`) does the following:
- Creates the target database if missing.
- Creates tables defined in `src/schema/tables.py`.
- Adds missing columns from schema or from incoming DataFrame columns.
- Ensures unique indexes for upserts.
- Normalizes column names and truncates to Postgres 63-char limit.
- Never drops columns.

## CSV Output
All pipelines accept a `--csv` path to write outputs.
- Directories are created automatically.
- Encoding: UTF-8 with BOM (`utf-8-sig`).
- CSV is optional and independent from DB loading.

## CLI Quick Reference
Global flags:
- `--db-profile PROFILE`: use DB_CONN_STRING_<PROFILE> and META_AD_ACCOUNT_IDS_<PROFILE>
- `--no-db`: skip DB writes (CSV still works; replay commands still need DB reads)

Examples:
```
python main.py insights-daily ad
python main.py insights-daily ad --breakdowns age,gender --workers 4
python main.py insights-range 2025-10-01 2025-10-10 ad 1 --csv data/insights_oct.csv
python main.py insights-clean ad --from-date 2025-10-01 --to-date 2025-10-10 --breakdowns age,gender
python main.py clean-dim creatives --limit 1000
python main.py ads-info data/ads_settings.csv
python main.py creatives-info data/creatives.csv
python main.py ad-previews data/ad_previews.csv 2025-11-20
python main.py db-truncate
```

## Scheduling (Examples)

### Windows Task Scheduler
Run daily insights at 6am:
```
python C:\path\to\facebook_etl_new\main.py insights-daily ad --workers 2
```

### Linux Cron
```
0 6 * * * /usr/bin/python3 /opt/facebook_etl_new/main.py insights-daily ad --workers 2 >> /var/log/etl.log 2>&1
```

## Extending the ETL

### Add New Fields
1) Update field lists in `src/fields/endpoints.py` or extractor modules.
2) Run a pipeline; schema manager will add new columns automatically.

### Add a New Endpoint/Table
1) Create a new extractor in `src/etl/extract/`.
2) Create a pipeline in `src/etl/pipelines/`.
3) Add table definition in `src/schema/tables.py`.
4) Add unique keys in `src/schema/unique_keys.py`.

### Add Custom Breakdown
Use `--breakdowns` in insights pipelines. The table name will be created dynamically.
Ensure the breakdown columns are part of the unique key if you add a custom schema.

## Troubleshooting
- "META_AD_ACCOUNT_IDS is empty": set `META_AD_ACCOUNT_IDS` or `META_AD_ACCOUNT_IDS_<PROFILE>`.
- "No DB connection string found": set `DB_CONN_STRING` or `DB_CONN_STRING_<PROFILE>`.
- "Missing unique key columns": verify the target table and `UNIQUE_KEYS` are aligned.
- "Normalized rows exceed raw rows": duplicates can appear when flattening list metrics; the loader drops duplicates on unique keys.
- "Rate limit": reduce `--workers`, use shorter ranges, or run `insights-range` in smaller chunks.

## Security Notes
- Treat `META_ACCESS_TOKEN` and DB credentials as secrets.
- Do not commit `.env` with real tokens or passwords to source control.
- Rotate tokens regularly and use least-privilege scopes.

## Schema Design Decisions
*Context for future developers on why the database looks this way.*

### 1. Star Schema with Raw Layer
We use a **Star Schema** (Fact/Dimensions) for the clean layer.
- **Why**: Best for analytical queries (OLAP) via tools like Tableau/PowerBI.
- **Raw Layer**: We keep `meta_*_raw` tables with full JSONB payloads. This allows **replayability**—if we find a bug in `normalize_insights`, we can re-run the pipeline from raw data without hitting the API (saving rate limits).

### 2. Split Ad Dimensions (`dim_meta_ads` vs `dim_meta_ads_settings`)
You will notice two tables for Ads:
- `dim_meta_ads_settings`: Contains status, names, dates, campaign_id, etc.
- `dim_meta_ads`: Contains **Preview HTML** and heavy creative text.
- **Why**: Performance. The preview HTML blobs are massive (KB/row). If they were on the main settings table, simple queries like "checking ad status" would suffer from "Wide Row" I/O penalties.
- **Tip**: If you need both, join them on `ad_id`, or create a SQL View.

### 3. JSONB for Metrics
We store breakdown metrics (e.g., `actions`, `results`) as `JSONB` rather than hundreds of columns (e.g., `actions_comment`, `actions_like`...).
- **Why**: Meta has hundreds of metric variations. Isoloating them in JSONB prevents "Column Explosion" and sparse tables. Use Postgres JSON operators (`->>`) to query specific niche metrics if needed.

### 4. Text IDs
All Meta IDs are stored as `TEXT`.
- **Why**: Meta IDs are large integers that can overflow standard 32-bit (and sometimes signed 64-bit) integers in some systems. Text is the safest portable format.
