CLI Commands (main.py)
=====================

Global flags:
- `--db-profile PROFILE` selects `DB_CONN_STRING_<PROFILE>` (default uses DB_CONN_STRING / DB_CONN_STRING_DEFAULT)
- `--no-db` skips DB writes

Commands:
- `insights-daily [level] [--date-preset PRESET] [--csv path]`
  - level: ad | adset | campaign | account (default ad)
- `insights-range <from_date> <to_date> [level] [chunk_days] [--csv path]`
  - dates: YYYY-MM-DD; level default ad; chunk_days default 7
- `insights-clean [level] [--breakdowns b1,b2] [--from-date YYYY-MM-DD] [--to-date YYYY-MM-DD] [--limit N] [--no-db]`
  - Reprocess raw insights (meta_insights_raw) into fact tables; breakdowns filter picks the target table
- `clean-dim <entity> [--limit N] [--no-db]`
  - Reprocess raw dimension tables into their targets; entity: accounts, creatives, campaigns, adsets, ads, ad-previews
- `accounts-info [csv_path]`
- `creatives-info [csv_path]`
- `campaigns-info [csv_path]`
- `adsets-info [csv_path]`
- `ads-info [csv_path]`
- `ad-previews [csv_path] [started_after]`
  - Formats default: feed/story/reels; preview links are short-lived
  - started_after filters ads by created_time before preview fetch
- `db-truncate [--tables t1 t2 ...]`
  - Without --tables, truncates all tables defined in unique_keys.py
