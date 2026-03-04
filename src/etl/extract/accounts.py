from typing import List, Dict

from src.clients.graph_client import GraphAPIClient, GraphAPIError
from src.config import load_graph_config

graph_cfg = load_graph_config()
client = GraphAPIClient(
    access_token=graph_cfg.access_token,
    version=graph_cfg.version,
    base_url=graph_cfg.base_url,
)


ACCOUNT_FIELDS = [
    "id",
    "name",
    "account_status",
    "currency",
    "timezone_id",
    "amount_spent",
    "spend_cap",
    "balance",
    "business_name",
    "disable_reason",
    "funding_source_details",
    "created_time",
]


def fetch_accounts() -> List[Dict]:
    """
    Fetch ad accounts accessible to the token (includes billing-ish fields).
    """
    endpoint = "me/adaccounts"
    params = {
        "fields": ",".join(ACCOUNT_FIELDS),
        "limit": 200,
    }
    try:
        return client.fetch_list(endpoint, params=params, use_next_url=True)
    except GraphAPIError:
        raise
