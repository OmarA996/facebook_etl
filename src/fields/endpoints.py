# src/fields/endpoints.py

ENDPOINT_FIELDS = {
    # Delivery insights fields
    "insights": {
        "ad": [
            "date_start","date_stop",
            "account_id","account_name",
            "campaign_id","campaign_name",
            "adset_id","adset_name",
            "ad_id","ad_name",
            "objective","results","optimization_goal",
            "spend","social_spend","reach","impressions",
            "estimated_ad_recall_rate","clicks","unique_clicks",
            "unique_inline_link_clicks",
            "unique_outbound_clicks","outbound_clicks",
            "video_30_sec_watched_actions","video_avg_time_watched_actions",
            "video_p100_watched_actions","video_p25_watched_actions",
            "video_p50_watched_actions","video_p75_watched_actions",
            "video_p95_watched_actions",
            "actions","action_values","video_play_actions"
        ],
        "adset": [
            "date_start", "date_stop",
            "campaign_id", "campaign_name",
            "adset_id", "adset_name",
            "objective", "spend", "impressions", "reach",
            "clicks", "ctr", "cpm", "cpp", "frequency",
        ],
        "campaign": [
            "date_start", "date_stop",
            "account_id", "account_name",
            "campaign_id", "campaign_name",
            "objective", "spend", "impressions", "reach",
            "clicks", "ctr", "cpm", "cpp", "frequency",
        ],
        "account": [
            "date_start", "date_stop",
            "account_id", "account_name",
            "spend", "impressions", "reach", "clicks",
            "ctr", "cpm", "cpp", "frequency",
        ],
    },
}
