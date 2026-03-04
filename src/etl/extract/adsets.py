from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from src.clients.graph_client import GraphAPIClient, GraphAPIError
from src.config import load_graph_config, load_ad_account_ids

graph_cfg = load_graph_config()
client = GraphAPIClient(
    access_token=graph_cfg.access_token,
    version=graph_cfg.version,
    base_url=graph_cfg.base_url,
)

ADSET_FIELDS = [
    "id",
    "name",
    "account_id",
    "campaign_id",
    "created_time",
    "start_time",
    "end_time",
    "updated_time",
    "status",
    "effective_status",
    "learning_stage_info",
    "billing_event",
    "daily_budget",
    "lifetime_budget",
    "bid_amount",
    "bid_strategy",
    "destination_type",
    "optimization_goal",
    "targeting",
]


def fetch_adsets(
    effective_statuses: Optional[List[str]] = None,
    ad_account_ids: Optional[List[str]] = None,
    max_workers: int = 1,
) -> List[Dict[str, Any]]:
    """
    Fetch adsets across configured ad accounts.

    Args:
        effective_statuses: optional list to filter adsets (e.g. ["ACTIVE", "PAUSED"])
    """
    account_ids = ad_account_ids or load_ad_account_ids()
    if not account_ids:
        raise ValueError("META_AD_ACCOUNT_IDS is empty; provide at least one account id.")

    all_rows: List[Dict[str, Any]] = []

    base_params: Dict[str, Any] = {
        "fields": ",".join(ADSET_FIELDS),
        "limit": 200,
    }
    if effective_statuses:
        base_params["effective_status"] = ",".join(effective_statuses)

    def _fetch_for_account(account_id: str) -> List[Dict[str, Any]]:
        endpoint = f"{account_id}/adsets"
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
                    raise GraphAPIError(f"Adsets fetch failed for {futures[fut]}: {e}") from e
                all_rows.extend(rows)
    else:
        for account_id in account_ids:
            rows = _fetch_for_account(account_id)
            all_rows.extend(rows)

    return all_rows
