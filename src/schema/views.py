from __future__ import annotations

VIEW_NAME = "vw_meta_ads_full"

_DIM_ACCOUNTS_COLS: list[tuple[str, str | None]] = [
    ("currency", None), ("timezone_id", None), ("account_status", None),
    ("business_name", None), ("disable_reason", None),
    ("funding_source_display", None), ("funding_source_id", None),
    ("funding_source_type", None), ("created_time", "account_created_time"),
]
_DIM_ADS_COLS: list[tuple[str, str | None]] = [
    ("status", "ad_status"), ("effective_status", None),
    ("configured_status", None), ("creative_id", None),
    ("created_time", "ad_created_time"), ("updated_time", "ad_updated_time"),
    ("ad_review_feedback_global_non_functional_landing_page", None),
]
_DIM_CREATIVES_COLS: list[tuple[str, str | None]] = [
    ("creative_name", None), ("title", "creative_title"), ("body", "creative_body"),
    ("description", "creative_description"), ("call_to_action_type", None),
    ("video_id", None), ("link_url", None), ("object_url", None),
    ("display_url", None), ("effective_object_story_id", None), ("status", "creative_status"),
]
_DIM_CAMPAIGNS_COLS: list[tuple[str, str | None]] = [
    ("status", "campaign_status"),
    ("effective_status", "campaign_effective_status"),
    ("bid_strategy", None),
    ("buying_type", None),
    ("daily_budget", None),
    ("lifetime_budget", None),
    ("budget_remaining", None),
    ("start_time", "campaign_start_time"),
    ("stop_time", "campaign_stop_time"),
]


_IMAGE_URL_FALLBACK_COLS: list[str] = [
    "image_url",
    "asset_feed_spec_image_url",
    "object_story_spec_video_data_image_url",
    "object_story_spec_link_data_picture",
]
_THUMBNAIL_URL_FALLBACK_COLS: list[str] = [
    "thumbnail_url",
    "asset_feed_spec_image_url",
    "object_story_spec_video_data_image_url",
    "object_story_spec_link_data_picture",
]
_IMAGE_HASH_FALLBACK_COLS: list[str] = [
    "image_hash",
    "asset_feed_spec_image_hash",
    "object_story_spec_link_data_image_hash",
    "object_story_spec_video_data_image_hash",
]


def _coalesce_fragment(alias: str, cols: list[str], output_name: str, existing: set[str] | None) -> str:
    available = [c for c in cols if existing is None or c in existing]
    if not available:
        return ""
    if len(available) == 1:
        return f"        {alias}.{available[0]} AS {output_name}"
    inner = ", ".join(f"{alias}.{c}" for c in available)
    return f"        COALESCE({inner}) AS {output_name}"

STATIC_FACT_COLUMNS: frozenset[str] = frozenset({
    "date_start", "date_stop",
    "spend", "social_spend", "reach", "impressions", "clicks",
    "unique_clicks", "unique_inline_link_clicks",
    "results_indicator", "results_value",
    "objective", "optimization_goal",
    "account_id", "account_name",
    "campaign_id", "campaign_name",
    "adset_id", "adset_name",
    "ad_id", "ad_name",
    "actions", "action_values", "results",
    "outbound_clicks", "unique_outbound_clicks",
    "video_play_actions",
    "video_p25_watched_actions", "video_p50_watched_actions",
    "video_p75_watched_actions", "video_p95_watched_actions",
    "video_p100_watched_actions", "video_30_sec_watched_actions",
    "video_avg_time_watched_actions",
    "ad_created_time", "ad_updated_time",
})

_STATIC_SELECT = """
    SELECT
        f.date_start,
        f.date_stop,
        f.spend,
        f.social_spend,
        f.reach,
        f.impressions,
        f.clicks,
        f.unique_clicks,
        f.unique_inline_link_clicks,
        f.results_indicator,
        f.results_value,
        f.objective,
        f.optimization_goal,

        f.account_id,
        f.account_name,

        f.campaign_id,
        f.campaign_name,

        f.adset_id,
        f.adset_name,

        f.ad_id,
        f.ad_name,

        f.actions,
        f.action_values,
        f.results,
        f.outbound_clicks,
        f.unique_outbound_clicks,
        f.video_play_actions,
        f.video_p25_watched_actions,
        f.video_p50_watched_actions,
        f.video_p75_watched_actions,
        f.video_p95_watched_actions,
        f.video_p100_watched_actions,
        f.video_30_sec_watched_actions,
        f.video_avg_time_watched_actions"""


def _dim_fragment(
    alias: str,
    cols: list[tuple[str, str | None]],
    existing: set[str] | None,
) -> str:
    lines = []
    for col, col_alias in cols:
        if existing is not None and col not in existing:
            continue
        if col_alias:
            lines.append(f"        {alias}.{col:<55} AS {col_alias}")
        else:
            lines.append(f"        {alias}.{col}")
    return ",\n".join(lines)


def _dynamic_select_fragment(extra_fact_columns: list[str]) -> str:
    if not extra_fact_columns:
        return ""
    lines = ",\n".join(f"        f.{col}" for col in sorted(extra_fact_columns))
    return ",\n" + lines


def postgres_view_sql(
    extra_fact_columns: list[str] | None = None,
    existing_dim_cols: dict[str, set[str]] | None = None,
) -> str:
    edc = existing_dim_cols or {}
    cr_existing = edc.get("dim_meta_creatives")
    cmp_existing = edc.get("dim_meta_campaigns")

    acc_frag = _dim_fragment("acc", _DIM_ACCOUNTS_COLS, edc.get("dim_meta_accounts"))
    ads_frag = _dim_fragment("ad",  _DIM_ADS_COLS,      edc.get("dim_meta_ads"))
    cr_frag  = _dim_fragment("cr",  _DIM_CREATIVES_COLS, cr_existing)
    cmp_frag = _dim_fragment("cmp", _DIM_CAMPAIGNS_COLS, cmp_existing) if cmp_existing is not None else ""
    image_frag = _coalesce_fragment("cr", _IMAGE_URL_FALLBACK_COLS, "image_url", cr_existing)
    thumb_frag = _coalesce_fragment("cr", _THUMBNAIL_URL_FALLBACK_COLS, "thumbnail_url", cr_existing)
    hash_frag  = _coalesce_fragment("cr", _IMAGE_HASH_FALLBACK_COLS,  "image_hash",   cr_existing)
    dynamic  = _dynamic_select_fragment(extra_fact_columns or [])

    cmp_join = "\n    LEFT JOIN dim_meta_campaigns  cmp ON f.campaign_id = cmp.campaign_id" if cmp_existing is not None else ""

    joins = (
        "\n    FROM fact_meta_delivery_ad f"
        "\n    LEFT JOIN dim_meta_accounts  acc ON f.account_id  = REPLACE(acc.id, 'act_', '')"
        "\n    LEFT JOIN dim_meta_ads        ad ON f.ad_id        = ad.ad_id"
        "\n    LEFT JOIN dim_meta_creatives  cr ON ad.creative_id = cr.creative_id"
        + cmp_join
    )

    select = (
        f"{_STATIC_SELECT}"
        + (f",\n{acc_frag}" if acc_frag else "")
        + (f",\n{ads_frag}" if ads_frag else "")
        + (f",\n{cr_frag}"  if cr_frag  else "")
        + (f",\n{cmp_frag}" if cmp_frag else "")
        + (f",\n{image_frag}" if image_frag else "")
        + (f",\n{thumb_frag}" if thumb_frag else "")
        + (f",\n{hash_frag}"  if hash_frag  else "")
        + dynamic
    )
    return f"CREATE VIEW {VIEW_NAME} AS{select}\n{joins}"


def bigquery_view_sql(
    project_id: str,
    dataset_id: str,
    extra_fact_columns: list[str] | None = None,
    existing_dim_cols: dict[str, set[str]] | None = None,
) -> str:
    edc = existing_dim_cols or {}
    cr_existing = edc.get("dim_meta_creatives")
    cmp_existing = edc.get("dim_meta_campaigns")

    acc_frag = _dim_fragment("acc", _DIM_ACCOUNTS_COLS, edc.get("dim_meta_accounts"))
    ads_frag = _dim_fragment("ad",  _DIM_ADS_COLS,      edc.get("dim_meta_ads"))
    cr_frag  = _dim_fragment("cr",  _DIM_CREATIVES_COLS, cr_existing)
    cmp_frag = _dim_fragment("cmp", _DIM_CAMPAIGNS_COLS, cmp_existing) if cmp_existing is not None else ""
    image_frag = _coalesce_fragment("cr", _IMAGE_URL_FALLBACK_COLS, "image_url", cr_existing)
    thumb_frag = _coalesce_fragment("cr", _THUMBNAIL_URL_FALLBACK_COLS, "thumbnail_url", cr_existing)
    hash_frag  = _coalesce_fragment("cr", _IMAGE_HASH_FALLBACK_COLS,  "image_hash",   cr_existing)
    dynamic  = _dynamic_select_fragment(extra_fact_columns or [])

    cmp_join = f"\n    LEFT JOIN `{project_id}.{dataset_id}.dim_meta_campaigns` cmp ON f.campaign_id = cmp.campaign_id" if cmp_existing is not None else ""

    joins = (
        f"\n    FROM `{project_id}.{dataset_id}.fact_meta_delivery_ad` f"
        f"\n    LEFT JOIN `{project_id}.{dataset_id}.dim_meta_accounts`  acc ON f.account_id  = REPLACE(acc.id, 'act_', '')"
        f"\n    LEFT JOIN `{project_id}.{dataset_id}.dim_meta_ads`        ad ON f.ad_id        = ad.ad_id"
        f"\n    LEFT JOIN `{project_id}.{dataset_id}.dim_meta_creatives`  cr ON ad.creative_id = cr.creative_id"
        + cmp_join
    )

    select = (
        f"{_STATIC_SELECT}"
        + (f",\n{acc_frag}" if acc_frag else "")
        + (f",\n{ads_frag}" if ads_frag else "")
        + (f",\n{cr_frag}"  if cr_frag  else "")
        + (f",\n{cmp_frag}" if cmp_frag else "")
        + (f",\n{image_frag}" if image_frag else "")
        + (f",\n{thumb_frag}" if thumb_frag else "")
        + (f",\n{hash_frag}"  if hash_frag  else "")
        + dynamic
    )
    return f"{select}\n{joins}"


BQ_REQUIRED_TABLES = {"fact_meta_delivery_ad", "dim_meta_accounts", "dim_meta_ads", "dim_meta_creatives"}
