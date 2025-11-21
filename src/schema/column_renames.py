# src/schema/column_renames.py
# Centralized column renaming map for Meta data across all endpoints
# Keys = long flattened Meta columns
# Values = clean, readable underscore column names for DB + pipeline

META_RENAME_MAP = {
    # ===== Dates =====
    "date_start": "date_start",
    "date_stop": "date_stop",

    # ===== Identity / Hierarchy =====
    "account_id": "account_id",
    "account_name": "account_name",
    "campaign_id": "campaign_id",
    "campaign_name": "campaign_name",
    "adset_id": "adset_id",
    "adset_name": "adset_name",
    "ad_id": "ad_id",
    "ad_name": "ad_name",

    # ===== Objectives =====
    "objective": "objective",
    "optimization_goal": "optimization_goal",

    # ===== Delivery Metrics =====
    "spend": "spend",
    "social_spend": "social_spend",
    "reach": "reach",
    "impressions": "impressions",
    "clicks": "clicks",
    "unique_clicks": "unique_clicks",
    "unique_inline_link_clicks": "unique_inline_link_clicks",

    # ===== Results =====
    "results_actions_omni_landing_page_view": "results_omni_landing_page_view",
    "results_actions_offsite_conversion_fb_pixel_view_content": "results_pixel_view_content",
    "results_actions_offsite_conversion_fb_pixel_purchase": "results_pixel_purchase",
    "results_actions_offsite_conversion_fb_pixel_add_to_cart": "results_pixel_add_to_cart",

    # ===== Click Metrics =====
    "unique_outbound_clicks_outbound_click": "unique_outbound_clicks",
    "outbound_clicks_outbound_click": "outbound_clicks",

    # ===== Actions Metrics (actions_ removed) =====
    "actions_onsite_conversion_total_messaging_connection": "total_messaging_connection",
    "actions_web_in_store_purchase": "web_in_store_purchase",
    "actions_omni_search": "omni_search",
    "actions_offsite_conversion_fb_pixel_search": "pixel_search",
    "actions_omni_purchase": "omni_purchase",
    "actions_link_click": "link_click",
    "actions_omni_add_to_cart": "omni_add_to_cart",
    "actions_omni_initiated_checkout": "omni_initiated_checkout",
    "actions_page_engagement": "page_engagement",
    "actions_purchase": "purchase",
    "actions_landing_page_view": "landing_page_view",
    "actions_add_to_cart": "add_to_cart",
    "actions_omni_landing_page_view": "omni_landing_page_view",
    "actions_post_engagement": "post_engagement",
    "actions_onsite_web_view_content": "onsite_web_view_content",
    "actions_onsite_web_add_to_cart": "onsite_web_add_to_cart",
    "actions_onsite_web_app_purchase": "onsite_web_app_purchase",
    "actions_offsite_content_view_add_meta_leads": "offsite_content_view_add_meta_leads",
    "actions_view_content": "view_content",
    "actions_web_app_in_store_purchase": "web_app_in_store_purchase",
    "actions_onsite_web_app_add_to_cart": "onsite_web_app_add_to_cart",
    "actions_offsite_search_add_meta_leads": "offsite_search_add_meta_leads",
    "actions_post": "post_share",
    "actions_onsite_conversion_post_save": "post_save",

    # 🔧 FIXED: give onsite/web its own name, keep generic as "initiate_checkout"
    "actions_onsite_web_initiate_checkout": "onsite_initiate_checkout",
    "actions_initiate_checkout": "initiate_checkout",

    "actions_onsite_conversion_post_net_save": "post_net_save",
    "actions_onsite_conversion_messaging_first_reply": "messaging_first_reply",
    "actions_onsite_web_app_view_content": "onsite_web_app_view_content",
    "actions_post_interaction_gross": "post_interaction",
    "actions_like": "post_like",
    "actions_onsite_web_purchase": "onsite_web_purchase",
    "actions_onsite_conversion_messaging_conversation_started_7d": "messaging_conversation_started_7d",
    "actions_onsite_conversion_messaging_conversation_replied_7d": "messaging_conversation_replied_7d",
    "actions_search": "searches",
    "actions_omni_view_content": "omni_view_content",
    "actions_offsite_conversion_fb_pixel_view_content": "pixel_view_content",
    "actions_offsite_conversion_fb_pixel_add_to_cart": "pixel_add_to_cart",
    "actions_post_reaction": "post_reaction",
    "actions_offsite_conversion_fb_pixel_initiate_checkout": "pixel_initiate_checkout",
    "actions_offsite_conversion_fb_pixel_purchase": "pixel_purchase",
    "actions_onsite_conversion_messaging_user_depth_2_message_send": "messaging_depth_2",
    "actions_onsite_conversion_messaging_user_depth_3_message_send": "messaging_depth_3",
    "actions_comment": "post_comment",
    "actions_onsite_conversion_messaging_user_depth_5_message_send": "messaging_depth_5",
    "actions_video_view": "video_view",
    "actions_photo_view": "photo_view",

    # ===== Action Value Metrics =====
    "action_values_onsite_web_app_purchase": "value_onsite_app_purchase",
    "action_values_onsite_web_app_add_to_cart": "value_onsite_app_add_to_cart",
    "action_values_onsite_web_initiate_checkout": "value_onsite_initiate_checkout",
    "action_values_search": "value_search",
    "action_values_omni_initiated_checkout": "value_omni_initiated_checkout",
    "action_values_offsite_conversion_fb_pixel_view_content": "value_pixel_view_content",
    "action_values_web_app_in_store_purchase": "value_web_app_in_store_purchase",
    "action_values_omni_view_content": "value_omni_view_content",
    "action_values_add_to_cart": "value_add_to_cart",
    "action_values_onsite_web_purchase": "value_onsite_purchase",
    "action_values_offsite_conversion_fb_pixel_add_to_cart": "value_pixel_add_to_cart",
    "action_values_purchase": "value_purchase",
    "action_values_view_content": "value_view_content",
    "action_values_offsite_conversion_fb_pixel_initiate_checkout": "value_pixel_initiate_checkout",
    "action_values_onsite_web_view_content": "value_onsite_view_content",
    "action_values_onsite_web_app_view_content": "value_onsite_app_view_content",
    "action_values_offsite_conversion_fb_pixel_purchase": "value_pixel_purchase",
    "action_values_initiate_checkout": "value_initiate_checkout",
    "action_values_omni_add_to_cart": "value_omni_add_to_cart",
    "action_values_omni_purchase": "value_omni_purchase",
    "action_values_offsite_conversion_fb_pixel_search": "value_pixel_search",
    "action_values_omni_search": "value_omni_search",
    "action_values_web_in_store_purchase": "value_web_in_store_purchase",
    "action_values_onsite_web_add_to_cart": "value_onsite_add_to_cart",

    # ===== Video Metrics =====
    "video_avg_time_watched_actions_video_view": "video_avg_watch_time",
    "video_p25_watched_actions_video_view": "video_25_watch",
    "video_play_actions_video_view": "video_play",
    "video_30_sec_watched_actions_video_view": "video_30_sec_watch",
    "video_p100_watched_actions_video_view": "video_100_watch",
    "video_p50_watched_actions_video_view": "video_50_watch",
    "video_p75_watched_actions_video_view": "video_75_watch",
    "video_p95_watched_actions_video_view": "video_95_watch",
}
