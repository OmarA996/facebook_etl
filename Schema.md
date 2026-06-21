# Database Schema Reference

This document describes the database entities defined by the codebase, their columns, data types, keys, and logical relationships.

## Scope And Conventions

- Source of truth:
  - `src/schema/tables.py` for base table definitions
  - `src/schema/unique_keys.py` for unique keys used by UPSERT logic
  - `src/etl/load/schema_manager.py` for runtime schema evolution rules
- Database engine: PostgreSQL
- IDs are stored as `TEXT` to avoid overflow and preserve external Meta identifiers.
- Foreign keys are not declared in SQL today. Relations listed below are logical joins used by the ETL and reporting layer.
- Some tables are schema-on-write:
  - the loader can add missing columns from incoming DataFrames
  - some `TEXT` columns may be promoted to `NUMERIC` if incoming data is numeric-like
- Raw tables are append-only. Dimension and fact tables are upserted using the unique keys below.

## High-Level Model

### Core runtime entities

- `dim_meta_accounts`
- `fact_meta_delivery_ad`
- `fact_meta_delivery_adset`
- `fact_meta_delivery_campaign`
- `fact_meta_delivery_account`
- `meta_accounts_raw`
- `meta_insights_raw`

### Legacy or compatibility entities

- `dim_meta_creatives`
- `dim_meta_ads`
- `dim_meta_campaigns`
- `dim_meta_adsets`
- `dim_meta_ads_settings`
- `meta_creatives_raw`
- `meta_campaigns_raw`
- `meta_adsets_raw`
- `meta_ads_raw`
- `meta_ads_previews_raw`

## Relationship Summary

### Logical primary joins

- `fact_meta_delivery_ad.account_id -> dim_meta_accounts.id`
- `fact_meta_delivery_ad.campaign_id -> dim_meta_campaigns.campaign_id`
- `fact_meta_delivery_ad.adset_id -> dim_meta_adsets.adset_id`
- `fact_meta_delivery_ad.ad_id -> dim_meta_ads.ad_id`
- `fact_meta_delivery_ad.ad_id -> dim_meta_ads_settings.ad_id`
- `fact_meta_delivery_adset.campaign_id -> dim_meta_campaigns.campaign_id`
- `fact_meta_delivery_campaign.account_id -> dim_meta_accounts.id`
- Raw tables join back to their cleaned dimensions or facts through the business ID columns they carry in addition to their surrogate raw `id`.

### Constraint model

- Enforced primary keys exist only where the base schema declares `PRIMARY KEY`.
- Enforced uniqueness for upserts is created as a unique index from `src/schema/unique_keys.py`.
- No SQL-level foreign keys are currently enforced.

## Entity Definitions

## `dim_meta_accounts`

Purpose: cleaned account dimension loaded from the Meta accounts endpoint.

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `id` | `TEXT` | PK, UNIQUE | Meta ad account ID |
| `account_name` | `TEXT` |  | Display name |
| `account_status` | `INTEGER` |  | Meta status code |
| `currency` | `TEXT` |  | Account currency |
| `timezone_id` | `INTEGER` |  | Meta timezone identifier |
| `amount_spent` | `NUMERIC` |  | Lifetime spend |
| `spend_cap` | `NUMERIC` |  | Account cap |
| `balance` | `NUMERIC` |  | Current balance |
| `business_name` | `TEXT` |  | Owning business |
| `disable_reason` | `INTEGER` |  | Meta disable reason code |
| `funding_source_display` | `TEXT` |  | Funding source label |
| `funding_source_id` | `TEXT` |  | Funding source identifier |
| `funding_source_type` | `TEXT` |  | Funding source type |
| `created_time` | `TIMESTAMPTZ` |  | Account creation timestamp |

Relations:
- Parent entity for account-level facts and many legacy dimensions via `account_id`.

## `fact_meta_delivery_ad`

Purpose: ad-level delivery fact table for Meta insights.

Unique key:
- `UNIQUE (ad_id, date_start)`

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `ad_id` | `TEXT` | UNIQUE key part | Meta ad ID |
| `date_start` | `DATE` | UNIQUE key part | Grain start date |
| `date_stop` | `DATE` |  | Grain end date |
| `account_id` | `TEXT` | Logical FK | Joins to `dim_meta_accounts.id` |
| `account_name` | `TEXT` |  | Snapshot label |
| `campaign_id` | `TEXT` | Logical FK | Joins to `dim_meta_campaigns.campaign_id` |
| `campaign_name` | `TEXT` |  | Snapshot label |
| `adset_id` | `TEXT` | Logical FK | Joins to `dim_meta_adsets.adset_id` |
| `adset_name` | `TEXT` |  | Snapshot label |
| `ad_name` | `TEXT` |  | Snapshot label |
| `objective` | `TEXT` |  | Campaign objective |
| `optimization_goal` | `TEXT` |  | Optimization goal |
| `spend` | `NUMERIC` |  | Spend |
| `social_spend` | `NUMERIC` |  | Social spend |
| `reach` | `NUMERIC` |  | Reach |
| `impressions` | `NUMERIC` |  | Impressions |
| `clicks` | `NUMERIC` |  | Click count |
| `unique_clicks` | `NUMERIC` |  | Unique click count |
| `unique_inline_link_clicks` | `NUMERIC` |  | Unique inline link clicks |
| `results` | `JSONB` |  | Raw results payload |
| `results_indicator` | `TEXT` |  | Flattened result labels |
| `results_value` | `TEXT` |  | Flattened result values |
| `unique_outbound_clicks` | `JSONB` |  | Raw Meta metric payload |
| `outbound_clicks` | `JSONB` |  | Raw Meta metric payload |
| `actions` | `JSONB` |  | Raw Meta metric payload |
| `action_values` | `JSONB` |  | Raw Meta metric payload |
| `video_avg_time_watched_actions` | `JSONB` |  | Raw Meta metric payload |
| `video_p25_watched_actions` | `JSONB` |  | Raw Meta metric payload |
| `video_p50_watched_actions` | `JSONB` |  | Raw Meta metric payload |
| `video_play_actions` | `JSONB` |  | Raw Meta metric payload |
| `video_30_sec_watched_actions` | `JSONB` |  | Raw Meta metric payload |
| `video_p100_watched_actions` | `JSONB` |  | Raw Meta metric payload |
| `video_p75_watched_actions` | `JSONB` |  | Raw Meta metric payload |
| `video_p95_watched_actions` | `JSONB` |  | Raw Meta metric payload |

Relations:
- `account_id -> dim_meta_accounts.id`
- `campaign_id -> dim_meta_campaigns.campaign_id`
- `adset_id -> dim_meta_adsets.adset_id`
- `ad_id -> dim_meta_ads.ad_id`
- `ad_id -> dim_meta_ads_settings.ad_id`

## `fact_meta_delivery_adset`

Purpose: ad set-level delivery fact table.

Unique key:
- `UNIQUE (adset_id, date_start)`

Static base columns:

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `adset_id` | `TEXT` | UNIQUE key part | Meta ad set ID |
| `date_start` | `DATE` | UNIQUE key part | Grain start date |
| `date_stop` | `DATE` |  | Grain end date |

Expected runtime-inferred columns from the insights endpoint:
- `campaign_id TEXT`
- `campaign_name TEXT`
- `adset_name TEXT`
- `objective TEXT`
- `spend NUMERIC`
- `impressions NUMERIC`
- `reach NUMERIC`
- `clicks NUMERIC`
- `ctr NUMERIC`
- `cpm NUMERIC`
- `cpp NUMERIC`
- `frequency NUMERIC`

Relations:
- `campaign_id -> dim_meta_campaigns.campaign_id`
- `adset_id -> dim_meta_adsets.adset_id`

## `fact_meta_delivery_campaign`

Purpose: campaign-level delivery fact table.

Unique key:
- `UNIQUE (campaign_id, date_start)`

Static base columns:

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `campaign_id` | `TEXT` | UNIQUE key part | Meta campaign ID |
| `date_start` | `DATE` | UNIQUE key part | Grain start date |
| `date_stop` | `DATE` |  | Grain end date |

Expected runtime-inferred columns from the insights endpoint:
- `account_id TEXT`
- `account_name TEXT`
- `campaign_name TEXT`
- `objective TEXT`
- `spend NUMERIC`
- `impressions NUMERIC`
- `reach NUMERIC`
- `clicks NUMERIC`
- `ctr NUMERIC`
- `cpm NUMERIC`
- `cpp NUMERIC`
- `frequency NUMERIC`

Relations:
- `account_id -> dim_meta_accounts.id`
- `campaign_id -> dim_meta_campaigns.campaign_id`

## `fact_meta_delivery_account`

Purpose: account-level delivery fact table.

Unique key:
- `UNIQUE (account_id, date_start)`

Static base columns:

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `account_id` | `TEXT` | UNIQUE key part | Meta account ID |
| `date_start` | `DATE` | UNIQUE key part | Grain start date |
| `date_stop` | `DATE` |  | Grain end date |

Expected runtime-inferred columns from the insights endpoint:
- `account_name TEXT`
- `spend NUMERIC`
- `impressions NUMERIC`
- `reach NUMERIC`
- `clicks NUMERIC`
- `ctr NUMERIC`
- `cpm NUMERIC`
- `cpp NUMERIC`
- `frequency NUMERIC`

Relations:
- `account_id -> dim_meta_accounts.id`

## Dynamic Breakdown Fact Tables

These tables are not statically declared in `src/schema/tables.py`, but they are supported by `UNIQUE_KEYS` and are created or extended at runtime when breakdowns are requested.

Pattern:
- `fact_meta_delivery_<level>__<breakdown_suffix>`

Supported unique-key variants:
- `fact_meta_delivery_ad__age`
- `fact_meta_delivery_ad__gender`
- `fact_meta_delivery_ad__age_gender`
- `fact_meta_delivery_ad__country`
- `fact_meta_delivery_ad__attribution_setting`
- `fact_meta_delivery_adset__age`
- `fact_meta_delivery_adset__gender`
- `fact_meta_delivery_adset__age_gender`
- `fact_meta_delivery_adset__country`
- `fact_meta_delivery_adset__attribution_setting`
- `fact_meta_delivery_campaign__age`
- `fact_meta_delivery_campaign__gender`
- `fact_meta_delivery_campaign__age_gender`
- `fact_meta_delivery_campaign__country`
- `fact_meta_delivery_campaign__attribution_setting`
- `fact_meta_delivery_account__age`
- `fact_meta_delivery_account__gender`
- `fact_meta_delivery_account__age_gender`
- `fact_meta_delivery_account__country`
- `fact_meta_delivery_account__attribution_setting`

Breakdown key shapes:
- ad level: `UNIQUE (ad_id, date_start, <breakdown columns>)`
- ad set level: `UNIQUE (adset_id, date_start, <breakdown columns>)`
- campaign level: `UNIQUE (campaign_id, date_start, <breakdown columns>)`
- account level: `UNIQUE (account_id, date_start, <breakdown columns>)`

Typical columns:
- base ID column for the level
- `date_start`
- `date_stop`
- requested breakdown columns such as `age`, `gender`, `country`, `attribution_setting`
- runtime-inferred metric columns from the Meta response

Relations:
- same logical joins as the non-breakdown fact tables, plus the breakdown attributes in the unique key.

## `meta_insights_raw`

Purpose: append-only raw storage for insight payloads before normalization.

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `id` | `BIGSERIAL` | PK | Surrogate row ID |
| `account_id` | `TEXT` |  | Meta account ID |
| `level` | `TEXT` |  | `ad`, `adset`, `campaign`, or `account` |
| `date_start` | `DATE` |  | Payload date start |
| `date_stop` | `DATE` |  | Payload date stop |
| `breakdowns` | `TEXT` |  | Comma-separated breakdown list |
| `fetched_at` | `TIMESTAMPTZ` | DEFAULT `now()` | Load timestamp |
| `payload` | `JSONB` | NOT NULL | Full raw payload |

Relations:
- Feeds all `fact_meta_delivery_*` tables after transformation.
- Logical replay source keyed by `account_id`, `level`, `date_start`, `date_stop`, and `breakdowns`.

## `meta_accounts_raw`

Purpose: append-only raw storage for account payloads.

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `id` | `BIGSERIAL` | PK | Surrogate row ID |
| `account_id` | `TEXT` |  | Meta account ID |
| `fetched_at` | `TIMESTAMPTZ` | DEFAULT `now()` | Load timestamp |
| `payload` | `JSONB` | NOT NULL | Full raw payload |

Relations:
- Feeds `dim_meta_accounts`.

## `dim_meta_creatives`

Purpose: legacy compatibility dimension for creatives.

Unique key:
- `UNIQUE (creative_id)`

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `creative_id` | `TEXT` | PK, UNIQUE | Meta creative ID |
| `account_id` | `TEXT` | Logical FK | Related account |
| `creative_name` | `TEXT` |  | Creative name |
| `status` | `TEXT` |  | Creative status |

Relations:
- `account_id -> dim_meta_accounts.id`

## `dim_meta_ads`

Purpose: legacy compatibility dimension for ads.

Unique key:
- `UNIQUE (ad_id)`

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `ad_id` | `TEXT` | PK, UNIQUE | Meta ad ID |
| `account_id` | `TEXT` | Logical FK | Related account |
| `ad_name` | `TEXT` |  | Ad name |
| `adset_id` | `TEXT` | Logical FK | Related ad set |
| `campaign_id` | `TEXT` | Logical FK | Related campaign |

Relations:
- `account_id -> dim_meta_accounts.id`
- `adset_id -> dim_meta_adsets.adset_id`
- `campaign_id -> dim_meta_campaigns.campaign_id`

## `dim_meta_campaigns`

Purpose: legacy compatibility dimension for campaigns.

Unique key:
- `UNIQUE (campaign_id)`

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `campaign_id` | `TEXT` | PK, UNIQUE | Meta campaign ID |
| `account_id` | `TEXT` | Logical FK | Related account |
| `campaign_name` | `TEXT` |  | Campaign name |

Relations:
- `account_id -> dim_meta_accounts.id`

## `dim_meta_adsets`

Purpose: legacy compatibility dimension for ad sets.

Unique key:
- `UNIQUE (adset_id)`

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `adset_id` | `TEXT` | PK, UNIQUE | Meta ad set ID |
| `account_id` | `TEXT` | Logical FK | Related account |
| `campaign_id` | `TEXT` | Logical FK | Related campaign |
| `adset_name` | `TEXT` |  | Ad set name |

Relations:
- `account_id -> dim_meta_accounts.id`
- `campaign_id -> dim_meta_campaigns.campaign_id`

## `dim_meta_ads_settings`

Purpose: legacy compatibility dimension for ad settings-level metadata.

Unique key:
- `UNIQUE (ad_id)`

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `ad_id` | `TEXT` | PK, UNIQUE | Meta ad ID |
| `account_id` | `TEXT` | Logical FK | Related account |
| `adset_id` | `TEXT` | Logical FK | Related ad set |
| `campaign_id` | `TEXT` | Logical FK | Related campaign |
| `ad_name` | `TEXT` |  | Ad name |

Relations:
- `account_id -> dim_meta_accounts.id`
- `adset_id -> dim_meta_adsets.adset_id`
- `campaign_id -> dim_meta_campaigns.campaign_id`

## `meta_creatives_raw`

Purpose: append-only raw storage for creative payloads.

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `id` | `BIGSERIAL` | PK | Surrogate row ID |
| `creative_id` | `TEXT` |  | Meta creative ID |
| `account_id` | `TEXT` |  | Related account |
| `fetched_at` | `TIMESTAMPTZ` | DEFAULT `now()` | Load timestamp |
| `payload` | `JSONB` | NOT NULL | Full raw payload |

Relations:
- Feeds `dim_meta_creatives`.

## `meta_campaigns_raw`

Purpose: append-only raw storage for campaign payloads.

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `id` | `BIGSERIAL` | PK | Surrogate row ID |
| `campaign_id` | `TEXT` |  | Meta campaign ID |
| `account_id` | `TEXT` |  | Related account |
| `fetched_at` | `TIMESTAMPTZ` | DEFAULT `now()` | Load timestamp |
| `payload` | `JSONB` | NOT NULL | Full raw payload |

Relations:
- Feeds `dim_meta_campaigns`.

## `meta_adsets_raw`

Purpose: append-only raw storage for ad set payloads.

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `id` | `BIGSERIAL` | PK | Surrogate row ID |
| `adset_id` | `TEXT` |  | Meta ad set ID |
| `account_id` | `TEXT` |  | Related account |
| `campaign_id` | `TEXT` |  | Related campaign |
| `fetched_at` | `TIMESTAMPTZ` | DEFAULT `now()` | Load timestamp |
| `payload` | `JSONB` | NOT NULL | Full raw payload |

Relations:
- Feeds `dim_meta_adsets`.

## `meta_ads_raw`

Purpose: append-only raw storage for ad payloads.

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `id` | `BIGSERIAL` | PK | Surrogate row ID |
| `ad_id` | `TEXT` |  | Meta ad ID |
| `account_id` | `TEXT` |  | Related account |
| `adset_id` | `TEXT` |  | Related ad set |
| `campaign_id` | `TEXT` |  | Related campaign |
| `fetched_at` | `TIMESTAMPTZ` | DEFAULT `now()` | Load timestamp |
| `payload` | `JSONB` | NOT NULL | Full raw payload |

Relations:
- Feeds `dim_meta_ads` or `dim_meta_ads_settings`, depending on the pipeline path.

## `meta_ads_previews_raw`

Purpose: append-only raw storage for ad preview payloads.

| Column | Type | Constraint | Notes |
| --- | --- | --- | --- |
| `id` | `BIGSERIAL` | PK | Surrogate row ID |
| `ad_id` | `TEXT` |  | Meta ad ID |
| `account_id` | `TEXT` |  | Related account |
| `fetched_at` | `TIMESTAMPTZ` | DEFAULT `now()` | Load timestamp |
| `payload` | `JSONB` | NOT NULL | Full raw payload |

Relations:
- Logical relation to ad-level dimensions through `ad_id`.

## Schema Evolution Rules

These behaviors come from `src/etl/load/schema_manager.py` and matter when interpreting the schema:

- Missing tables are auto-created.
- Missing columns are auto-added at load time.
- Column names are normalized to lowercase, underscore-separated SQL-safe names.
- ID-like columns are coerced to `TEXT`.
- Incoming numeric-like columns can cause existing `TEXT` columns to be upgraded to `NUMERIC`.
- For insights tables, the static schema is only the starting point; additional columns may appear over time based on payload shape.

## Recommended Reporting Joins

- Account reporting:
  - `fact_meta_delivery_account.account_id = dim_meta_accounts.id`
- Campaign reporting:
  - `fact_meta_delivery_campaign.account_id = dim_meta_accounts.id`
  - `fact_meta_delivery_campaign.campaign_id = dim_meta_campaigns.campaign_id`
- Ad set reporting:
  - `fact_meta_delivery_adset.adset_id = dim_meta_adsets.adset_id`
  - `fact_meta_delivery_adset.campaign_id = dim_meta_campaigns.campaign_id`
- Ad reporting:
  - `fact_meta_delivery_ad.account_id = dim_meta_accounts.id`
  - `fact_meta_delivery_ad.campaign_id = dim_meta_campaigns.campaign_id`
  - `fact_meta_delivery_ad.adset_id = dim_meta_adsets.adset_id`
  - `fact_meta_delivery_ad.ad_id = dim_meta_ads_settings.ad_id`
