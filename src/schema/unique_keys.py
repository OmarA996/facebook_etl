# src/schema/unique_keys.py
# Central definition of natural keys / dedupe rules per table.

UNIQUE_KEYS = {
    # Meta insights facts
    "fact_meta_delivery_ad": ["ad_id", "date_start"],
    "fact_meta_delivery_adset": ["adset_id", "date_start"],
    "fact_meta_delivery_campaign": ["campaign_id", "date_start"],
    "fact_meta_delivery_account": ["account_id", "date_start"],

    # examples for future tables:
    # "dim_meta_campaigns": ["campaign_id"],
    # "dim_meta_adsets": ["adset_id"],
    # "dim_meta_ads": ["ad_id"],
}
