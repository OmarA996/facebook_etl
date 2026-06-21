# src/schema/unique_keys.py
# Natural keys used by UPSERT logic.

UNIQUE_KEYS = {
    # Delivery insights fact tables
    "fact_meta_delivery_ad": ["ad_id", "date_start"],
    "fact_meta_delivery_adset": ["adset_id", "date_start"],
    "fact_meta_delivery_campaign": ["campaign_id", "date_start"],
    # Delivery insights breakdown tables
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

    # Operational
    "etl_insights_checkpoint": ["profile", "level", "breakdowns_key", "since", "until"],

    # Goals
    "dim_goals": ["account_id", "month"],

    # Accounts dimension
    "dim_meta_accounts": ["id"],
    "dim_meta_account_registry": ["account_id"],
    # Legacy dimensions kept for compatibility (not part of core runtime)
    "dim_meta_creatives": ["creative_id"],
    "dim_meta_ads": ["ad_id"],
    "dim_meta_campaigns": ["campaign_id"],
    "dim_meta_adsets": ["adset_id"],
}
