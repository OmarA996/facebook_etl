from dataclasses import dataclass
from typing import List

from src.config.settings import settings


@dataclass
class GraphConfig:
    access_token: str
    version: str
    base_url: str


@dataclass
class PostgresConfig:
    conn_string: str


def load_ad_account_ids(profile: str | None = None) -> List[str]:
    """
    Return ad account ids for a given profile, falling back to default list.
    """
    def _normalize(account_id: str) -> str:
        if not account_id:
            return account_id
        return account_id if account_id.startswith("act_") else f"act_{account_id}"

    raw_ids = settings.get_ad_account_ids(profile)
    return [_normalize(acc) for acc in raw_ids]


def load_graph_config() -> GraphConfig:
    """
    Build a Graph API config object from environment-backed settings.

    Note: GraphAPIClient expects `base_url` without the version suffix
    because it appends `/{version}/{endpoint}` internally.
    """
    # The canonical host; avoid double-including the version from BASE_META_URL.
    base_url = "https://graph.facebook.com"

    return GraphConfig(
        access_token=settings.META_ACCESS_TOKEN,
        version=settings.META_API_VERSION,
        base_url=base_url,
    )


def load_postgres_config(profile: str | None = None) -> PostgresConfig:
    """
    Build a Postgres config object based on profile.

    - profile is lowercased and mapped to env var DB_CONN_STRING_<PROFILE>
    - profile=None falls back to DB_CONN_STRING_DEFAULT or DB_CONN_STRING
    """
    if profile:
        key = profile.lower()
        conn = settings.db_conn_profiles.get(key)
        if not conn:
            raise ValueError(
                f"No DB connection string found for profile '{profile}'. "
                "Set DB_CONN_STRING_<PROFILE> in your environment."
            )
        return PostgresConfig(conn_string=conn)

    # default path
    conn = settings.DB_CONN_STRING_DEFAULT or settings.DB_CONN_STRING
    if not conn:
        raise ValueError("No default DB connection string found. Set DB_CONN_STRING or DB_CONN_STRING_DEFAULT.")
    return PostgresConfig(conn_string=conn)
