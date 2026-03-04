Project Overview
================
Meta (Facebook) marketing ETL that fetches insights, accounts, campaigns, adsets, ads (settings), ad creatives (payload), and ad previews, then writes raw JSON and cleaned tables to Postgres (optional CSV). Supports multiple DB profiles, automatic schema creation/extension, and replay from raw.

Prerequisites
-------------
- Python 3.12+
- Install: `pip install -r requirements.txt`
- `.env`:
  - `META_ACCESS_TOKEN` (required), `META_API_VERSION` (default v22.0)
  - `META_AD_ACCOUNT_IDS` and optional `META_AD_ACCOUNT_IDS_<PROFILE>`
  - `DB_CONN_STRING` or `DB_CONN_STRING_<PROFILE>`
  - `DATA_DIR` (optional, default `./data`)

Core CLI (main.py)
------------------
Global flags: `--db-profile PROFILE` picks accounts/DB; `--no-db` skips DB writes.
- Insights daily: `python main.py insights-daily [level] [--date-preset PRESET] [--csv PATH] [--workers N]`
- Insights range: `python main.py insights-range <from> <to> [level] [chunk_days] [--csv PATH] [--workers N]`
- Re-clean insights raw: `python main.py insights-clean [level] [--breakdowns b1,b2] [--from-date] [--to-date] [--limit N]`
- Re-clean dim raw: `python main.py clean-dim <entity> [--limit N]`
  - entity: `accounts|creatives|campaigns|adsets|ads|ad-previews`
- Dimension fetchers: `accounts-info`, `creatives-info`, `campaigns-info`, `adsets-info`, `ads-info`, `ad-previews`
- Truncate: `python main.py db-truncate [--tables t1 t2 ...]`

Architecture
------------
- Raw tables (append-only JSONB): `meta_insights_raw`, `meta_accounts_raw`, `meta_creatives_raw`, `meta_campaigns_raw`, `meta_adsets_raw`, `meta_ads_raw`, `meta_ads_previews_raw`.
- Cleaned insights facts: `fact_meta_delivery_ad[_breakdowns]`, `fact_meta_delivery_adset`, `fact_meta_delivery_campaign`, `fact_meta_delivery_account`.
- Cleaned dimensions:
  - `dim_meta_accounts`: account metadata.
  - `dim_meta_campaigns`: campaign metadata.
  - `dim_meta_adsets`: adset metadata + targeting JSONB.
  - `dim_meta_ads_settings`: ad object/settings from `/ads` (status/effective_status/configured_status, adset_id, campaign_id, created_time, updated_time, creative_id, creative_name). This is the bridge to creatives.
  - `dim_meta_creatives`: creative payload from `/adcreatives` (media/copy: image/video URLs, body, title, CTA, object_story_spec, asset_feed_spec, template fields).
  - `dim_meta_ads`: previews from `generatepreviews` (per ad_id, per format). Optional; only needed if you display live previews.
- Joins for reporting: facts → `dim_meta_ads_settings` (ad_id, creative_id, status) → `dim_meta_creatives` (media/copy). Previews join on ad_id when needed.

API Endpoints and Fields
------------------------
- `/ads` (ads-info): `ADS_SETTINGS_FIELDS` currently include id, name, account_id, adset_id, campaign_id, created_time, updated_time, status, effective_status, configured_status, creative{id,name}. Heavier JSON fields (issues_info, ad_review_feedback, tracking_specs, delivery_info) are omitted by default for size/perf.
- `/adcreatives` (creatives-info): `CREATIVE_FIELDS` include id, account_id, name, status, object_story_spec, asset_feed_spec, template_url(_spec), degrees_of_freedom_spec, dynamic_ad_voice, product_set_id, url_tags, link_url, instagram_permalink_url, image_hash, image_url, thumbnail_url, video_id, body, title, call_to_action_type. Note: for catalog/dynamic creatives, image_url/thumbnail_url are often empty; media is inside asset_feed_spec/object_story_spec.
- `/{act}/generatepreviews` (ad-previews): per ad_id, returns short-lived preview URLs/HTML. Unsupported for some creative types and requires page permissions.

Data Flow (per pipeline)
------------------------
1) Fetch from Graph with pagination and retries (`src/clients/graph_client.py`).
2) Write raw payloads to `meta_<entity>_raw` (if DB enabled).
3) Flatten JSON (`flatten_json`), ensure ids/names (`ensure_id_and_name`), numeric cleanup (`fill_numeric_keep_nulls`).
4) Optional CSV export.
5) Upsert into target dim/fact using `save_df_to_postgres_upsert` and `UNIQUE_KEYS`.
6) Replay without API: `insights-clean` and `clean-dim` reprocess raw tables.

Schema Handling
---------------
- Column names normalized (lowercase, underscores, trimmed from the left to 63 chars).
- ID-like columns stored as TEXT to avoid bigint issues.
- Insights list/dict metrics kept as JSONB (not expanded) to prevent column explosion.
- Schema manager auto-creates tables and adds missing columns; it does not drop columns.

Efficiency Review (for developers)
----------------------------------
- Network/API:
  - `/ads` pulls a compact field list; previews are isolated to avoid bloating ad settings.
  - `/adcreatives` includes bulky specs because catalog/dynamic creatives require them for media/copy.
  - ThreadPool across accounts; pagination follows `paging.next`.
  - Incremental filters (e.g., updated_time) are not yet implemented; could be added to reduce daily volume.
- Storage/DB:
  - Raw + cleaned pattern allows replay without re-hitting the API.
  - Upserts dedupe on `UNIQUE_KEYS`; duplicate normalized columns are merged.
  - IDs coerced to string before upsert to avoid duplicate PKs from numeric coercion.
  - Previews live in `dim_meta_ads` to keep `dim_meta_ads_settings` lean.
- Reporting joins:
  - facts → `dim_meta_ads_settings` (ad status + creative_id) → `dim_meta_creatives` (media/copy). Add `dim_meta_ads` only if preview URLs/HTML are required.

Operational Modes
-----------------
- Minimal (names + status): run `ads-info`; skip creatives and previews; join facts to `dim_meta_ads_settings` only.
- Media/copy needed: also run `creatives-info`; join to `dim_meta_creatives`.
- Live previews needed: run `ad-previews`; optionally filter by `started_after` and effective_statuses or cap volume if you extend the pipeline.
- Reprocessing: use `clean-dim <entity>` and `insights-clean` to rebuild from raw without new API calls.

Examples
--------
- Daily insights: `python main.py insights-daily ad`
- Range insights to CSV: `python main.py insights-range 2025-10-01 2025-10-10 ad 1 --csv data/insights_oct.csv`
- Re-clean raw insights: `python main.py insights-clean ad --from-date 2025-10-01 --to-date 2025-10-10 --breakdowns age,gender`
- Re-clean dim creatives: `python main.py clean-dim creatives --limit 1000`
- Ads settings: `python main.py ads-info data/ads_settings.csv`
- Creatives: `python main.py creatives-info data/creatives.csv`
- Ad previews: `python main.py ad-previews data/ad_previews.csv 2025-11-20`
- Truncate: `python main.py db-truncate`

Notes and Limitations
---------------------
- Preview URLs/HTML are short-lived; regenerate when needed.
- `started_after` filters ad previews by `created_time` (Ads API does not expose start_time).
- For catalog/dynamic creatives, image_url/thumbnail_url can be empty; use asset_feed_spec/object_story_spec for media.
- Rate limiting: retries on 429/5xx with backoff; range pipeline paces chunks by 1s.
- CSV writer creates parent dirs; raises on permission errors.
