import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from src.clients.graph_client import GraphAPIClient, GraphAPIError
from src.config import load_ad_account_ids, load_graph_config

graph_cfg = load_graph_config()
client = GraphAPIClient(
    access_token=graph_cfg.access_token,
    version=graph_cfg.version,
    base_url=graph_cfg.base_url,
)

AD_FIELDS = [
    "id",
    "name",
    "account_id",
    "adset_id",
    "campaign_id",
    "status",
    "configured_status",
    "effective_status",
    "created_time",
    "updated_time",
    "ad_review_feedback",
    "issues_info",
    "tracking_specs",
    # delivery_info is not available on Ad in Graph API v22; omit to avoid (#100) errors
    "creative{id,name,object_type,object_story_id,object_story_spec,asset_feed_spec,template_url,template_url_spec,degrees_of_freedom_spec,dynamic_ad_voice,product_set_id,url_tags,link_url,instagram_permalink_url,image_hash,image_url,thumbnail_url,video_id,body,title,call_to_action_type}",
]


def fetch_ads(
    effective_statuses: Optional[List[str]] = None,
    ad_account_ids: Optional[List[str]] = None,
    max_workers: int = 1,
) -> List[Dict[str, Any]]:
    """
    Fetch ads with their creative ids for the configured accounts.

    Args:
        effective_statuses: optional list of effective_status values to filter (e.g. ["ACTIVE", "PAUSED"]).

    Returns:
        List of ad dicts.
    """
    account_ids = ad_account_ids or load_ad_account_ids()
    if not account_ids:
        raise ValueError("META_AD_ACCOUNT_IDS is empty; provide at least one account id.")

    all_rows: List[Dict[str, Any]] = []

    base_params: Dict[str, Any] = {
        "fields": ",".join(AD_FIELDS),
        "limit": 100,
    }
    if effective_statuses:
        base_params["effective_status"] = ",".join(effective_statuses)

    def _fetch_for_account(account_id: str) -> List[Dict[str, Any]]:
        endpoint = f"{account_id}/ads"
        try:
            return client.fetch_list(endpoint, params=dict(base_params), use_next_url=True)
        except GraphAPIError as e:
            raise GraphAPIError(f"{account_id}: {e}") from e

    if max_workers and max_workers > 1 and len(account_ids) > 1:
        workers = min(max_workers, len(account_ids))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_fetch_for_account, acct): acct for acct in account_ids}
            for fut in as_completed(futures):
                try:
                    rows = fut.result()
                except Exception as e:
                    raise GraphAPIError(f"Ads fetch failed for {futures[fut]}: {e}") from e
                all_rows.extend(rows)
    else:
        for account_id in account_ids:
            rows = _fetch_for_account(account_id)
            all_rows.extend(rows)

    return all_rows


def fetch_ad_preview(ad_id: str, ad_format: str = "MOBILE_FEED_BASIC") -> Tuple[Optional[str], Optional[str]]:
    """
    Fetch preview HTML for an ad_id and return (preview_url, raw_body_html).
    """
    if not ad_id:
        return None, None

    endpoint = f"{ad_id}/previews"
    params = {
        "ad_format": ad_format,
        "fields": "body",  # align with Graph API explorer usage
    }
    try:
        payload = client.get(endpoint, params=params)
    except GraphAPIError:
        raise

    data = payload.get("data") or []
    if not data:
        return None, None

    body = data[0].get("body")
    if not body:
        return None, None

    # Unescape HTML entities to get a clickable URL (the iframe HTML is entity-encoded)
    body_unescaped = html.unescape(body)
    match = re.search(r"https?://[^\s\"'<]+", body_unescaped)
    url = match.group(0) if match else None
    return url, body_unescaped
