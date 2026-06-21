# BigQuery Runbook

This guide walks through the full BigQuery workflow in this repo:

1. Configure BigQuery access
2. Send fresh data from the ETL directly to BigQuery
3. Load data into PostgreSQL
4. Sync PostgreSQL tables into existing BigQuery tables

Use these steps from the repo root:

```powershell
C:\Users\Mahmoud Morsy\Desktop\facebook_etl_new
```

## 1. Prerequisites

Make sure these are ready first:

- Python dependencies are installed
- PostgreSQL is installed and running if you want SQL loads or syncs
- `.env` contains valid Meta, PostgreSQL, and BigQuery settings
- your BigQuery credential file exists if you are using key-file auth

Install dependencies:

```powershell
pip install -r requirements.txt
```

Optional but recommended for PostgreSQL:

```powershell
pip install psycopg2-binary
```

Optional but recommended for future BigQuery compatibility:

```powershell
pip install pandas-gbq>=0.26.1
```

## 2. Configure `.env`

At minimum, make sure these values exist in [.env](/c:/Users/Mahmoud%20Morsy/Desktop/facebook_etl_new/.env):

```ini
META_ACCESS_TOKEN=your_meta_token
META_API_VERSION=v25.0
META_AD_ACCOUNT_IDS=act_123,act_456

DB_CONN_STRING=postgresql://postgres:your_password@localhost:5432/ads_db

BQ_PROJECT_ID=your-gcp-project-id
BQ_DATASET=your_dataset_name
BQ_LOCATION=europe-west2
BQ_CREDENTIALS_PATH=credentials/bigquery-service-account.json
```

Notes:

- `BQ_DATASET` is the BigQuery dataset name, not the table name
- `BQ_CREDENTIALS_PATH` should point to a real service-account JSON if you are not using ADC
- the PostgreSQL user in `DB_CONN_STRING` must be able to connect to the server

## 3. Confirm the BigQuery credential file

If you are using a key file, confirm the file exists in [credentials](/c:/Users/Mahmoud%20Morsy/Desktop/facebook_etl_new/credentials).

Expected example:

```text
credentials/bigquery-service-account.json
```

## 4. First-time direct load to BigQuery

These commands send ETL output directly to BigQuery.

### 4.1 Send ad accounts to BigQuery

This writes the cleaned accounts dimension to:

- `dim_meta_accounts`

BigQuery-only run:

```powershell
python main.py accounts-info --no-db --to-bigquery
```

BigQuery plus PostgreSQL:

```powershell
python main.py accounts-info --to-bigquery
```

### 4.2 Send today's ad insights to BigQuery

This writes ad-level reporting data to:

- `fact_meta_delivery_ad`

BigQuery-only run:

```powershell
python main.py insights-daily ad --date-preset today --no-db --to-bigquery
```

BigQuery plus PostgreSQL:

```powershell
python main.py insights-daily ad --date-preset today --to-bigquery
```

### 4.3 Send today's account-level insights to BigQuery

This writes account-level reporting data to:

- `fact_meta_delivery_account`

```powershell
python main.py insights-daily account --date-preset today --no-db --to-bigquery
```

## 5. Load the same data into PostgreSQL first

If you want to sync from PostgreSQL later, you need the SQL tables populated first.

### 5.1 Load ad accounts into PostgreSQL

```powershell
python main.py accounts-info
```

### 5.2 Load today's ad insights into PostgreSQL

```powershell
python main.py insights-daily ad --date-preset today
```

### 5.3 Load today's account-level insights into PostgreSQL

```powershell
python main.py insights-daily account --date-preset today
```

## 6. Sync PostgreSQL to BigQuery

The sync command reads from PostgreSQL and exports into BigQuery.

Important rule:

- sync only writes into BigQuery tables that already exist

That means:

- if a target BigQuery table does not exist, sync will fail for that table
- create the BigQuery table first by using a direct `--to-bigquery` ETL command, or create it in BigQuery yourself

### 6.1 Sync one table

Examples:

```powershell
python main.py sync-to-bigquery dim_meta_accounts
python main.py sync-to-bigquery fact_meta_delivery_ad
python main.py sync-to-bigquery fact_meta_delivery_account
```

Default behavior:

- `fact_meta_delivery_ad` uses merge
- `fact_meta_delivery_account` uses merge
- other tables use truncate/load in `auto` mode

### 6.2 Sync all matching tables automatically

This is the simplest sync command:

```powershell
python main.py sync-to-bigquery all
```

What it does:

- lists PostgreSQL tables
- lists existing BigQuery tables in your configured dataset
- finds the overlap
- syncs only the overlapping tables

Example:

- PostgreSQL has 5 tables
- BigQuery has 2 of those table names
- `sync-to-bigquery all` syncs only those 2

### 6.3 Force a specific sync mode

Examples:

```powershell
python main.py sync-to-bigquery dim_meta_accounts --mode truncate
python main.py sync-to-bigquery fact_meta_delivery_ad --mode merge
python main.py sync-to-bigquery all --mode auto
```

Modes:

- `auto`: merge for known fact tables, truncate/load for others
- `merge`: only valid for tables with configured merge keys
- `truncate`: replace table contents
- `append`: append rows

## 7. Recommended start-to-finish flows

### Option A: Direct ETL to BigQuery only

Use this when you want fresh API data in BigQuery immediately.

```powershell
python main.py accounts-info --no-db --to-bigquery
python main.py insights-daily ad --date-preset today --no-db --to-bigquery
python main.py insights-daily account --date-preset today --no-db --to-bigquery
```

### Option B: Load PostgreSQL first, then sync to BigQuery

Use this when PostgreSQL is your system of record and BigQuery should mirror it.

```powershell
python main.py accounts-info
python main.py insights-daily ad --date-preset today
python main.py insights-daily account --date-preset today
python main.py sync-to-bigquery all
```

### Option C: Write to both PostgreSQL and BigQuery in one ETL run

Use this when you want both sinks updated at once.

```powershell
python main.py accounts-info --to-bigquery
python main.py insights-daily ad --date-preset today --to-bigquery
python main.py insights-daily account --date-preset today --to-bigquery
```

## 8. Notes on schema behavior

This repo now tries to align known BigQuery tables to the declared schema.

Important behavior:

- direct BigQuery loads and syncs use the same declared schema source
- undeclared columns are dropped before BigQuery load
- missing declared columns are added as `NULL`
- BigQuery types are mapped from the PostgreSQL-style schema definitions

This matters for tables like `fact_meta_delivery_ad`:

- if PostgreSQL contains new `actions_*` columns that are not declared yet, sync will drop them before loading to BigQuery
- if you want those columns in BigQuery too, add them to the declared schema in [tables.py](/c:/Users/Mahmoud%20Morsy/Desktop/facebook_etl_new/src/schema/tables.py)

## 9. Troubleshooting

### PostgreSQL auth error

Example:

```text
password authentication failed for user "postgres"
```

Fix:

- update `DB_CONN_STRING` in [.env](/c:/Users/Mahmoud%20Morsy/Desktop/facebook_etl_new/.env)

### BigQuery target table does not exist

Example:

```text
Target BigQuery table does not exist
```

Fix:

- create it first using a direct `--to-bigquery` ETL command
- or create the table manually in BigQuery

### Network error reaching Meta API

Example:

```text
Failed to establish a new connection
```

Fix:

- check internet access
- check firewall or VPN restrictions
- retry outside a restricted shell if needed

### Columns dropped during BigQuery load

Example:

```text
Dropping columns not declared for 'fact_meta_delivery_ad'
```

Fix:

- update [tables.py](/c:/Users/Mahmoud%20Morsy/Desktop/facebook_etl_new/src/schema/tables.py) if those columns should be part of the declared schema

## 10. Quick command list

```powershell
python main.py accounts-info --no-db --to-bigquery
python main.py insights-daily ad --date-preset today --no-db --to-bigquery
python main.py insights-daily account --date-preset today --no-db --to-bigquery

python main.py accounts-info
python main.py insights-daily ad --date-preset today
python main.py insights-daily account --date-preset today

python main.py sync-to-bigquery dim_meta_accounts
python main.py sync-to-bigquery fact_meta_delivery_ad
python main.py sync-to-bigquery fact_meta_delivery_account
python main.py sync-to-bigquery all
```
