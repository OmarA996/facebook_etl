CLI Commands (main.py)
=====================

Global flags:
- `--db-profile PROFILE` selects registry rows for that `profile_name`, `DB_CONN_STRING_<PROFILE>`, and profile-specific BigQuery config when available
- `--no-db` skips DB writes
- `--to-bigquery` loads normalized output to BigQuery
- `--bq-write-disposition` one of: `WRITE_APPEND` (default), `WRITE_TRUNCATE`, `WRITE_EMPTY`
- `--bq-table` optional BigQuery table override

Commands:
- `insights-daily [level] [--date-preset PRESET] [--csv path]`
  - level: ad | adset | campaign | account (default ad)
- `insights-range <from_date> <to_date> [level] [chunk_days] [--csv path]`
  - dates: YYYY-MM-DD; level default ad; chunk_days default 7
- `accounts-info [csv_path]`
- `accounts-registry [csv_path]`
  - writes an editable registry with `account_id`, `account_name`, `account_status`, `profile_name`, `include_in_etl`, and `notes`
  - reruns preserve existing `profile_name`, `include_in_etl`, and `notes`
  - ETL account selection reads this registry first; `.env` account ids are only a fallback
- `sync-to-bigquery <table_name> [<table_name> ...] [--mode auto|merge|truncate|append] [--chunk-size N] [--bq-table NAME]`
  - syncs PostgreSQL tables into existing BigQuery tables only
  - `auto` defaults to merge for `fact_meta_delivery_ad` and `fact_meta_delivery_account`, otherwise truncate/load
- `sync-to-bigquery all [--mode auto|merge|truncate|append] [--chunk-size N]`
  - automatically syncs only the tables that exist in both PostgreSQL and BigQuery
