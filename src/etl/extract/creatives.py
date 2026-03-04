import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from src.clients.graph_client import GraphAPIClient, GraphAPIError
from src.config import load_ad_account_ids, load_graph_config

graph_cfg = load_graph_config()
client = GraphAPIClient(
    access_token=graph_cfg.access_token,
    version=graph_cfg.version,
    base_url=graph_cfg.base_url,
)

# Core creative fields to pull; add more if needed.
CREATIVE_FIELDS = [
    "id",
    "account_id",
    "name",
    "status",
    "object_story_id",
    "object_type",
    "object_story_spec",
    "asset_feed_spec",
    "template_url",
    "template_url_spec",
    "degrees_of_freedom_spec",
    "dynamic_ad_voice",
    "product_set_id",
    "url_tags",
    "link_url",
    "instagram_permalink_url",
    "image_hash",
    "image_url",
    "thumbnail_url",
    "video_id",
    "body",
    "title",
    "call_to_action_type",
]


def fetch_creatives(
    ad_account_ids: Optional[List[str]] = None,
    max_workers: int = 1,
) -> List[Dict[str, Any]]:
    """
    Fetch ad creatives across configured ad accounts with pagination.
    """
    account_ids = ad_account_ids or load_ad_account_ids()
    if not account_ids:
        raise ValueError("META_AD_ACCOUNT_IDS is empty; provide at least one account id.")

    all_rows: List[Dict[str, Any]] = []

    base_params = {
        "fields": ",".join(CREATIVE_FIELDS),
        # Smaller page size to avoid oversized responses
        "limit": 100,
    }

    def _fetch_for_account(account_id: str) -> List[Dict[str, Any]]:
        endpoint = f"{account_id}/adcreatives"
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
                    raise GraphAPIError(f"Creatives fetch failed for {futures[fut]}: {e}") from e
                all_rows.extend(rows)
    else:
        for account_id in account_ids:
            rows = _fetch_for_account(account_id)
            all_rows.extend(rows)

    return all_rows


def fetch_creatives_with_previews(
    ad_format: str = "MOBILE_FEED_BASIC",
    limit: int = 100,
    ad_account_ids: Optional[List[str]] = None,
    max_workers: int = 1,
) -> List[Dict[str, Any]]:
    """
    Fetch ad creatives with inline previews for a specific format.
    """
    account_ids = ad_account_ids or load_ad_account_ids()
    if not account_ids:
        raise ValueError("META_AD_ACCOUNT_IDS is empty; provide at least one account id.")

    all_rows: List[Dict[str, Any]] = []
    fields = [
        "id",
        "account_id",
        f"previews.ad_format({ad_format})",
    ]

    base_params = {
        "fields": ",".join(fields),
        "limit": limit,
    }

    def _fetch_for_account(account_id: str) -> List[Dict[str, Any]]:
        endpoint = f"{account_id}/adcreatives"
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
                    raise GraphAPIError(f"Creatives preview fetch failed for {futures[fut]}: {e}") from e
                all_rows.extend(rows)
    else:
        for account_id in account_ids:
            rows = _fetch_for_account(account_id)
            all_rows.extend(rows)

    return all_rows


def extract_first_url(html_body: str) -> Optional[str]:
    """
    Extract the first http(s) URL from an HTML snippet.
    """
    if not html_body:
        return None
    match = re.search(r"https?://[^\s\"'<]+", html_body)
    return match.group(0) if match else None


def normalize_ad_account_id(account_id: str) -> str:
    """
    Ensure ad account IDs are in the act_<id> format required by Graph endpoints.
    """
    if not account_id:
        return account_id
    return account_id if account_id.startswith("act_") else f"act_{account_id}"


def fetch_preview_url(account_id: str, creative_id: str, ad_format: str = "DESKTOP_FEED_STANDARD") -> Optional[str]:
    """
    Fetch a preview URL for a given creative by calling generatepreviews.
    """
    # Use the creative-specific endpoint as we have the ID to avoid "creative parameter required" error
    endpoint = f"{creative_id}/previews"
    params = {
        "ad_format": ad_format,
    }
    payload = client.get(endpoint, params=params)
    data = payload.get("data") or []
    if not data:
        return None
    body = data[0].get("body")
    return extract_first_url(body) or body
