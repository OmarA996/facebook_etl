# Facebook / Meta Ads ETL — Full Technical Documentation

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Directory Structure](#3-directory-structure)
4. [Setup & Installation](#4-setup--installation)
5. [Configuration (.env)](#5-configuration-env)
6. [Multi-Profile System](#6-multi-profile-system)
7. [Database Schema (PostgreSQL)](#7-database-schema-postgresql)
8. [BigQuery Schema](#8-bigquery-schema)
9. [Meta Graph API Integration](#9-meta-graph-api-integration)
10. [Field Rename System (CSV-Driven)](#10-field-rename-system-csv-driven)
11. [ETL Pipelines — Dimensions](#11-etl-pipelines--dimensions)
12. [ETL Pipelines — Insights (Facts)](#12-etl-pipelines--insights-facts)
13. [ETL Pipelines — Orchestration](#13-etl-pipelines--orchestration)
14. [Data Transformation](#14-data-transformation)
15. [PostgreSQL Loader](#15-postgresql-loader)
16. [BigQuery Loader](#16-bigquery-loader)
17. [CLI Reference](#17-cli-reference)
18. [Views](#18-views)
19. [Maintenance Operations](#19-maintenance-operations)
20. [Scheduler & Windows Task Scheduler](#20-scheduler--windows-task-scheduler)
21. [BigQuery Sync & Reset](#21-bigquery-sync--reset)
22. [Testing](#22-testing)
23. [Data Flow — End to End](#23-data-flow--end-to-end)
24. [Troubleshooting](#24-troubleshooting)

---

## 1. Project Overview

This is a **production-grade Meta (Facebook) Ads ETL system** built for agencies managing multiple client ad accounts. It extracts advertising data from the Meta Graph API v25.0, transforms it, and loads it into PostgreSQL and Google BigQuery for reporting in Power BI or Looker Studio.

### What it does

- Extracts **account metadata**, **campaign/adset/ad/creative dimensions**, and **daily delivery insights** from the Meta Graph API
- Loads data into a **star-schema PostgreSQL database** (dimension tables + fact tables)
- Synchronises that data to **Google BigQuery** for scalable analytics
- Exposes a **unified CLI** (`python main.py <command>`) for all operations
- Runs on a **Windows Task Scheduler** (two scheduled tasks: every 2 hours for insights, daily for dims)
- Supports **multiple accounts and profiles** — one environment can manage many clients with separate databases and BigQuery datasets

### Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| API | Meta Graph API v25.0 |
| OLTP Database | PostgreSQL (via SQLAlchemy + psycopg2) |
| OLAP / Analytics | Google BigQuery |
| HTTP | requests with retry/backoff |
| Data Wrangling | pandas, numpy |
| Logging | structlog |
| Config | python-dotenv, environment variables |
| Scheduler | Windows Task Scheduler (PowerShell scripts) |
| Testing | pytest |

---

## 2. Architecture

```
Meta Graph API
      │
      │  HTTP (requests + retry)
      ▼
┌─────────────────────────────────────────────────────────────┐
│                    EXTRACT LAYER                            │
│  accounts · campaigns · adsets · ads · creatives · insights │
└─────────────────────────┬───────────────────────────────────┘
                          │  raw JSON records (List[Dict])
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  TRANSFORM LAYER                            │
│  flatten_json · expand actions · rename columns · coerce    │
│  types · deduplicate · apply CSV rename map                 │
└─────────────────────────┬───────────────────────────────────┘
                          │  pandas DataFrame
                          ▼
          ┌───────────────┴────────────────┐
          │                                │
          ▼                                ▼
┌─────────────────┐              ┌──────────────────┐
│   PostgreSQL    │              │   BigQuery       │
│                 │              │                  │
│  dim_meta_*     │─── sync ────▶│  dim_meta_*      │
│  fact_meta_*    │              │  fact_meta_*     │
│  vw_meta_ads_   │              │  vw_meta_ads_    │
│    full (view)  │              │    full (view)   │
│  fact_meta_ads_ │              │  fact_meta_ads_  │
│    combined     │              │    combined      │
└─────────────────┘              └──────────────────┘
          │
          ▼
    Power BI / Looker Studio
```

### Execution Flow

Every 2 hours → **MetaETL_AccountsInsights** task:
1. Fetch account billing metadata → upsert `dim_meta_accounts`
2. Fetch last 7 days of ad-level insights → upsert `fact_meta_delivery_ad`
3. Sync both to BigQuery

Daily at 10:00 AM → **MetaETL_DimsRefresh** task:
1. Fetch all campaigns → upsert `dim_meta_campaigns`
2. Fetch all adsets → upsert `dim_meta_adsets`
3. Fetch all ads → upsert `dim_meta_ads`
4. Fetch all creatives → upsert `dim_meta_creatives`
5. Sync all to BigQuery

---

## 3. Directory Structure

```
facebook_etl_new_big/
├── main.py                          # CLI entry point (argparse)
├── scheduler.py                     # Background Python scheduler (alternative to Task Scheduler)
├── .env                             # Credentials and config (not committed)
│
├── data/
│   ├── api_field_rename_template.csv    # Master field mapping (source of truth)
│   ├── account_registry.csv             # User-maintained account registry
│   ├── delete_accounts_template.csv     # Bulk account deletion list
│   └── database_fields_edit_template.csv
│
├── scripts/
│   ├── setup_task.ps1               # Register Windows Task Scheduler tasks (run as Admin once)
│   ├── accounts_insights_sync.ps1   # 2-hour job script
│   ├── dims_sync.ps1                # Daily dims job script
│   └── daily_sync.ps1               # Full daily orchestration script
│
├── logs/                            # Auto-created; contains dated log files
│
├── src/
│   ├── config/
│   │   └── settings.py              # Pydantic config + multi-profile resolution
│   │
│   ├── clients/
│   │   └── graph_client.py          # Meta Graph API HTTP client (retry, pagination)
│   │
│   ├── fields/
│   │   ├── endpoints.py             # API field lists per endpoint/level
│   │   └── rename_maps.py           # CSV rename map loader and writer
│   │
│   ├── schema/
│   │   ├── tables.py                # PostgreSQL table schemas (TABLE_SCHEMAS dict)
│   │   ├── unique_keys.py           # Upsert/ON CONFLICT keys per table
│   │   ├── views.py                 # vw_meta_ads_full view builder (PG + BQ)
│   │   └── bigquery.py              # Postgres → BigQuery type mapping
│   │
│   ├── etl/
│   │   ├── extract/
│   │   │   ├── accounts.py          # me/adaccounts
│   │   │   ├── campaigns.py         # {account}/campaigns
│   │   │   ├── adsets.py            # {account}/adsets
│   │   │   ├── ads_settings.py      # {account}/ads (dimensions)
│   │   │   ├── creatives.py         # {account}/adcreatives
│   │   │   └── meta_insights.py     # {account}/insights
│   │   │
│   │   ├── transform/
│   │   │   ├── core.py              # Flatten, rename, coerce, expand actions
│   │   │   └── meta_insights.py     # Insights-specific: results split, dedup
│   │   │
│   │   ├── load/
│   │   │   ├── postgres_loader.py   # UPSERT to PostgreSQL
│   │   │   ├── bigquery_loader.py   # Load to BigQuery (merge/truncate/append)
│   │   │   ├── schema_manager.py    # CREATE TABLE / ADD COLUMN migrations
│   │   │   └── csv_loader.py        # Export to CSV
│   │   │
│   │   └── pipelines/
│   │       ├── accounts_info.py         # dim_meta_accounts pipeline
│   │       ├── accounts_registry.py     # dim_meta_account_registry pipeline
│   │       ├── campaigns_info.py        # dim_meta_campaigns pipeline
│   │       ├── adsets_info.py           # dim_meta_adsets pipeline
│   │       ├── ads_info.py              # dim_meta_ads pipeline
│   │       ├── creatives_info.py        # dim_meta_creatives pipeline
│   │       ├── meta_insights.py         # Core insights pipeline (daily + range)
│   │       ├── meta_insights_daily.py   # Daily wrapper
│   │       ├── meta_insights_range.py   # Historical range wrapper
│   │       ├── run_pipeline.py          # Orchestration (run_daily, run_full_refresh, etc.)
│   │       ├── sync_to_bigquery.py      # Postgres → BigQuery sync
│   │       ├── materialize_combined.py  # Build fact_meta_ads_combined
│   │       ├── backup_restore.py        # DB schema backup/restore
│   │       ├── prune_columns.py         # Drop excluded columns
│   │       ├── rename_columns.py        # Rename columns per CSV
│   │       ├── delete_account_data.py   # Delete rows for specific accounts
│   │       ├── clean_db.py              # Drop non-ETL tables
│   │       └── reset_bigquery.py        # Nuke and rebuild BigQuery
│   │
│   ├── cli/
│   │   └── handlers.py              # One handler function per CLI command
│   │
│   └── utils/
│       ├── logger.py                # structlog setup
│       ├── names.py                 # Column name normalization (63-char PG limit)
│       └── logging_utils.py        # Additional logging helpers
│
└── tests/
    ├── test_config.py
    ├── test_names.py
    ├── test_transform_core.py
    ├── test_bigquery_loader.py
    ├── test_sync_to_bigquery.py
    ├── test_meta_insights_bigquery.py
    ├── test_accounts_registry.py
    └── test_ads_info.py
```

---

## 4. Setup & Installation

### Prerequisites

- Python 3.10+
- PostgreSQL 14+
- Google Cloud project with BigQuery API enabled (if using BigQuery)
- Meta Business Manager access with a long-lived access token

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd facebook_etl_new_big

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Copy and fill in the environment file
copy .env.example .env
# Edit .env with your credentials
```

### First Run

```bash
# Verify connections
python main.py health-check

# Initialize the database (creates all tables)
python main.py accounts-info

# Fetch historical data (adjust dates)
python main.py insights-range --from-date 2025-01-01 --to-date 2025-04-30 --to-db

# Set up Windows Task Scheduler (run PowerShell as Administrator)
cd scripts
.\setup_task.ps1
```

---

## 5. Configuration (.env)

All configuration is loaded from a `.env` file in the project root via `python-dotenv`.

### Required Variables

| Variable | Description | Example |
|---|---|---|
| `META_ACCESS_TOKEN` | Long-lived Meta Graph API token | `EAAGm...` |
| `META_API_VERSION` | Graph API version | `v25.0` |
| `META_AD_ACCOUNT_IDS` | Default account list (comma-separated) | `act_123,act_456` |
| `DB_CONN_STRING` | Default PostgreSQL connection string | `postgresql://user:pass@localhost:5432/ads_db` |

### Optional — BigQuery

| Variable | Description |
|---|---|
| `BQ_PROJECT_ID` | GCP project ID |
| `BQ_DATASET` | BigQuery dataset name |
| `BQ_LOCATION` | Dataset location (e.g., `US`, `EU`, `europe-west1`) |
| `BQ_CREDENTIALS_PATH` | Path to service account JSON key file |
| `BQ_IMPERSONATE_SERVICE_ACCOUNT` | Service account email to impersonate |

### Optional — Multi-Profile

Append `_<PROFILE>` to any variable to create a named profile (see Section 6).

```env
META_AD_ACCOUNT_IDS_AGENCY=act_aaa,act_bbb
DB_CONN_STRING_AGENCY=postgresql://user:pass@host:5432/agency_db
BQ_PROJECT_ID_AGENCY=gcp-agency-project
BQ_DATASET_AGENCY=meta_agency
```

---

## 6. Multi-Profile System

The project supports running multiple clients with completely separate databases and BigQuery datasets from a single installation.

### How It Works

Profile names are discovered dynamically by scanning environment variables for the suffix pattern `_<PROFILE>`. Any variable matching `META_AD_ACCOUNT_IDS_*`, `DB_CONN_STRING_*`, or `BQ_PROJECT_ID_*` registers a profile.

### Using a Profile

All CLI commands accept `--db-profile <NAME>`:

```bash
# Pull insights for the "agency" profile's accounts into the agency database
python main.py insights-daily --db-profile AGENCY --to-bigquery

# Refresh dims for the "freelance" profile
python main.py dims-refresh --db-profile FREELANCE --to-bigquery
```

### Fallback Behaviour

If a profile variable is not found, the system falls back to the default (unprefixed) variable. This means you can run without `--db-profile` and it uses the primary `.env` settings.

### Account Registry per Profile

`data/account_registry.csv` maps accounts to profiles:

```csv
account_id,account_name,account_status,profile_name,include_in_etl,notes
act_123,Client A,1,AGENCY,TRUE,
act_456,Client B,1,FREELANCE,TRUE,
```

When running with `--db-profile AGENCY`, only accounts with `profile_name=AGENCY` and `include_in_etl=TRUE` are processed.

---

## 7. Database Schema (PostgreSQL)

The schema follows a **star schema** design: dimension tables holding descriptive attributes, and fact tables holding time-series metrics.

### Dimension Tables

#### `dim_meta_accounts`
Stores billing and metadata for each ad account. Populated by `accounts-info`.

| Column | Type | Description |
|---|---|---|
| `id` | TEXT (PK) | Account ID with `act_` prefix (e.g., `act_123456`) |
| `account_name` | TEXT | Display name |
| `account_status` | INTEGER | 1=Active, 2=Disabled, 3=Unsettled, 7=Pending Risk Review, etc. |
| `currency` | TEXT | Account currency (e.g., `EGP`, `USD`) |
| `timezone_id` | INTEGER | Meta timezone identifier |
| `amount_spent` | NUMERIC | Total lifetime spend |
| `spend_cap` | NUMERIC | Optional account spend cap |
| `balance` | NUMERIC | Current balance |
| `business_name` | TEXT | Business Manager name |
| `disable_reason` | INTEGER | Reason code if account disabled |
| `funding_source_display` | TEXT | Human-readable payment method |
| `funding_source_id` | TEXT | Payment method ID |
| `funding_source_type` | TEXT | Payment method type |
| `created_time` | TIMESTAMPTZ | Account creation timestamp |

> **Note:** `dim_meta_accounts.id` stores the `act_` prefix form. Fact tables store account_id **without** the `act_` prefix. The view handles this with `REPLACE(acc.id, 'act_', '')`.

---

#### `dim_meta_account_registry`
User-maintained registry of all known accounts. Populated via `accounts-registry` or manually.

| Column | Type | Description |
|---|---|---|
| `account_id` | TEXT (PK) | Account ID |
| `account_name` | TEXT | Display name |
| `account_status` | INTEGER | Status code |
| `profile_name` | TEXT | Profile assignment for multi-tenant use |
| `include_in_etl` | BOOLEAN | Whether to include in scheduled ETL runs |
| `notes` | TEXT | Free-text notes |

---

#### `dim_meta_campaigns`
Campaign-level metadata. Populated by `campaigns-info`.

| Column | Type | Description |
|---|---|---|
| `campaign_id` | TEXT (PK) | Campaign ID |
| `account_id` | TEXT | Parent account ID |
| `campaign_name` | TEXT | Campaign display name |

---

#### `dim_meta_adsets`
Ad set metadata. Populated by `adsets-info`.

| Column | Type | Description |
|---|---|---|
| `adset_id` | TEXT (PK) | Ad set ID |
| `account_id` | TEXT | Parent account ID |
| `campaign_id` | TEXT | Parent campaign ID |
| `adset_name` | TEXT | Ad set display name |

---

#### `dim_meta_ads`
Ad-level metadata. Populated by `ads-info`.

| Column | Type | Description |
|---|---|---|
| `ad_id` | TEXT (PK) | Ad ID |
| `account_id` | TEXT | Parent account ID |
| `adset_id` | TEXT | Parent ad set ID |
| `campaign_id` | TEXT | Parent campaign ID |
| `ad_name` | TEXT | Ad display name |
| `creative_id` | TEXT | Associated creative ID |
| `creative_name` | TEXT | Creative display name |
| `status` | TEXT | Current status |
| `effective_status` | TEXT | Effective status (considering parent) |
| `configured_status` | TEXT | User-set status |
| `created_time` | TIMESTAMPTZ | Ad creation timestamp |
| `updated_time` | TIMESTAMPTZ | Last update timestamp |
| `ad_review_feedback_*` | TEXT | Review feedback fields |

---

#### `dim_meta_creatives`
Ad creative metadata. Populated by `creatives-info`.

| Column | Type | Description |
|---|---|---|
| `creative_id` | TEXT (PK) | Creative ID |
| `account_id` | TEXT | Parent account ID |
| `creative_name` | TEXT | Creative display name |
| `title` | TEXT | Ad title |
| `body` | TEXT | Ad body text |
| `description` | TEXT | Ad description |
| `call_to_action_type` | TEXT | CTA type (SHOP_NOW, LEARN_MORE, etc.) |
| `image_url` | TEXT | Image URL |
| `thumbnail_url` | TEXT | Thumbnail URL |
| `image_hash` | TEXT | Image hash |
| `video_id` | TEXT | Video asset ID |
| `object_url` | TEXT | Destination URL |
| `link_url` | TEXT | Link URL |
| `display_url` | TEXT | Display URL |
| `effective_object_story_id` | TEXT | Associated post ID |
| `status` | TEXT | Creative status |

---

### Fact Tables

#### `fact_meta_delivery_ad`
Daily ad-level delivery metrics. Populated by `insights-daily` or `insights-range`.

| Column | Type | Description |
|---|---|---|
| `ad_id` | TEXT | Ad ID (part of composite PK) |
| `date_start` | DATE | Reporting date (part of composite PK) |
| `date_stop` | DATE | Reporting date end (usually same as date_start) |
| `account_id` | TEXT | Account ID (without `act_` prefix) |
| `account_name` | TEXT | Account display name |
| `campaign_id` | TEXT | Campaign ID |
| `campaign_name` | TEXT | Campaign name |
| `adset_id` | TEXT | Ad set ID |
| `adset_name` | TEXT | Ad set name |
| `ad_name` | TEXT | Ad name |
| `objective` | TEXT | Campaign objective |
| `optimization_goal` | TEXT | Ad set optimization goal |
| `spend` | NUMERIC | Amount spent (in account currency) |
| `social_spend` | NUMERIC | Social spend |
| `reach` | NUMERIC | Unique reach |
| `impressions` | NUMERIC | Total impressions |
| `clicks` | NUMERIC | Total link clicks |
| `unique_clicks` | NUMERIC | Unique link clicks |
| `unique_inline_link_clicks` | NUMERIC | Unique inline link clicks |
| `results` | JSONB | Raw results array from API |
| `results_indicator` | TEXT | Comma-separated result types (e.g., `purchase,lead`) |
| `results_value` | TEXT | Comma-separated result values |
| `unique_outbound_clicks` | JSONB | Outbound click breakdown |
| `outbound_clicks` | JSONB | Total outbound clicks |
| `actions` | JSONB | Raw actions array |
| `action_values` | JSONB | Raw action values array |
| `video_avg_time_watched_actions` | JSONB | Average video watch time |
| `video_p25_watched_actions` | JSONB | 25% completion |
| `video_p50_watched_actions` | JSONB | 50% completion |
| `video_p75_watched_actions` | JSONB | 75% completion |
| `video_p95_watched_actions` | JSONB | 95% completion |
| `video_p100_watched_actions` | JSONB | 100% completion |
| `video_play_actions` | JSONB | Play events |
| `video_30_sec_watched_actions` | JSONB | 30-second completions |

**Dynamic columns:** When actions are expanded (e.g., `actions_link_click`, `actions_purchase`), columns are added automatically.

**Upsert key:** `(ad_id, date_start)` — re-running the same date replaces data.

---

#### Breakdown Fact Tables

The same schema as `fact_meta_delivery_ad` but partitioned by a demographic breakdown dimension. Created dynamically when you run insights with `--breakdowns`.

| Table | Extra Column | Upsert Key |
|---|---|---|
| `fact_meta_delivery_ad__age` | `age` | `(ad_id, date_start, age)` |
| `fact_meta_delivery_ad__gender` | `gender` | `(ad_id, date_start, gender)` |
| `fact_meta_delivery_ad__age_gender` | `age`, `gender` | `(ad_id, date_start, age, gender)` |
| `fact_meta_delivery_ad__country` | `country` | `(ad_id, date_start, country)` |
| `fact_meta_delivery_ad__attribution_setting` | `attribution_setting` | `(ad_id, date_start, attribution_setting)` |
| `fact_meta_delivery_adset` | — | `(adset_id, date_start)` |
| `fact_meta_delivery_adset__age` | `age` | `(adset_id, date_start, age)` |
| `fact_meta_delivery_adset__gender` | `gender` | `(adset_id, date_start, gender)` |
| `fact_meta_delivery_adset__age_gender` | `age`, `gender` | `(adset_id, date_start, age, gender)` |
| `fact_meta_delivery_adset__country` | `country` | `(adset_id, date_start, country)` |
| `fact_meta_delivery_adset__attribution_setting` | `attribution_setting` | `(adset_id, date_start, attribution_setting)` |
| `fact_meta_delivery_campaign` | — | `(campaign_id, date_start)` |
| `fact_meta_delivery_campaign__age` | `age` | `(campaign_id, date_start, age)` |
| `fact_meta_delivery_campaign__gender` | `gender` | `(campaign_id, date_start, gender)` |
| `fact_meta_delivery_campaign__age_gender` | `age`, `gender` | `(campaign_id, date_start, age, gender)` |
| `fact_meta_delivery_campaign__country` | `country` | `(campaign_id, date_start, country)` |
| `fact_meta_delivery_campaign__attribution_setting` | `attribution_setting` | `(campaign_id, date_start, attribution_setting)` |

---

### Materialized Table

#### `fact_meta_ads_combined`
A materialized snapshot of `vw_meta_ads_full`. Rebuilt on demand via `materialize-combined`. Used as the primary Power BI source table because it includes all joined dim attributes without runtime join cost.

---

### Raw Table

#### `meta_insights_raw`
An optional raw dump of API responses before transformation. Not always populated; used for debugging.

---

## 8. BigQuery Schema

BigQuery mirrors the PostgreSQL schema with type translations:

| PostgreSQL Type | BigQuery Type |
|---|---|
| TEXT | STRING |
| INTEGER | INT64 |
| NUMERIC | NUMERIC |
| DATE | DATE |
| TIMESTAMPTZ | TIMESTAMP |
| BOOLEAN | BOOL |
| JSONB | STRING (JSON-encoded) |

Dynamic columns like `actions_link_click`, `video_30_sec_watched_actions` are inferred as `FLOAT64` in BigQuery.

### Sync Strategy per Table

| Table | Sync Mode | Partition | Cluster |
|---|---|---|---|
| `fact_meta_delivery_ad` | MERGE on `(ad_id, date_start)` | `date_start` | `account_id, campaign_id, adset_id, ad_id` |
| `fact_meta_ads_combined` | TRUNCATE + reload | — | — |
| `dim_meta_*` | WRITE_APPEND or MERGE | — | — |

---

## 9. Meta Graph API Integration

### Client (`src/clients/graph_client.py`)

The `GraphAPIClient` class handles all HTTP communication with the Meta Graph API.

**Features:**
- **Automatic pagination** — Follows `paging.next` cursors transparently; all paginated results are collected into a single list.
- **Retry with exponential backoff** — Up to 5 retries; waits `2^attempt × base_backoff` seconds between attempts.
- **Rate limit handling** — Detects HTTP 429 and respects the `Retry-After` header.
- **Server error handling** — Retries on 500, 502, 503, 504.
- **Token injection safety** — The access token is injected into every request but never duplicated on already-tokenised pagination URLs.

### API Endpoints Used

| Endpoint | Purpose | Pipeline |
|---|---|---|
| `me/adaccounts` | List accessible ad accounts | `accounts-info` |
| `{account_id}/campaigns` | Fetch campaigns | `campaigns-info` |
| `{account_id}/adsets` | Fetch ad sets | `adsets-info` |
| `{account_id}/ads` | Fetch ads | `ads-info` |
| `{account_id}/adcreatives` | Fetch creatives | `creatives-info` |
| `{account_id}/insights` | Fetch delivery metrics | `insights-daily`, `insights-range` |

### Insights API Parameters

| Parameter | Value | Notes |
|---|---|---|
| `level` | `ad`, `adset`, `campaign`, `account` | Controls aggregation level |
| `time_increment` | `1` | Always daily |
| `limit` | `50` | Records per page |
| `date_preset` | `yesterday`, `last_7d`, etc. | Mutually exclusive with `since`/`until` |
| `since` / `until` | `YYYY-MM-DD` | Explicit date range |
| `breakdowns` | `age`, `gender`, `country`, `attribution_setting` | Optional demographic splits |

### Parallel Account Fetching

All extractors support `max_workers` (default 1). When `max_workers > 1`, accounts are processed in parallel using `ThreadPoolExecutor`. This significantly speeds up runs with many accounts.

```bash
python main.py insights-daily --workers 4
```

---

## 10. Field Rename System (CSV-Driven)

The rename system is the **source of truth** for which API fields become which database columns. It is designed so non-developers can manage the field mapping without touching code.

### File: `data/api_field_rename_template.csv`

| Column | Description |
|---|---|
| `group_name` | Visual grouping (e.g., `01_accounts`, `03_insights`) |
| `endpoint_or_pipeline` | Pipeline key (e.g., `accounts-info`, `insights-daily ad`) |
| `api_field` | Raw JSON field name from Meta API (supports dot notation for nested paths: `funding_source_details.id`) |
| `current_database_table` | Destination PostgreSQL table |
| `current_database_column` | Default column name (used if `rename_to` is empty) |
| `rename_to` | Override column name (takes precedence over `current_database_column`) |
| `status` | `approved` · `pending` · `excluded` |
| `notes` | Free-text description |

### Status Values

- **`approved`** — Field is active. It is fetched from the API, renamed per `rename_to`, and loaded into the database.
- **`pending`** — New field detected in the API response that has not been reviewed yet. It is logged but **not loaded**.
- **`excluded`** — Field is intentionally ignored. It is silently dropped from all DataFrames. Run `prune-columns` to also drop the database column.

### Auto-Detection of New Fields

When the pipeline encounters an API field not in the CSV, it automatically appends it as `pending`. The workflow is:

1. Run the pipeline — new fields appear in logs: `"New API fields detected"`
2. Open `data/api_field_rename_template.csv`
3. For each new row:
   - Set `rename_to` to your preferred column name
   - Change `status` to `approved` (to load) or `excluded` (to ignore)
4. Re-run the pipeline — new fields are now loaded

### Pipeline Keys

| Pipeline Key | Target Table |
|---|---|
| `accounts-info` | `dim_meta_accounts` |
| `campaigns-info` | `dim_meta_campaigns` |
| `adsets-info` | `dim_meta_adsets` |
| `ads-info` | `dim_meta_ads` |
| `creatives-info` | `dim_meta_creatives` |
| `insights-daily ad` | `fact_meta_delivery_ad` |
| `insights-daily adset` | `fact_meta_delivery_adset` |
| `insights-daily campaign` | `fact_meta_delivery_campaign` |

---

## 11. ETL Pipelines — Dimensions

Each dimension pipeline follows the same pattern:
1. Extract from Meta API (in parallel if `--workers N`)
2. Flatten nested JSON
3. Apply rename map from CSV
4. Fill/coerce types
5. Upsert to PostgreSQL
6. Optionally sync to BigQuery

### `accounts-info`

Fetches billing and account-level metadata. Updates `dim_meta_accounts`.

```bash
python main.py accounts-info [--to-bigquery] [--db-profile PROFILE] [--workers N]
```

Key fields: account status, currency, timezone, spend, balance, funding source.

### `campaigns-info`

Fetches all campaigns for each account. Updates `dim_meta_campaigns`.

```bash
python main.py campaigns-info [--status ACTIVE,PAUSED] [--to-bigquery] [--workers N]
```

The `--status` argument filters by Meta campaign effective status.

### `adsets-info`

Fetches all ad sets. Updates `dim_meta_adsets`.

```bash
python main.py adsets-info [--status ACTIVE,PAUSED] [--to-bigquery] [--workers N]
```

### `ads-info`

Fetches all ads with creative references. Updates `dim_meta_ads`.

```bash
python main.py ads-info [--status ACTIVE,PAUSED] [--to-bigquery] [--workers N]
```

### `creatives-info`

Fetches ad creatives. Updates `dim_meta_creatives`.

```bash
python main.py creatives-info [--to-bigquery] [--workers N]
```

### `accounts-registry`

Loads account registry from a CSV file instead of querying the Meta API. Useful for manually managing which accounts are included in ETL.

```bash
python main.py accounts-registry [--csv data/account_registry.csv] [--to-bigquery]
```

### `dims-refresh` (Orchestrated)

Runs all dimension pipelines in sequence: campaigns → adsets → ads → creatives → optional BigQuery sync.

```bash
python main.py dims-refresh [--to-bigquery] [--workers N] [--db-profile PROFILE]
```

---

## 12. ETL Pipelines — Insights (Facts)

### `insights-daily`

Fetches delivery metrics for a single date (default: yesterday).

```bash
# Yesterday's data at ad level (default)
python main.py insights-daily

# Last 7 days at ad level, sync to BigQuery
python main.py insights-daily --date-preset last_7d --to-bigquery

# Ad-level with age/gender breakdown
python main.py insights-daily --breakdowns age,gender

# Campaign level
python main.py insights-daily --level campaign --to-bigquery

# Export to CSV only (no DB write)
python main.py insights-daily --csv output/insights.csv --no-db
```

**Date presets:** `yesterday`, `last_7d`, `last_30d`, `last_90d`, `last_quarter`, `last_year`

**Levels:** `ad` (default), `adset`, `campaign`, `account`

**Breakdowns:** `age`, `gender`, `country`, `attribution_setting` (can combine multiple)

---

### `insights-range`

Fetches historical data over an explicit date range. Data is processed in weekly chunks to respect API limits.

```bash
# Full year of data
python main.py insights-range --from-date 2025-01-01 --to-date 2025-12-31 --to-bigquery

# Historical adset-level with country breakdown
python main.py insights-range \
  --from-date 2025-01-01 --to-date 2025-06-30 \
  --level adset --breakdowns country \
  --to-bigquery

# Use smaller chunks if hitting API limits
python main.py insights-range --from-date 2025-01-01 --to-date 2025-12-31 --chunk-days 3
```

**Rate limit handling:** If an API rate limit error is hit mid-chunk, the pipeline waits 60 seconds and retries once before logging the error and moving on to the next chunk.

---

### How Insights Data is Loaded

1. API returns a list of JSON records (one per ad/adset/campaign per day)
2. `normalize_insights()` transforms the records:
   - Splits `results` list into `results_indicator` and `results_value` (comma-separated strings)
   - Flattens nested fields using `pd.json_normalize`
   - Expands `actions` and `action_values` arrays into `actions_<type>` columns
   - Collapses duplicate columns (pandas auto-numbering artefact)
   - Applies rename map from CSV
3. DataFrame is upserted to PostgreSQL using `ON CONFLICT (ad_id, date_start) DO UPDATE`
4. Optionally synced to BigQuery via MERGE on the same composite key

---

## 13. ETL Pipelines — Orchestration

### `accounts-insights` (2-hour scheduled job)

Quick refresh combining accounts metadata and insights.

```bash
python main.py accounts-insights [--days-back 7] [--to-bigquery] [--workers N]
```

Steps:
1. `accounts-info` → update `dim_meta_accounts`
2. `insights-daily --date-preset last_7d` → update `fact_meta_delivery_ad`
3. BigQuery sync (if `--to-bigquery`)

---

### `dims-refresh` (daily scheduled job)

Refreshes all dimension tables.

```bash
python main.py dims-refresh [--to-bigquery] [--workers N]
```

Steps:
1. `campaigns-info`
2. `adsets-info`
3. `ads-info`
4. `creatives-info`
5. BigQuery sync (if `--to-bigquery`)

---

### `run-daily` (full orchestrated daily)

Combines dims refresh + rolling insights in one command.

```bash
python main.py run-daily [--days-back 7] [--level ad] [--to-bigquery]
```

Steps:
1. All dim pipelines (unless `--skip-dims`)
2. Rolling N-day insights
3. BigQuery sync
4. Prints step-by-step timing summary

---

### `full-refresh` (historical backfill)

Dims + full date range for insights.

```bash
python main.py full-refresh \
  --from-date 2024-01-01 --to-date 2024-12-31 \
  --level ad --to-bigquery
```

---

## 14. Data Transformation

### Core Transform (`src/etl/transform/core.py`)

#### `flatten_json(records, expand_lists=True)`

Converts a list of API response dicts to a flat pandas DataFrame:
1. `pd.json_normalize()` flattens one level of nesting
2. Detects columns containing arrays of `{"action_type": ..., "value": ...}` objects and expands them
3. Renames expanded columns with a prefix (e.g., `actions_link_click`, `action_values_purchase`)
4. Drops the original list column to avoid column explosion
5. Casts numeric columns (skips ID columns like `ad_id`, `account_id`)

#### `apply_rename_map(df, pipeline, table_name)`

Applies the CSV rename map to a DataFrame:
1. Drops columns marked `excluded` in the CSV
2. Renames approved columns from API name to DB column name
3. Logs any new (pending) fields encountered
4. Registers truly new fields (not in CSV at all) back to `api_field_rename_template.csv`

#### `fill_numeric_keep_nulls(df)`

Safely coerces string-numeric columns to float64 without converting NULL values:
- Preserves `None` and `NaN` as NULL (important for psycopg2 parameter binding)
- Only coerces columns where all non-null values are parseable as numbers

---

### Insights Transform (`src/etl/transform/meta_insights.py`)

#### `normalize_insights(records, level, breakdowns)`

Full pipeline for raw API response → clean DataFrame:

1. **`_split_results_columns(records)`** — In-place modification of raw dicts. Converts the `results` list (`[{"indicator": "purchase", "values": [{"value": "5"}]}, ...]`) into two simple string columns:
   - `results_indicator` = `"purchase,lead"`
   - `results_value` = `"5,12"`
   The original `results` key is removed to avoid column explosion.

2. **`flatten_json(records)`** — Core flattening (see above)

3. **`_collapse_numbered_duplicates(df)`** — Fixes pandas' behaviour when two API fields normalise to the same column name (e.g., `col`, `col.1`, `col.2`). Collapses them by taking the first non-null value across duplicates.

4. **Replace inf/-inf** — Converts numpy infinity values to None (cannot be stored in Postgres or BigQuery)

5. **Ensure key columns** — Guarantees `ad_id`/`adset_id`/`campaign_id`, `date_start`, `date_stop`, and all breakdown columns exist (adds NULL column if missing)

6. **`apply_rename_map()`** — Applies CSV mapping for the relevant level

#### `get_insights_table_name(level, breakdowns)`

Determines the destination table name:
- `ad` + no breakdowns → `fact_meta_delivery_ad`
- `ad` + `["age", "gender"]` → `fact_meta_delivery_ad__age_gender`
- `campaign` + `["country"]` → `fact_meta_delivery_campaign__country`

---

## 15. PostgreSQL Loader

### `save_df_to_postgres_upsert(df, table_name, unique_cols, conn_string)`

The main loading function. Handles all edge cases for safely inserting/updating rows.

**Process:**
1. Normalize column names to 63-character PostgreSQL limit
2. Convert pandas `NaT` → `None` (psycopg2 cannot bind `NaT`)
3. Convert `float('nan')` → `None` (psycopg2 cannot bind `NaN`)
4. Deduplicate rows on `unique_cols` (keeps last occurrence — handles duplicate API responses)
5. Collapse columns with the same normalised name
6. Chunk into batches of max 20,000 parameters (Postgres parameter limit is 65,535)
7. Execute `INSERT ... ON CONFLICT (unique_cols) DO UPDATE SET ...`

**Schema migration:** Before the first insert to a new table, calls `ensure_database_and_tables()` which creates the table if it doesn't exist and adds any missing columns (never drops existing ones).

**Key Detail — Account ID Format:**
Fact tables receive `account_id` values **without** the `act_` prefix (as returned by the insights API). Dimension tables receive `account_id` values **with** the `act_` prefix (as returned by the ads API). This is reconciled in the view via `REPLACE(acc.id, 'act_', '')`.

---

## 16. BigQuery Loader

### `save_df_to_bigquery(df, table_name, profile, write_disposition, merge_keys, partition_field, cluster_fields)`

Loads a DataFrame to BigQuery with type safety and optional merge logic.

**Process:**
1. Load GCP credentials (service account JSON or ADC)
2. Get declared schema from `src/schema/bigquery.py`
3. Normalize column names for BigQuery identifiers
4. Coerce each column to its declared type:
   - `DATE` / `TIMESTAMP` → parsed from string or datetime objects
   - `STRING` → any dict/list serialized to JSON string
   - `BOOL` → handles `True/False`, `1/0`, `"true"/"false"`, `"yes"/"no"`
   - `INT64` / `NUMERIC` / `FLOAT64` → numeric coercion
5. Load with `write_disposition`:
   - `WRITE_APPEND` — appends rows (no deduplication)
   - `WRITE_TRUNCATE` — replaces all data
   - `WRITE_EMPTY` — fails if table has data
6. If `merge_keys` provided — performs DML MERGE for upsert semantics

---

## 17. CLI Reference

Run `python main.py --help` or `python main.py <command> --help` for full usage.

### Global Options

| Option | Description |
|---|---|
| `--db-profile PROFILE` | Use a named profile for DB/BQ/account config |
| `--to-bigquery` | Also sync to BigQuery |
| `--no-db` | Skip PostgreSQL load |
| `--workers N` | Parallel account fetch threads (default 1) |
| `--csv PATH` | Export DataFrame to CSV |

---

### Command Reference

#### Insights

```
insights-daily        Fetch delivery metrics for a date preset (default: yesterday)
  --level             ad | adset | campaign | account
  --date-preset       yesterday | last_7d | last_30d | last_90d | last_quarter | last_year
  --breakdowns        age,gender,country,attribution_setting (comma-separated)

insights-range        Fetch historical metrics over a date range
  --from-date         YYYY-MM-DD
  --to-date           YYYY-MM-DD
  --chunk-days        Chunk size in days (default 7)
  --level / --breakdowns  Same as insights-daily
```

#### Dimensions

```
accounts-info         Fetch account billing metadata → dim_meta_accounts
accounts-registry     Load accounts from CSV → dim_meta_account_registry
campaigns-info        Fetch campaigns → dim_meta_campaigns  [--status ACTIVE,PAUSED]
adsets-info           Fetch ad sets → dim_meta_adsets       [--status ACTIVE,PAUSED]
ads-info              Fetch ads → dim_meta_ads               [--status ACTIVE,PAUSED]
creatives-info        Fetch creatives → dim_meta_creatives
```

#### Orchestration

```
dims-refresh          All dims in sequence + optional BQ sync
accounts-insights     accounts-info + last 7 days insights + BQ sync
run-daily             dims + rolling insights + BQ sync  [--days-back N] [--skip-dims]
full-refresh          dims + date range insights + BQ sync  --from-date ... --to-date ...
```

#### BigQuery Operations

```
sync-to-bigquery      Sync specific tables from Postgres to BQ
  --tables            Comma-separated table names (default: all ETL tables)
  --mode              merge | truncate | append

materialize-combined  Rebuild fact_meta_ads_combined from vw_meta_ads_full

reset-bigquery        Drop all BQ tables and rebuild from Postgres
```

#### Database Maintenance

```
backup-db             Create backup schema (backup_YYYYMMDD_HHMMSS)
list-backups          Show all backup schemas with row counts
restore-backup        Restore from a backup schema  --schema backup_20250101_120000
drop-backup           Delete a backup schema

prune-columns         Drop columns marked 'excluded' in rename CSV
  --dry-run           Preview without executing
  --also-bigquery     Also drop from BigQuery

migrate-renames       Rename columns per CSV rename_to mapping
  --dry-run           Preview without executing
  --also-bigquery     Also rename in BigQuery

delete-account-data   Delete all rows for accounts marked delete=TRUE in CSV
  --yes               Execute (default is preview only)
  --dry-run           Show row counts without deleting
  --also-bigquery     Also delete from BigQuery
  --csv PATH          Path to delete template CSV

clean-db              Drop non-ETL tables and views from public schema

health-check          Validate all connections (Postgres, BigQuery, Meta API)
```

---

## 18. Views

### `vw_meta_ads_full` (PostgreSQL + BigQuery)

A view that joins the fact table with all dimension tables to produce a denormalized analytics table.

**Source Tables:**
- `fact_meta_delivery_ad f` — Core delivery metrics
- `dim_meta_accounts acc` — Account attributes (joined on `REPLACE(acc.id, 'act_', '') = f.account_id`)
- `dim_meta_ads ad` — Ad attributes
- `dim_meta_creatives cr` — Creative attributes

**Key Columns:**

All fact columns (date_start, spend, reach, impressions, clicks, actions, video metrics) plus:

From `dim_meta_accounts`:
- `currency`, `timezone_id`, `account_status`, `business_name`
- `disable_reason`, `funding_source_display`, `funding_source_id`, `funding_source_type`
- `account_created_time`

From `dim_meta_ads`:
- `ad_status`, `effective_status`, `configured_status`, `creative_id`
- `ad_created_time`, `ad_updated_time`
- `ad_review_feedback_*` (dynamically included if present)

From `dim_meta_creatives`:
- `creative_name`, `creative_title`, `creative_body`, `creative_description`
- `call_to_action_type`, `image_url`, `image_hash`, `thumbnail_url`
- `video_id`, `link_url`, `object_url`, `display_url`
- `effective_object_story_id`, `creative_status`

**Dynamic Columns:** Any non-standard fact columns (e.g., `actions_link_click`, `video_30_sec_watched_actions_video_view`) discovered at view creation time are appended automatically.

**Note:** Only dim columns that actually exist in the table are included — the view skips columns that were pruned.

---

### `fact_meta_ads_combined`

A materialized copy of `vw_meta_ads_full`. Created by `materialize-combined`:

```sql
DROP TABLE IF EXISTS fact_meta_ads_combined;
CREATE TABLE fact_meta_ads_combined AS
SELECT * FROM vw_meta_ads_full;
```

**Purpose:** Power BI connects to this table for fast queries without runtime join cost. It should be rebuilt after any data update via `python main.py materialize-combined`.

---

## 19. Maintenance Operations

### Backup & Restore

The backup system copies all ETL tables into a timestamped schema (e.g., `backup_20250501_120000`) within the same PostgreSQL database.

```bash
# Create backup
python main.py backup-db

# List available backups
python main.py list-backups

# Restore (DESTRUCTIVE — overwrites public schema tables)
python main.py restore-backup --schema backup_20250501_120000

# Dry-run restore (shows what would happen)
python main.py restore-backup --schema backup_20250501_120000 --dry-run

# Delete a backup
python main.py drop-backup --schema backup_20250501_120000
```

---

### Delete Account Data

Permanently delete all data for specific accounts from all tables (PostgreSQL and/or BigQuery).

**Template CSV:** `data/delete_accounts_template.csv`

| Column | Description |
|---|---|
| `account_id` | Account ID (with `act_` prefix) |
| `account_name` | Display name |
| `delete` | `TRUE` to mark for deletion, `FALSE` to skip |

```bash
# Preview only (no changes)
python main.py delete-account-data

# Preview with row counts
python main.py delete-account-data --dry-run --also-bigquery

# Execute in PostgreSQL only
python main.py delete-account-data --yes

# Execute in both PostgreSQL and BigQuery
python main.py delete-account-data --yes --also-bigquery

# Use a custom CSV
python main.py delete-account-data data/my_list.csv --yes --also-bigquery
```

**How it resolves which rows to delete:**

1. **Tables with `account_id` directly** — `DELETE WHERE account_id = ANY(ids)`. Both `act_XXXXX` and `XXXXX` forms are passed to cover fact tables (no prefix) and dim tables (with prefix).

2. **`dim_meta_accounts`** — Uses `id` column with `act_` prefix form.

3. **Breakdown fact tables without `account_id`** — Resolved via a subquery join through the relevant dim table:
   ```sql
   DELETE FROM fact_meta_delivery_adset__age
   WHERE adset_id IN (
     SELECT adset_id FROM dim_meta_adsets
     WHERE account_id = ANY(ids)
   )
   ```

---

### Prune Excluded Columns

Drops database columns for fields marked `excluded` in the rename CSV.

```bash
# Preview
python main.py prune-columns --dry-run

# Execute in PostgreSQL only
python main.py prune-columns

# Execute in PostgreSQL + BigQuery
python main.py prune-columns --also-bigquery
```

---

### Rename Columns

Renames database columns for approved fields where `rename_to` differs from `current_database_column`.

```bash
# Preview
python main.py migrate-renames --dry-run

# Execute
python main.py migrate-renames

# Execute in PostgreSQL + BigQuery
python main.py migrate-renames --also-bigquery
```

---

### Clean Database

Drops any tables or views in the `public` schema that are NOT part of the ETL schema (useful after experimentation).

```bash
python main.py clean-db
```

---

## 20. Scheduler & Windows Task Scheduler

### Registered Tasks

Two Windows Task Scheduler tasks are registered by `scripts/setup_task.ps1`:

#### `MetaETL_AccountsInsights`

| Property | Value |
|---|---|
| Script | `scripts/accounts_insights_sync.ps1` |
| Schedule | Every 2 hours: 08:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00 |
| Also runs | At logon (catches missed runs) |
| Command | `python main.py accounts-insights --to-bigquery` |
| Log | `logs/accounts_insights_YYYY-MM-DD.log` |
| Timeout | 3 hours |
| On failure | Restart once after 30 minutes |

#### `MetaETL_DimsRefresh`

| Property | Value |
|---|---|
| Script | `scripts/dims_sync.ps1` |
| Schedule | Daily at 10:00 AM |
| Also runs | At logon (catches missed runs) |
| Command | `python main.py dims-refresh --to-bigquery` |
| Log | `logs/dims_sync_YYYY-MM-DD.log` |
| Timeout | 3 hours |
| On failure | Restart once after 30 minutes |

### Task Management Commands (PowerShell as Admin)

```powershell
# Initial setup (run once as Administrator)
.\scripts\setup_task.ps1

# Enable tasks after they were disabled
Enable-ScheduledTask -TaskName "MetaETL_AccountsInsights"
Enable-ScheduledTask -TaskName "MetaETL_DimsRefresh"

# Run immediately
Start-ScheduledTask -TaskName "MetaETL_AccountsInsights"
Start-ScheduledTask -TaskName "MetaETL_DimsRefresh"

# Check status and last/next run
Get-ScheduledTaskInfo -TaskName "MetaETL_AccountsInsights"
Get-ScheduledTaskInfo -TaskName "MetaETL_DimsRefresh"

# Disable without deleting
Disable-ScheduledTask -TaskName "MetaETL_AccountsInsights"

# Remove tasks
Unregister-ScheduledTask -TaskName "MetaETL_AccountsInsights" -Confirm:$false
Unregister-ScheduledTask -TaskName "MetaETL_DimsRefresh" -Confirm:$false
```

### Log Rotation

Both scripts automatically delete log files older than 30 days from the `logs/` directory. No manual cleanup is required.

### Alternative: Python Scheduler

`scheduler.py` is a pure-Python alternative that can run in the foreground instead of using Task Scheduler:

```bash
python scheduler.py
```

It runs the same two jobs on the same schedule and logs to `logs/scheduler.log`.

---

## 21. BigQuery Sync & Reset

### Sync Specific Tables

```bash
# Sync a single table
python main.py sync-to-bigquery --tables fact_meta_delivery_ad

# Sync multiple tables
python main.py sync-to-bigquery --tables dim_meta_ads,dim_meta_campaigns

# Sync all ETL tables
python main.py sync-to-bigquery
```

### Materialize Combined Table

Rebuilds `fact_meta_ads_combined` (the Power BI source table) from the view:

```bash
# PostgreSQL only
python main.py materialize-combined

# PostgreSQL + BigQuery
python main.py materialize-combined --to-bigquery
```

This should be run after any batch of insights data is loaded to refresh the Power BI dataset.

### Full BigQuery Reset

Use when BigQuery is out of sync and needs to be completely rebuilt from PostgreSQL:

```bash
python main.py reset-bigquery
```

**Warning:** This drops ALL existing BigQuery tables before rebuilding. It then:
1. Syncs all dimension tables
2. Syncs all fact tables (with merge strategy)
3. Materializes `fact_meta_ads_combined`
4. Rebuilds `vw_meta_ads_full`

---

## 22. Testing

Tests are located in `tests/` and use `pytest`.

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_transform_core.py
```

### Test Coverage

| Test File | What It Covers |
|---|---|
| `test_config.py` | Settings loading, profile resolution, account registry filtering |
| `test_names.py` | Column name normalization for the 63-char PostgreSQL limit |
| `test_transform_core.py` | JSON flattening, action array expansion, numeric coercion |
| `test_bigquery_loader.py` | BigQuery type coercion, column normalization |
| `test_sync_to_bigquery.py` | Sync mode resolution (merge, truncate, append) |
| `test_meta_insights_bigquery.py` | Insights transformation and BigQuery loading |
| `test_accounts_registry.py` | Account registry filtering by profile and include_in_etl flag |
| `test_ads_info.py` | Ads metadata extraction and transformation |

---

## 23. Data Flow — End to End

### Daily Scheduled Run (every 2 hours)

```
Windows Task Scheduler
    → accounts_insights_sync.ps1
        → python main.py accounts-insights --to-bigquery
            │
            ├── accounts-info pipeline
            │   ├── GraphAPIClient.fetch_list("me/adaccounts")
            │   ├── flatten_json + apply_rename_map
            │   └── save_df_to_postgres_upsert(dim_meta_accounts)
            │
            ├── insights-daily pipeline (last 7 days, ad level)
            │   ├── GraphAPIClient.fetch_list("{account}/insights", date_preset=last_7d)
            │   ├── normalize_insights (split results, flatten, rename)
            │   └── save_df_to_postgres_upsert(fact_meta_delivery_ad)
            │
            └── sync-to-bigquery
                ├── iterate_table_chunks(dim_meta_accounts) → save_df_to_bigquery (WRITE_APPEND)
                └── iterate_table_chunks(fact_meta_delivery_ad) → save_df_to_bigquery (MERGE)
```

### Historical Backfill

```
python main.py full-refresh --from-date 2024-01-01 --to-date 2024-12-31 --to-bigquery
    │
    ├── All dim pipelines (campaigns, adsets, ads, creatives, accounts)
    │
    ├── insights-range (weekly chunks: 2024-01-01→01-07, 01-07→01-14, ...)
    │   └── For each chunk:
    │       ├── fetch_insights(since, until)
    │       ├── normalize_insights
    │       └── save_df_to_postgres_upsert(fact_meta_delivery_ad)
    │
    └── sync-to-bigquery (all ETL tables)
```

### Power BI Refresh

```
python main.py materialize-combined --to-bigquery
    │
    ├── DROP TABLE IF EXISTS fact_meta_ads_combined
    ├── CREATE TABLE fact_meta_ads_combined AS SELECT * FROM vw_meta_ads_full
    │   (joins fact_meta_delivery_ad + dim_meta_accounts + dim_meta_ads + dim_meta_creatives)
    └── save_df_to_bigquery(fact_meta_ads_combined, WRITE_TRUNCATE)
```

---

## 24. Troubleshooting

### 0 rows deleted when running delete-account-data

**Cause:** Fact tables store `account_id` without the `act_` prefix, but dim tables and the CSV use the `act_` prefix. The delete pipeline passes both forms to match either format.

**Fix:** Ensure you are on the latest version of `delete_account_data.py` which includes `_both_id_forms()`.

### "Application request limit reached" in insights pipeline

**Cause:** Meta API rate limit hit. The pipeline waits 60 seconds and retries once.

**Fix:** Reduce `--workers` to 1 (default). For range queries, increase `--chunk-days` to reduce frequency of API calls.

### Postgres "duplicate key value violates unique constraint"

**Cause:** Two rows in the DataFrame have the same upsert key. The loader deduplicates on `unique_cols` before inserting.

**Fix:** Check for duplicate rows with `.duplicated(subset=unique_cols)`. This is usually caused by the API returning the same record twice.

### BigQuery schema mismatch

**Cause:** A column was added to PostgreSQL but the BigQuery table has an older schema.

**Fix:** Run `python main.py reset-bigquery` to rebuild BigQuery from the current PostgreSQL state, or use `sync-to-bigquery --mode truncate` for specific tables.

### Windows Task Scheduler: "Access is denied" when enabling tasks

**Cause:** Enabling scheduled tasks requires Administrator privileges.

**Fix:** Open PowerShell as Administrator (Win + X → Terminal (Admin)) and run:
```powershell
Enable-ScheduledTask -TaskName "MetaETL_AccountsInsights"
Enable-ScheduledTask -TaskName "MetaETL_DimsRefresh"
```

### Column not found in vw_meta_ads_full view

**Cause:** The view references a column that was pruned from the source dim table.

**Fix:** The view builder dynamically skips missing columns. Run:
```bash
python main.py sync-to-bigquery --tables vw_meta_ads_full
```
Or recreate the view by running `materialize-combined`.

### "New API fields detected" in logs

**Cause:** The Meta API returned a field not declared in `api_field_rename_template.csv`. The field was added as `pending` and is not being loaded.

**Fix:** Open `data/api_field_rename_template.csv`, find the new `pending` rows, set `rename_to` and change `status` to `approved`, then re-run the pipeline.

---

*Generated from codebase — facebook_etl_new_big — Meta Graph API v25.0*
