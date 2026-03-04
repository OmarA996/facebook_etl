# src/etl/extract/meta_insights.py

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from src.clients.graph_client import GraphAPIClient, GraphAPIError
from src.config import load_ad_account_ids, load_graph_config
from src.fields.endpoints import ENDPOINT_FIELDS

graph_cfg = load_graph_config()
client = GraphAPIClient(
    access_token=graph_cfg.access_token,
    version=graph_cfg.version,
    base_url=graph_cfg.base_url
)

def get_insights_fields(level: str = "ad") -> List[str]:
    """
    Return the list of fields for a given insights level.

    level can be: "ad", "adset", "campaign", or "account".
    """
    insights = ENDPOINT_FIELDS.get("insights", {})
    if level not in insights:
        raise ValueError(
            f"Invalid insights level '{level}'. "
            "Use one of: 'ad', 'adset', 'campaign', 'account'."
        )
    return insights[level]


def fetch_insights(
    level: str = "ad",
    date_preset: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    breakdowns: Optional[List[str]] = None,
    ad_account_ids: Optional[List[str]] = None,
    max_workers: int = 1,
) -> List[Dict[str, Any]]:
    """
    Fetch insights from Meta API with pagination and retry handling.

    You can use either:
    - date_preset="yesterday" / "last_7d" etc
    OR
    - since="YYYY-MM-DD" and until="YYYY-MM-DD"

    Not both.
    """

    if not date_preset and not (since and until):
        raise ValueError("You must pass either date_preset OR (since and until)")

    if date_preset and (since or until):
        raise ValueError("Use either date_preset OR (since & until), not both")

    account_ids = ad_account_ids or load_ad_account_ids()
    if not account_ids:
        raise ValueError("META_AD_ACCOUNT_IDS is empty; provide at least one account id.")

    fields = get_insights_fields(level)
    all_records: List[Dict[str, Any]] = []

    base_params: Dict[str, Any] = {
        "fields": ",".join(fields),
        "limit": 50,  # Lower limit to prevent timeouts with heavy fields
        "level": level,  # required for ad-level data
        "time_increment": 1,
    }

    if date_preset:
        base_params["date_preset"] = date_preset
    else:
        base_params["time_range[since]"] = since
        base_params["time_range[until]"] = until

    if breakdowns:
        base_params["breakdowns"] = ",".join(b for b in breakdowns if b and b.strip())

    def _fetch_for_account(account_id: str) -> List[Dict[str, Any]]:
        endpoint = f"{account_id}/insights"
        try:
            return client.fetch_list(endpoint, params=dict(base_params), use_next_url=True)
        except GraphAPIError as e:
            raise GraphAPIError(f"{account_id}: {e}") from e

    if max_workers and max_workers > 1 and len(account_ids) > 1:
        workers = min(max_workers, len(account_ids))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_fetch_for_account, acct): acct for acct in account_ids}
            for fut in as_completed(futures):
                account_id = futures[fut]
                try:
                    page_rows = fut.result()
                except Exception as e:
                    raise GraphAPIError(f"Insights fetch failed for {account_id}: {e}") from e
                all_records.extend(page_rows)
    else:
        for account_id in account_ids:
            page_rows = _fetch_for_account(account_id)
            all_records.extend(page_rows)

    return all_records
