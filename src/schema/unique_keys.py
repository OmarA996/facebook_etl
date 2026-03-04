# src/schema/unique_keys.py
# Central definition of natural keys / dedupe rules per table.

UNIQUE_KEYS = {
    # Meta insights facts
    "fact_meta_delivery_ad": ["ad_id", "date_start"],
    "fact_meta_delivery_adset": ["adset_id", "date_start"],
    "fact_meta_delivery_campaign": ["campaign_id", "date_start"],
    "fact_meta_delivery_account": ["account_id", "date_start"],
    # Insights breakdown tables
    "fact_meta_delivery_ad__age": ["ad_id", "date_start", "age"],
    "fact_meta_delivery_ad__gender": ["ad_id", "date_start", "gender"],
    "fact_meta_delivery_ad__age_gender": ["ad_id", "date_start", "age", "gender"],
    "fact_meta_delivery_ad__country": ["ad_id", "date_start", "country"],
    "fact_meta_delivery_ad__attribution_setting": ["ad_id", "date_start", "attribution_setting"],
    "fact_meta_delivery_adset__age": ["adset_id", "date_start", "age"],
    "fact_meta_delivery_adset__gender": ["adset_id", "date_start", "gender"],
    "fact_meta_delivery_adset__age_gender": ["adset_id", "date_start", "age", "gender"],
    "fact_meta_delivery_adset__country": ["adset_id", "date_start", "country"],
    "fact_meta_delivery_adset__attribution_setting": ["adset_id", "date_start", "attribution_setting"],
    "fact_meta_delivery_campaign__age": ["campaign_id", "date_start", "age"],
    "fact_meta_delivery_campaign__gender": ["campaign_id", "date_start", "gender"],
    "fact_meta_delivery_campaign__age_gender": ["campaign_id", "date_start", "age", "gender"],
    "fact_meta_delivery_campaign__country": ["campaign_id", "date_start", "country"],
    "fact_meta_delivery_campaign__attribution_setting": ["campaign_id", "date_start", "attribution_setting"],
    "fact_meta_delivery_account__age": ["account_id", "date_start", "age"],
    "fact_meta_delivery_account__gender": ["account_id", "date_start", "gender"],
    "fact_meta_delivery_account__age_gender": ["account_id", "date_start", "age", "gender"],
    "fact_meta_delivery_account__country": ["account_id", "date_start", "country"],
    "fact_meta_delivery_account__attribution_setting": ["account_id", "date_start", "attribution_setting"],

    # Meta accounts dimension
    "dim_meta_accounts": ["id"],
    # Meta creatives dimension
    "dim_meta_creatives": ["creative_id"],
    # Meta ads dimension
    "dim_meta_ads": ["ad_id"],
    # Meta campaigns dimension
    "dim_meta_campaigns": ["campaign_id"],
    # Meta adsets dimension
    "dim_meta_adsets": ["adset_id"],
    # Meta ads settings dimension
    "dim_meta_ads_settings": ["ad_id"],
    # Raw tables (append-only; no unique constraints)
    "meta_insights_raw": [],
    "meta_accounts_raw": [],
    "meta_creatives_raw": [],
    "meta_campaigns_raw": [],
    "meta_adsets_raw": [],
    "meta_ads_raw": [],
    "meta_ads_previews_raw": [],

    # examples for future tables:
    # "dim_meta_campaigns": ["campaign_id"],
    # "dim_meta_adsets": ["adset_id"],
    # "dim_meta_ads": ["ad_id"],
}
