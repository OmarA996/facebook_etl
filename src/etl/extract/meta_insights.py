# src/etl/extract/meta_insights.py

from typing import List, Dict, Any, Optional

from src.clients.graph_client import GraphAPIClient
from src.config.settings import META_AD_ACCOUNT_IDS
from src.fields.endpoints import ENDPOINT_FIELDS
from src.config import load_graph_config
from src.clients.graph_client import GraphAPIClient

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
) -> List[Dict[str, Any]]:
    """
    Fetch insights from Meta API.

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

    fields = get_insights_fields(level)
    all_records: List[Dict[str, Any]] = []

    for account_id in META_AD_ACCOUNT_IDS:
        endpoint = f"{account_id}/insights"

        params = {
            "fields": ",".join(fields),
            "limit": 500,
            "level": level,      # REQUIRED FOR TRUE AD LEVEL
            "breakdowns": "",    # keeping your original intent
        }

        # Preset mode (old behavior)
        if date_preset:
            params["date_preset"] = date_preset

        # Range mode (new behavior)
        else:
            params["time_range"] = {
                "since": since,
                "until": until,
            }

        data = client.get(endpoint, params)
        all_records.extend(data.get("data", []))

    return all_records
